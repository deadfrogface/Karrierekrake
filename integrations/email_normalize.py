"""Email normalization pipeline for classification / association.

Pipeline (untrusted content throughout):
  raw MIME -> headers -> plain text -> safe HTML text -> quoted history
  separated -> signature separated -> attachment metadata -> NormalizedEmail

Adapted from PBP email_service (MIT) and GmailJobTracker EmailBodyParser (MIT).
No Django dependency. Prefer Python stdlib ``email``; HTML stripping is regex-
based (no BeautifulSoup required).

Contract versioning
-------------------
``NORMALIZED_EMAIL_VERSION`` bumps when the NormalizedEmail schema changes.
Stored / older mails may be lazy-renormalized when ``schema_version`` is stale
via ``needs_renormalization`` / ``normalize_raw_mime``.
"""

from __future__ import annotations

import base64
import hashlib
import re
from dataclasses import asdict, dataclass, field
from email import message_from_bytes, message_from_string
from email.header import decode_header, make_header
from email.message import Message
from email.utils import parseaddr, parsedate_to_datetime
from html import unescape
from typing import Any, Mapping, Optional


NORMALIZED_EMAIL_VERSION = 1


_TAG_RE = re.compile(r"<[^>]+>")
_STYLE_RE = re.compile(r"<style[^>]*>[\s\S]*?</style>", re.I)
_SCRIPT_RE = re.compile(r"<script[^>]*>[\s\S]*?</script>", re.I)
_COMMENT_RE = re.compile(r"<!--[\s\S]*?-->")
_BLOCK_BREAK_RE = re.compile(
    r"</(?:p|div|br|tr|li|h[1-6])\s*>|<br\s*/?>",
    re.I,
)

_QUOTE_LINE_START = re.compile(r"^\s*>+")
_QUOTE_MARKERS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.I)
    for p in (
        r"^on .+ wrote:\s*$",
        r"^am .+ schrieb .+:\s*$",
        r"^-{2,}\s*original message\s*-{2,}",
        r"^-{2,}\s*urspr(?:ü|u)ngliche nachricht\s*-{2,}",
        r"^_{5,}\s*$",
        r"^from:\s+.+\n(?:sent|date):\s+",
        r"^von:\s+.+\n(?:gesendet|datum):\s+",
        r"^-+\s*forwarded message\s*-+",
        r"^-+\s*weitergeleitete nachricht\s*-+",
        r"^begin forwarded message",
        r"^-----+\s*weitergeleitet",
    )
)

_SIGNATURE_MARKERS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.I | re.M)
    for p in (
        r"^--\s*$",
        r"^—\s*$",
        r"^_{2,}\s*$",
        r"^mit freundlichen gr(?:ü|u)(?:ß|ss)en\b",
        r"^freundliche gr(?:ü|u)(?:ß|ss)e\b",
        r"^viele gr(?:ü|u)(?:ß|ss)e\b",
        r"^best regards\b",
        r"^kind regards\b",
        r"^regards\b",
        r"^sent from my (iphone|ipad|android)",
        r"^gesendet von mein(?:em|er)\b",
        r"^get outlook for\b",
    )
)


@dataclass(frozen=True)
class AttachmentMeta:
    """Metadata only — never open / execute attachment payloads."""

    filename: str = ""
    content_type: str = ""
    size_bytes: int = 0
    content_id: str = ""
    content_disposition: str = ""
    checksum_sha256: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class NormalizedEmail:
    """Versioned normalized email contract (untrusted body throughout)."""

    schema_version: int = NORMALIZED_EMAIL_VERSION
    message_id: str = ""
    subject: str = ""
    from_raw: str = ""
    from_email: str = ""
    from_domain: str = ""
    to_raw: str = ""
    cc_raw: str = ""
    date_header: str = ""
    date_iso: str = ""
    content_type: str = ""
    charset: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    plain_text: str = ""
    html_text: str = ""
    body_text: str = ""
    quoted_history: str = ""
    signature: str = ""
    attachments: list[AttachmentMeta] = field(default_factory=list)
    parse_warnings: list[str] = field(default_factory=list)
    is_multipart: bool = False
    is_html_only: bool = False
    is_forwarded: bool = False
    body_sha256: str = ""
    raw_size_bytes: int = 0

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["attachments"] = [
            a.to_dict() if isinstance(a, AttachmentMeta) else a for a in self.attachments
        ]
        return d

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "NormalizedEmail":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        kwargs = {k: v for k, v in data.items() if k in known}
        atts = kwargs.pop("attachments", None) or []
        kwargs["attachments"] = [
            AttachmentMeta(**a) if isinstance(a, dict) else a for a in atts
        ]
        return cls(**kwargs)

    def classification_text(self) -> str:
        return re.sub(r"\s+", " ", f"{self.subject}\n{self.body_text}").strip()


def needs_renormalization(stored: Mapping[str, Any] | NormalizedEmail | None) -> bool:
    if stored is None:
        return True
    if isinstance(stored, NormalizedEmail):
        ver = stored.schema_version
    else:
        ver = int(stored.get("schema_version") or 0)
    return ver < NORMALIZED_EMAIL_VERSION


def html_to_plaintext(html: str) -> str:
    text = html or ""
    text = _COMMENT_RE.sub(" ", text)
    text = _STYLE_RE.sub(" ", text)
    text = _SCRIPT_RE.sub(" ", text)
    text = _BLOCK_BREAK_RE.sub("\n", text)
    text = _TAG_RE.sub(" ", text)
    text = unescape(text)
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def strip_quoted_reply(text: str) -> str:
    body, _quoted = split_quoted_history(text)
    return body


def split_quoted_history(text: str) -> tuple[str, str]:
    if not text:
        return "", ""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    cut: Optional[int] = None
    for i, row in enumerate(lines):
        if _QUOTE_LINE_START.match(row):
            if i > 0:
                cut = i
                break
            continue
        for marker in _QUOTE_MARKERS:
            if marker.search(row):
                cut = i
                break
            if i + 1 < len(lines):
                pair = row + "\n" + lines[i + 1]
                if marker.search(pair):
                    cut = i
                    break
        if cut is not None:
            break
    if cut is None:
        return text.strip(), ""
    current = "\n".join(lines[:cut]).strip()
    quoted = "\n".join(lines[cut:]).strip()
    if not current and quoted:
        return "", quoted
    return current, quoted


def split_signature(text: str) -> tuple[str, str]:
    if not text:
        return "", ""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    start_scan = max(0, len(lines) // 3) if len(lines) > 6 else 0
    cut: Optional[int] = None
    for i in range(start_scan, len(lines)):
        row = lines[i]
        for marker in _SIGNATURE_MARKERS:
            if marker.search(row):
                if row.strip() in {"--", "—"} or row.strip() == "--":
                    cut = i
                    break
                rest = lines[i:]
                if len(rest) <= 12:
                    cut = i
                    break
        if cut is not None:
            break
    if cut is None:
        return text.strip(), ""
    body = "\n".join(lines[:cut]).strip()
    sig = "\n".join(lines[cut:]).strip()
    if not body and sig:
        return text.strip(), ""
    return body, sig


def extract_sender_email(sender: str) -> str:
    _, addr = parseaddr(sender or "")
    return (addr or "").strip().lower()


def extract_sender_domain(sender: str) -> str:
    email = extract_sender_email(sender)
    if "@" in email:
        return email.split("@", 1)[1].lower()
    return ""


def decode_gmail_body_data(data: str) -> str:
    if not data:
        return ""
    try:
        pad = "=" * (-len(data) % 4)
        return base64.urlsafe_b64decode((data + pad).encode("utf-8")).decode(
            "utf-8", errors="ignore"
        )
    except Exception:
        return ""


def extract_from_gmail_parts(parts: list[dict[str, Any]]) -> str:
    plain_fallback = ""
    for part in parts or []:
        mime = (part.get("mimeType") or "").lower()
        body_data = (part.get("body") or {}).get("data")
        if mime == "text/html" and body_data:
            decoded = decode_gmail_body_data(body_data)
            if decoded:
                return decoded
        elif mime == "text/plain" and body_data and not plain_fallback:
            plain_fallback = decode_gmail_body_data(body_data)
        nested = part.get("parts") or []
        if nested:
            result = extract_from_gmail_parts(nested)
            if result:
                return result
    return plain_fallback


def normalize_email_text(subject: str, body_html_or_text: str) -> str:
    body = body_html_or_text or ""
    if "<" in body and ">" in body:
        body = html_to_plaintext(body)
    body, _ = split_quoted_history(body)
    body, _ = split_signature(body)
    body = re.sub(r"https?://\S+", " ", body)
    combined = f"{subject or ''}\n{body}"
    return re.sub(r"\s+", " ", combined).strip()


def normalize_umlauts(text: str) -> str:
    return (
        (text or "")
        .lower()
        .replace("ä", "ae")
        .replace("ö", "oe")
        .replace("ü", "ue")
        .replace("ß", "ss")
    )


def _decode_header_value(raw: str) -> str:
    if not raw:
        return ""
    try:
        return str(make_header(decode_header(raw)))
    except Exception:
        try:
            parts = decode_header(raw)
            out: list[str] = []
            for text, enc in parts:
                if isinstance(text, bytes):
                    out.append(text.decode(enc or "utf-8", errors="ignore"))
                else:
                    out.append(text)
            return "".join(out)
        except Exception:
            return raw


def _safe_date_iso(date_header: str) -> str:
    if not date_header:
        return ""
    try:
        dt = parsedate_to_datetime(date_header)
        if dt is None:
            return ""
        return dt.isoformat()
    except Exception:
        return ""


def _part_charset(part: Message) -> str:
    try:
        cs = part.get_content_charset() or ""
    except Exception:
        cs = ""
    return (cs or "utf-8").strip() or "utf-8"


def _decode_part_payload(part: Message) -> tuple[bytes, str]:
    try:
        payload = part.get_payload(decode=True)
    except Exception:
        payload = None
    if payload is None:
        raw = part.get_payload(decode=False)
        if isinstance(raw, bytes):
            payload = raw
        elif isinstance(raw, str):
            return b"", raw
        else:
            return b"", ""
    if not isinstance(payload, bytes):
        return b"", str(payload or "")
    charset = _part_charset(part)
    try:
        text = payload.decode(charset, errors="ignore")
    except Exception:
        text = payload.decode("utf-8", errors="ignore")
    return payload, text


def _collect_headers(msg: Message) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        for k, v in msg.items():
            key = (k or "").strip()
            if not key:
                continue
            if key.lower() not in {x.lower() for x in out}:
                out[key] = _decode_header_value(v)
    except Exception:
        pass
    return out


def _is_attachment(part: Message) -> bool:
    disp = (part.get_content_disposition() or "").lower()
    if disp == "attachment":
        return True
    if part.get_filename():
        main = (part.get_content_maintype() or "").lower()
        if main not in {"text", "multipart"}:
            return True
        if disp == "inline" and main != "text":
            return True
    return False


def _attachment_meta(part: Message) -> AttachmentMeta:
    raw, _ = _decode_part_payload(part)
    filename = ""
    try:
        filename = part.get_filename() or ""
        if filename:
            filename = _decode_header_value(filename)
    except Exception:
        filename = ""
    try:
        ctype = part.get_content_type() or ""
    except Exception:
        ctype = "application/octet-stream"
    checksum = hashlib.sha256(raw).hexdigest() if raw else ""
    return AttachmentMeta(
        filename=filename or "unnamed",
        content_type=ctype or "application/octet-stream",
        size_bytes=len(raw) if raw else 0,
        content_id=(part.get("Content-ID") or "").strip(),
        content_disposition=(part.get_content_disposition() or "") or "",
        checksum_sha256=checksum,
    )


def _walk_message(msg: Message) -> tuple[str, str, list[AttachmentMeta], list[str]]:
    plains: list[str] = []
    htmls: list[str] = []
    attachments: list[AttachmentMeta] = []
    warnings: list[str] = []

    if msg.is_multipart():
        for part in msg.walk():
            try:
                ctype = (part.get_content_type() or "").lower()
            except Exception:
                ctype = ""
                warnings.append("part_content_type_error")
            if ctype.startswith("multipart/"):
                continue
            if _is_attachment(part):
                try:
                    attachments.append(_attachment_meta(part))
                except Exception:
                    warnings.append("attachment_meta_failed")
                continue
            try:
                _raw, text = _decode_part_payload(part)
            except Exception:
                warnings.append("part_decode_failed")
                continue
            if ctype == "text/plain":
                plains.append(text)
            elif ctype == "text/html":
                htmls.append(text)
            elif ctype.startswith("text/") and text.strip():
                plains.append(text)
    else:
        try:
            ctype = (msg.get_content_type() or "").lower()
        except Exception:
            ctype = "text/plain"
            warnings.append("root_content_type_error")
        try:
            _raw, text = _decode_part_payload(msg)
        except Exception:
            text = ""
            warnings.append("root_decode_failed")
        if ctype == "text/html":
            htmls.append(text)
        else:
            plains.append(text)

    plain = "\n\n".join(p for p in plains if p and p.strip())
    html = "\n\n".join(h for h in htmls if h and h.strip())
    return plain, html, attachments, warnings


def _looks_forwarded(subject: str, body: str) -> bool:
    subj = (subject or "").lower()
    if subj.startswith(("fwd:", "fw:", "wg:", "weiterleitung:")):
        return True
    blob = (body or "")[:2000].lower()
    return any(
        m in blob
        for m in (
            "forwarded message",
            "weitergeleitete nachricht",
            "begin forwarded message",
            "---------- forwarded",
        )
    )


def normalize_message(msg: Message, *, raw_size: int = 0) -> NormalizedEmail:
    warnings: list[str] = []
    headers = _collect_headers(msg)
    subject = _decode_header_value(msg.get("Subject") or headers.get("Subject") or "")
    from_raw = _decode_header_value(msg.get("From") or headers.get("From") or "")
    to_raw = _decode_header_value(msg.get("To") or headers.get("To") or "")
    cc_raw = _decode_header_value(msg.get("Cc") or headers.get("Cc") or "")
    date_header = msg.get("Date") or headers.get("Date") or ""
    message_id = (msg.get("Message-ID") or msg.get("Message-Id") or "").strip()

    from_values = [v for k, v in msg.items() if (k or "").lower() == "from"]
    if len(from_values) > 1:
        warnings.append("duplicate_from_header")

    try:
        is_multipart = bool(msg.is_multipart())
        content_type = msg.get_content_type() or ""
    except Exception:
        is_multipart = False
        content_type = ""
        warnings.append("content_type_probe_failed")

    plain, html, attachments, walk_warnings = _walk_message(msg)
    warnings.extend(walk_warnings)

    html_text = html_to_plaintext(html) if html else ""
    is_html_only = bool(html_text) and not (plain or "").strip()

    primary = (plain or "").strip() or html_text
    if not primary:
        warnings.append("empty_body")

    current, quoted = split_quoted_history(primary)
    if not current and quoted:
        warnings.append("quoted_only_body")
        current = quoted
        quoted = ""

    body_no_sig, signature = split_signature(current)
    is_forwarded = _looks_forwarded(subject, primary)

    body_for_hash = body_no_sig.encode("utf-8", errors="ignore")
    return NormalizedEmail(
        schema_version=NORMALIZED_EMAIL_VERSION,
        message_id=message_id,
        subject=subject,
        from_raw=from_raw,
        from_email=extract_sender_email(from_raw),
        from_domain=extract_sender_domain(from_raw),
        to_raw=to_raw,
        cc_raw=cc_raw,
        date_header=date_header,
        date_iso=_safe_date_iso(date_header),
        content_type=content_type,
        charset=_part_charset(msg),
        headers=headers,
        plain_text=plain,
        html_text=html_text,
        body_text=body_no_sig,
        quoted_history=quoted,
        signature=signature,
        attachments=attachments,
        parse_warnings=warnings,
        is_multipart=is_multipart,
        is_html_only=is_html_only,
        is_forwarded=is_forwarded,
        body_sha256=hashlib.sha256(body_for_hash).hexdigest() if body_for_hash else "",
        raw_size_bytes=raw_size,
    )


def normalize_raw_mime(raw: bytes | str) -> NormalizedEmail:
    warnings_prefix: list[str] = []
    if isinstance(raw, bytes):
        raw_bytes = raw
    else:
        raw_bytes = (raw or "").encode("utf-8", errors="ignore")
    if not raw_bytes.strip():
        return NormalizedEmail(
            schema_version=NORMALIZED_EMAIL_VERSION,
            parse_warnings=["empty_raw"],
            raw_size_bytes=0,
        )
    try:
        msg = message_from_bytes(raw_bytes)
    except Exception:
        warnings_prefix.append("message_from_bytes_failed")
        try:
            msg = message_from_string(raw_bytes.decode("utf-8", errors="ignore"))
        except Exception:
            text = raw_bytes.decode("utf-8", errors="ignore")
            body, quoted = split_quoted_history(text)
            body, sig = split_signature(body)
            return NormalizedEmail(
                schema_version=NORMALIZED_EMAIL_VERSION,
                body_text=body,
                plain_text=text,
                quoted_history=quoted,
                signature=sig,
                parse_warnings=warnings_prefix + ["fallback_plaintext_blob"],
                raw_size_bytes=len(raw_bytes),
                body_sha256=hashlib.sha256(
                    body.encode("utf-8", errors="ignore")
                ).hexdigest(),
            )
    result = normalize_message(msg, raw_size=len(raw_bytes))
    if warnings_prefix:
        result.parse_warnings = warnings_prefix + list(result.parse_warnings)
    return result


def normalize_from_parts(
    *,
    subject: str = "",
    sender: str = "",
    body_html_or_text: str = "",
    to: str = "",
    message_id: str = "",
) -> NormalizedEmail:
    raw_body = body_html_or_text or ""
    is_html = bool(re.search(r"<\s*(html|body|div|p|br|table)\b", raw_body, re.I))
    plain = ""
    html_text = ""
    if is_html:
        html_text = html_to_plaintext(raw_body)
        primary = html_text
    else:
        plain = raw_body
        primary = raw_body
    current, quoted = split_quoted_history(primary)
    if not current and quoted:
        current = quoted
        quoted = ""
    body, sig = split_signature(current)
    return NormalizedEmail(
        schema_version=NORMALIZED_EMAIL_VERSION,
        message_id=message_id,
        subject=subject or "",
        from_raw=sender or "",
        from_email=extract_sender_email(sender),
        from_domain=extract_sender_domain(sender),
        to_raw=to or "",
        plain_text=plain,
        html_text=html_text,
        body_text=body,
        quoted_history=quoted,
        signature=sig,
        is_html_only=is_html and not plain.strip(),
        is_forwarded=_looks_forwarded(subject, primary),
        body_sha256=hashlib.sha256(body.encode("utf-8", errors="ignore")).hexdigest(),
        raw_size_bytes=len(raw_body.encode("utf-8", errors="ignore")),
    )
