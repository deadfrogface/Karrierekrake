"""Model catalog + download manager (checksum, resumable, atomic, disk check).

One active local model serves CV extraction and writing. Setup adds pinned
device-dependent choices; Phi-4-mini remains a historical benchmark only.
"""

from __future__ import annotations

import json
import errno
import http.client
import os
import re
import shutil
import socket
import ssl
import tempfile
import time
import urllib.error
import urllib.request
import urllib.parse

import certifi
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from core.security.model_integrity import (
    ModelIntegrityError,
    require_sha256,
    sha256_file,
    verify_file_sha256,
)
from guenther.privacy import log_event

DOWNLOAD_TIMEOUT = 60
# Budget of failed attempts WITHOUT saved progress. An attempt that grew the
# .part past its previous best by at least DOWNLOAD_MIN_PROGRESS_BYTES after a
# valid response (206 with matching Content-Range, or 200 written from byte 0)
# does not consume it, so a flaky line can still finish a large model.
DOWNLOAD_ATTEMPTS = 3
# Hard cap on all attempts together, progress or not (estimate, not measured).
DOWNLOAD_MAX_TOTAL_ATTEMPTS = 20
# Minimum newly saved bytes for an attempt to count as progress (estimate).
DOWNLOAD_MIN_PROGRESS_BYTES = 1024 * 1024
DOWNLOAD_RETRY_DELAY = 1.0
# Backoff grows linearly with the attempt number up to this many delays (estimate).
DOWNLOAD_RETRY_DELAY_MAX_STEPS = 10
# An unusable resume answer (416, 200, wrong Content-Range) restarts from byte
# zero at most this many times per install before failing with a fixed code.
DOWNLOAD_RESTARTS = 1


def download_ssl_context() -> ssl.SSLContext:
    """Trust OS roots (including Windows enterprise roots) plus bundled public CAs."""
    context = ssl.create_default_context()
    context.load_verify_locations(cafile=certifi.where())
    return context


def download_diagnostic(exc: Exception, url: str) -> str:
    """Preserve useful TLS metadata without signed URLs, paths or credentials."""
    reason = exc.reason if isinstance(exc, urllib.error.URLError) else exc
    fields = [f"host={urllib.parse.urlsplit(url).hostname}",
              f"exception={type(reason).__name__}"]
    for key in ("library", "reason", "verify_code"):
        value = str(getattr(reason, key, ""))
        if re.fullmatch(r"[A-Za-z0-9_]+", value):
            fields.append(f"{key}={value}")
    return " ".join(fields)


class DownloadInterruptedError(ConnectionError):
    """The stream broke after response headers and body bytes had arrived.

    Raised by the read loop only, so a bare ``SSLEOFError`` during the
    handshake keeps meaning ``tls_failed``. The original error is kept as
    ``__cause__`` for diagnostics.
    """


# Exception names used by requests/urllib3 for a body that ended early; matched
# by name so this module does not need to import either library.
_BODY_INTERRUPTION_NAMES = {"ChunkedEncodingError", "ProtocolError", "IncompleteRead"}


def _exception_chain(exc: BaseException) -> list[BaseException]:
    """Return exc plus everything it wraps (cause, context, URLError.reason, args)."""
    seen: set[int] = set()
    todo: list[BaseException] = [exc]
    out: list[BaseException] = []
    while todo:
        cur = todo.pop(0)
        if id(cur) in seen:
            continue
        seen.add(id(cur))
        out.append(cur)
        linked = [cur.__cause__, cur.__context__]
        if isinstance(cur, urllib.error.URLError):
            linked.append(cur.reason)
        linked.extend(getattr(cur, "args", ()) or ())
        todo.extend(item for item in linked if isinstance(item, BaseException))
    return out


def _is_certificate_error(exc: BaseException) -> bool:
    return any(isinstance(item, ssl.SSLCertVerificationError) for item in _exception_chain(exc))


def _is_tls_eof(exc: BaseException) -> bool:
    """True for a TLS EOF / "unexpected eof" anywhere in the chain, never for certificate errors."""
    chain = _exception_chain(exc)
    if any(isinstance(item, ssl.SSLCertVerificationError) for item in chain):
        return False
    for item in chain:
        if isinstance(item, ssl.SSLEOFError):
            return True
        if isinstance(item, ssl.SSLError):
            text = f"{getattr(item, 'reason', '')} {item}".lower()
            if "unexpected eof" in text or "unexpected_eof" in text or "eof occurred" in text:
                return True
    return False


def _is_body_interruption(exc: BaseException) -> bool:
    """True for an EOF/reset of an established stream, never for certificate errors."""
    chain = _exception_chain(exc)
    if any(isinstance(item, ssl.SSLCertVerificationError) for item in chain):
        return False
    for item in chain:
        if isinstance(item, (ssl.SSLEOFError, ssl.SSLZeroReturnError, http.client.IncompleteRead,
                             ConnectionResetError, ConnectionAbortedError, BrokenPipeError)):
            return True
        if isinstance(item, ssl.SSLError):
            text = f"{getattr(item, 'reason', '')} {item}".lower()
            if "unexpected eof" in text or "unexpected_eof" in text or "eof occurred" in text:
                return True
        if type(item).__name__ in _BODY_INTERRUPTION_NAMES:
            return True
    return False


def download_failure_code(exc: Exception) -> str:
    """Expose only a fixed diagnostic code, never paths or signed URLs."""
    if isinstance(exc, urllib.error.HTTPError):
        return f"http_{exc.code}"
    if any(isinstance(item, DownloadInterruptedError) for item in _exception_chain(exc)):
        return "connection_interrupted"
    reason = exc.reason if isinstance(exc, urllib.error.URLError) else exc
    if isinstance(reason, ssl.SSLError):
        return "tls_failed"
    if isinstance(reason, TimeoutError):
        return "connection_timeout"
    if isinstance(reason, socket.gaierror):
        return "dns_failed"
    if isinstance(reason, PermissionError):
        return "write_permission_denied"
    if isinstance(reason, OSError) and reason.errno == errno.ENOSPC:
        return "insufficient_disk"
    if isinstance(reason, (http.client.IncompleteRead, ConnectionError)):
        return "connection_interrupted"
    if isinstance(exc, ValueError) and str(exc) in {"invalid_download_range", "download_size_mismatch"}:
        return str(exc)
    if isinstance(exc, ValueError):
        return "invalid_download_response"
    return "download_failed"


def _retryable_download_error(exc: Exception) -> bool:
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code in {408, 429, 500, 502, 503, 504}
    # Certificate/handshake problems are never retried and never downgraded.
    if _is_certificate_error(exc):
        return False
    if any(isinstance(item, DownloadInterruptedError) for item in _exception_chain(exc)):
        return True
    reason = exc.reason if isinstance(exc, urllib.error.URLError) else exc
    return (not isinstance(reason, ssl.SSLError)
            and isinstance(reason, (TimeoutError, ConnectionError,
                                    socket.gaierror, http.client.IncompleteRead)))


def _discard_part(part_path: Path) -> None:
    """Empty the .part at a restart decision so no later retry resumes from it."""
    with part_path.open("wb"):
        pass


def _final_host(response, url: str) -> str:
    """Host after redirects; never the signed path or query string."""
    geturl = getattr(response, "geturl", None)
    final = geturl() if callable(geturl) else url
    return str(urllib.parse.urlsplit(str(final or url)).hostname or "")


def _resume_problem(status: int, content_range: str, existing: int,
                    expected_total: int | None) -> tuple[str | None, int | None]:
    """Validate a (possibly resumed) response; return (error_code, total_bytes).

    Appending is only safe for 206 whose Content-Range starts exactly at the
    saved byte count, runs to the end, and (when the catalog pins the exact
    size) reports that size. 200 means a complete body from byte zero.
    """
    if status == 200:
        return None, None
    if status != 206:
        return "invalid_download_response", None
    match = re.fullmatch(r"bytes ([0-9]+)-([0-9]+)/([0-9]+)", content_range or "")
    if not match:
        return "invalid_download_range", None
    start_byte, end_byte, total_bytes = map(int, match.groups())
    if (start_byte != existing or not start_byte <= end_byte < total_bytes
            or end_byte != total_bytes - 1
            or (expected_total is not None and total_bytes != expected_total)):
        return "invalid_download_range", None
    return None, total_bytes

# Legacy default; setup selection takes precedence for both runtime paths.
PRODUCTION_MODEL_ID = "qwen3.5-4b"

# No weights in git — catalog metadata only.
MODEL_CATALOG: dict[str, dict] = {
    PRODUCTION_MODEL_ID: {
        "display_name": "Karrierekrake lokal (Qwen3.5-4B)",
        "license": "Apache-2.0",
        "approx_bytes": 2_741_000_000,
        "ram_gb_min": 5.0,
        "tier": "standard",
        "filename": "Qwen3.5-4B-Q4_K_M.gguf",
        # Official Qwen/Qwen3.5-4B-GGUF resolve often returns 401 unauthenticated.
        # Unsloth mirror is public and pins the same LFS oid / SHA-256.
        "url": (
            "https://huggingface.co/unsloth/Qwen3.5-4B-GGUF/resolve/main/"
            "Qwen3.5-4B-Q4_K_M.gguf"
        ),
        "sha256": "00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4",
        "source_repo": "unsloth/Qwen3.5-4B-GGUF",
        "base_model": "Qwen/Qwen3.5-4B",
        "upstream_license": "Apache-2.0",
        "quant": "Q4_K_M",
        "notes": (
            "SOLE production model for CV extract + Anschreiben (one-model dual-use). "
            "No second local weight. No DET. No cloud. "
            "Weights mirrored from Qwen3.5-4B-GGUF (same SHA-256)."
        ),
        "role": "primary",
        "deferred": False,
        "production": True,
    },
}

# Historical / benchmark-only — NOT production runtime. Not installable via ModelManager.
HISTORICAL_MODEL_CATALOG: dict[str, dict] = {
    "phi4-mini": {
        "display_name": "Phi-4-mini (historical — not production)",
        "license": "MIT",
        "approx_bytes": 2_491_874_688,
        "ram_gb_min": 5.0,
        "tier": "standard",
        "filename": "microsoft_Phi-4-mini-instruct-Q4_K_M.gguf",
        "url": (
            "https://huggingface.co/bartowski/microsoft_Phi-4-mini-instruct-GGUF/resolve/main/"
            "microsoft_Phi-4-mini-instruct-Q4_K_M.gguf"
        ),
        "sha256": "01999f17c39cc3074afae5e9c539bc82d45f2dd7faa3917c66cbef76fce8c0c2",
        "source_repo": "bartowski/microsoft_Phi-4-mini-instruct-GGUF",
        "base_model": "microsoft/Phi-4-mini-instruct",
        "notes": "HISTORICAL writing/extract bakeoff only — superseded by qwen3.5-4b dual-use",
        "role": "historical",
        "production": False,
    },
    "qwen3-1.7b": {
        "display_name": "Qwen3 1.7B (historical — not production)",
        "license": "Apache-2.0",
        "approx_bytes": 1_282_439_584,
        "ram_gb_min": 3.0,
        "tier": "light",
        "filename": "Qwen_Qwen3-1.7B-Q4_K_M.gguf",
        "url": (
            "https://huggingface.co/bartowski/Qwen_Qwen3-1.7B-GGUF/resolve/main/"
            "Qwen_Qwen3-1.7B-Q4_K_M.gguf"
        ),
        "sha256": "72c5c3cb38fa32d5256e2fe30d03e7a64c6c79e668ad84057e3bd66e250b24fb",
        "source_repo": "bartowski/Qwen_Qwen3-1.7B-GGUF",
        "base_model": "Qwen/Qwen3-1.7B",
        "hf_commit": "dcb19155b962dbb6389f4691a982043a8e651022",
        "notes": "HISTORICAL only",
        "role": "historical",
        "production": False,
    },
    "qwen3-4b": {
        "display_name": "Qwen3 4B (historical — not production)",
        "license": "Apache-2.0",
        "approx_bytes": 2_497_280_256,
        "ram_gb_min": 5.0,
        "tier": "standard",
        "filename": "Qwen3-4B-Q4_K_M.gguf",
        "url": (
            "https://huggingface.co/Qwen/Qwen3-4B-GGUF/resolve/main/"
            "Qwen3-4B-Q4_K_M.gguf"
        ),
        "sha256": "7485fe6f11af29433bc51cab58009521f205840f5b4ae3a32fa7f92e8534fdf5",
        "source_repo": "Qwen/Qwen3-4B-GGUF",
        "base_model": "Qwen/Qwen3-4B",
        "notes": "HISTORICAL only — different from Qwen3.5-4B production",
        "role": "historical",
        "production": False,
    },
}


def is_production_model(model_id: str) -> bool:
    from guenther.setup_models import SETUP_MODEL_CATALOG
    return model_id == PRODUCTION_MODEL_ID or model_id in SETUP_MODEL_CATALOG


def installable_catalog() -> dict[str, dict]:
    from guenther.setup_models import SETUP_MODEL_CATALOG
    return {**MODEL_CATALOG, **SETUP_MODEL_CATALOG}


@dataclass
class DownloadProgress:
    model_id: str
    bytes_done: int = 0
    bytes_total: int = 0
    status: str = "idle"  # idle|checking|downloading|verifying|done|error|cancelled
    message: str = ""
    diagnostic: str = ""


@dataclass
class ModelManager:
    models_dir: Path
    catalog: dict[str, dict] = field(default_factory=installable_catalog)

    def __post_init__(self) -> None:
        self.models_dir = Path(self.models_dir)
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self._state_path = self.models_dir / "installed.json"

    def list_catalog(self) -> list[dict]:
        out = []
        for mid, meta in self.catalog.items():
            row = {"id": mid, **meta, "installed": self.is_installed(mid)}
            out.append(row)
        return out

    def model_path(self, model_id: str) -> Path:
        meta = self.catalog[model_id]
        return self.models_dir / model_id / meta["filename"]

    def is_installed(self, model_id: str) -> bool:
        if model_id not in self.catalog:
            return False
        path = self.model_path(model_id)
        if path.is_symlink() or path.parent.is_symlink():
            return False
        if not (path.is_file() and path.stat().st_size > 1_000_000):
            return False
        # Catalog must declare a SHA-256; empty digest ⇒ not considered installed.
        try:
            require_sha256(str(self.catalog[model_id].get("sha256") or ""))
        except ModelIntegrityError:
            return False
        return True

    def assert_model_integrity(self, model_id: str) -> str:
        """Verify on-disk model matches catalog SHA-256 (fail closed)."""
        meta = self.catalog.get(model_id)
        if not meta:
            raise ModelIntegrityError("unknown_model")
        path = self.model_path(model_id)
        if path.is_symlink() or path.parent.is_symlink() or not path.is_file():
            raise ModelIntegrityError("model_missing")
        return verify_file_sha256(path, str(meta.get("sha256") or ""))

    def disk_free_bytes(self) -> int:
        usage = shutil.disk_usage(self.models_dir)
        return int(usage.free)

    def can_install(self, model_id: str) -> tuple[bool, str]:
        if model_id in HISTORICAL_MODEL_CATALOG and model_id not in self.catalog:
            return False, "historical_model_forbidden"
        meta = self.catalog.get(model_id)
        if not meta:
            return False, "unknown_model"
        if not is_production_model(model_id):
            return False, "not_a_production_model"
        # A resumed download only needs room for its missing bytes. Requiring
        # the entire model size again makes a nearly complete .part unusable.
        expected = int(meta.get("approx_bytes") or 0)
        partial = self.model_path(model_id).with_suffix(
            self.model_path(model_id).suffix + ".part"
        )
        # Never trust a symlinked partial file or a symlinked model directory.
        if partial.is_symlink() or partial.parent.is_symlink():
            return False, "invalid_download_response"
        saved = partial.stat().st_size if partial.is_file() else 0
        if saved > expected:
            saved = 0  # A stale/oversized partial cannot be trusted.
        need = max(0, expected - saved) + 500_000_000
        free = self.disk_free_bytes()
        if free < need:
            return False, "insufficient_disk"
        return True, "ok"

    def _load_state(self) -> dict:
        if not self._state_path.is_file():
            return {}
        try:
            return json.loads(self._state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def _save_state(self, state: dict) -> None:
        tmp = self._state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self._state_path)

    def uninstall(self, model_id: str) -> bool:
        root = self.models_dir / model_id
        if root.exists():
            shutil.rmtree(root, ignore_errors=True)
        state = self._load_state()
        state.pop(model_id, None)
        self._save_state(state)
        log_event("model_uninstalled", model_id=model_id)
        return True

    def verify_checksum(self, path: Path, expected_sha256: str) -> bool:
        """Require a real SHA-256; empty digest is a hard fail (no silent skip)."""
        try:
            require_sha256(expected_sha256)
            return sha256_file(path) == expected_sha256.strip().lower()
        except ModelIntegrityError:
            return False

    def install(
        self,
        model_id: str,
        *,
        progress_cb: Callable[[DownloadProgress], None] | None = None,
        cancel_check: Callable[[], bool] | None = None,
        allow_download: bool = False,
    ) -> DownloadProgress:
        """Download only when allow_download=True and URL configured — never silent."""
        prog = DownloadProgress(model_id=model_id, status="checking")
        meta = self.catalog.get(model_id)
        if not meta:
            prog.status = "error"
            prog.message = "unknown_model"
            return prog
        ok, reason = self.can_install(model_id)
        if not ok:
            prog.status = "error"
            prog.message = reason
            return prog
        if not allow_download:
            prog.status = "error"
            prog.message = "download_not_confirmed"
            return prog
        url = str(meta.get("url") or "")
        if not url:
            prog.status = "error"
            prog.message = "url_not_configured"
            log_event("model_install_blocked", model_id=model_id, reason="no_url")
            return prog

        dest_dir = self.models_dir / model_id
        dest_dir.mkdir(parents=True, exist_ok=True)
        final_path = self.model_path(model_id)
        if dest_dir.is_symlink() or final_path.is_symlink():
            prog.status, prog.message = "error", "invalid_download_response"
            return prog
        part_path = final_path.with_suffix(final_path.suffix + ".part")
        if part_path.is_symlink():
            prog.status, prog.message = "error", "invalid_download_response"
            return prog

        prog.status = "downloading"
        prog.bytes_total = int(meta.get("approx_bytes") or 0)
        if progress_cb:
            progress_cb(prog)

        context = download_ssl_context()
        restarts_left = DOWNLOAD_RESTARTS
        # Setup entries pin the exact LFS size; legacy entries only approximate it.
        expected_total = int(meta.get("approx_bytes") or 0) if meta.get("size_exact") else None
        attempt = -1
        unproductive = 0  # failed attempts without saved progress (budget)
        best_part = part_path.stat().st_size if part_path.is_file() else 0
        while True:
            attempt += 1
            valid_response = False
            if cancel_check and cancel_check():
                prog.status, prog.message = "cancelled", "cancelled"
                return prog
            try:
                existing = part_path.stat().st_size if part_path.is_file() else 0
                # Bytes kept from earlier attempts; a TLS EOF before this attempt's
                # first body byte is only an interruption while these exist.
                saved_before = existing
                response = None
                while response is None:
                    req = urllib.request.Request(url, headers={"User-Agent": "Karrierekrake-Guenther/1.0"})
                    if existing:
                        req.add_header("Range", f"bytes={existing}-")
                    # Evidence for resume diagnostics: host and offset only, no URL path/query.
                    log_event("model_download_request", model_id=model_id, attempt=attempt + 1,
                              host=urllib.parse.urlsplit(url).hostname,
                              range=req.get_header("Range") or "", part_bytes=existing)
                    try:
                        response = urllib.request.urlopen(req, timeout=DOWNLOAD_TIMEOUT, context=context)
                    except urllib.error.HTTPError as exc:
                        # A complete/stale partial file may be outside the server's range.
                        if not existing or exc.code != 416 or restarts_left <= 0:
                            raise
                        exc.close()
                        restarts_left -= 1
                        existing = 0
                        # Drop the stale bytes now: if the restarted request fails
                        # before writing, the retry must start at 0 without Range.
                        _discard_part(part_path)
                        log_event("model_download_restart", model_id=model_id, reason="http_416")
                        continue
                    except (urllib.error.URLError, OSError) as exc:
                        # TLS EOF before this attempt's first body byte: an interruption
                        # only if earlier attempts already saved bytes in the .part.
                        if saved_before > 0 and _is_tls_eof(exc):
                            raise DownloadInterruptedError("connection_interrupted") from exc
                        raise
                    log_event("model_download_response", model_id=model_id, attempt=attempt + 1,
                              status=response.status, final_host=_final_host(response, url),
                              content_range=response.headers.get("Content-Range", "") or "",
                              content_length=response.headers.get("Content-Length", "") or "",
                              part_bytes=existing)
                    problem, total_bytes = _resume_problem(
                        response.status, response.headers.get("Content-Range", ""),
                        existing, expected_total)
                    if problem:
                        response.close()
                        response = None
                        if not existing or restarts_left <= 0:
                            raise ValueError(problem)
                        # Never append to an unverifiable offset: restart at byte zero.
                        restarts_left -= 1
                        existing = 0
                        _discard_part(part_path)  # retries after this start at 0, no Range
                        log_event("model_download_restart", model_id=model_id, reason=problem)
                with response as resp:
                    valid_response = True
                    status = resp.status
                    if status == 206:
                        prog.bytes_total = total_bytes
                    else:
                        # Ignoring Range means a full file: truncate, never append.
                        existing = 0
                        total = resp.headers.get("Content-Length")
                        # A pinned size must be announced exactly before anything is written.
                        if expected_total is not None and total != str(expected_total):
                            raise ValueError("download_size_mismatch")
                        if total:
                            prog.bytes_total = int(total)
                    prog.bytes_done = existing
                    received = 0
                    with part_path.open("ab" if existing else "wb") as out:
                        while True:
                            if cancel_check and cancel_check():
                                prog.status = "cancelled"
                                prog.message = "cancelled"
                                return prog
                            try:
                                chunk = resp.read(1024 * 1024)
                            except Exception as exc:
                                # TLS "unexpected eof", resets and short reads after
                                # body bytes arrived are a dropped stream, not a TLS
                                # policy failure: keep the .part and resume.
                                if received and _is_body_interruption(exc):
                                    raise DownloadInterruptedError("connection_interrupted") from exc
                                # Before this attempt's first body byte only a TLS EOF
                                # counts, and only while the .part keeps earlier bytes.
                                if (received or saved_before > 0) and _is_tls_eof(exc):
                                    raise DownloadInterruptedError("connection_interrupted") from exc
                                raise
                            if not chunk:
                                if prog.bytes_done < prog.bytes_total:
                                    raise http.client.IncompleteRead(b"", prog.bytes_total - prog.bytes_done)
                                break
                            # Never write past the pinned size (200 and 206 alike).
                            if (expected_total is not None
                                    and prog.bytes_done + len(chunk) > expected_total):
                                raise ValueError("download_size_mismatch")
                            out.write(chunk)
                            received += len(chunk)
                            prog.bytes_done += len(chunk)
                            if progress_cb:
                                progress_cb(prog)
                break
            except (urllib.error.URLError, OSError, ValueError, http.client.HTTPException) as exc:
                code = download_failure_code(exc)
                if code == "download_size_mismatch":
                    part_path.unlink(missing_ok=True)  # oversized/unknown-size data is never resumed
                part_bytes = part_path.stat().st_size if part_path.is_file() else 0
                # Progress only counts when saved (flushed .part) past the best
                # size so far after a valid response; a restart from 0 that does
                # not overtake the earlier .part is no progress.
                progressed = (valid_response
                              and part_bytes >= best_part + DOWNLOAD_MIN_PROGRESS_BYTES)
                best_part = max(best_part, part_bytes)  # never lowered by a restart
                counted = not progressed
                if counted:
                    unproductive += 1
                if (_retryable_download_error(exc)
                        and unproductive < DOWNLOAD_ATTEMPTS
                        and attempt + 1 < DOWNLOAD_MAX_TOTAL_ATTEMPTS):
                    log_event("model_download_retry", model_id=model_id, reason=code,
                              attempt=attempt + 1, bytes_saved=prog.bytes_done,
                              part_bytes=part_bytes, counted=counted,
                              unproductive=unproductive, budget=DOWNLOAD_ATTEMPTS,
                              max_attempts=DOWNLOAD_MAX_TOTAL_ATTEMPTS)
                    prog.status, prog.message = "retrying", code
                    if progress_cb:
                        progress_cb(prog)
                    # Cancellable backoff; the next request resumes from the .part file.
                    deadline = time.monotonic() + DOWNLOAD_RETRY_DELAY * min(
                        attempt + 1, DOWNLOAD_RETRY_DELAY_MAX_STEPS)
                    while time.monotonic() < deadline:
                        if cancel_check and cancel_check():
                            prog.status, prog.message = "cancelled", "cancelled"
                            return prog
                        time.sleep(min(.1, max(0, deadline - time.monotonic())))
                    prog.status, prog.message = "downloading", ""
                    continue
                prog.status, prog.message = "error", code
                prog.diagnostic = download_diagnostic(exc, url)
                log_event("model_download_failed", model_id=model_id, reason=code,
                          diagnostic=prog.diagnostic, attempt=attempt + 1, counted=counted,
                          unproductive=unproductive, budget=DOWNLOAD_ATTEMPTS,
                          max_attempts=DOWNLOAD_MAX_TOTAL_ATTEMPTS)
                return prog

        prog.status = "verifying"
        if progress_cb:
            progress_cb(prog)
        # Hash the complete .part from disk (resumed prefix included), never
        # only the bytes received by the last attempt.
        expected_sha256 = str(meta.get("sha256") or "").strip().lower()
        try:
            require_sha256(expected_sha256)
            computed_sha256 = sha256_file(part_path)
        except ModelIntegrityError:
            computed_sha256 = ""
        if not computed_sha256 or computed_sha256 != expected_sha256:
            prog.status = "error"
            prog.message = "checksum_mismatch"
            part_path.unlink(missing_ok=True)
            return prog
        # Log the digest actually computed over the full file next to the catalog value.
        log_event("model_download_verified", model_id=model_id, size=part_path.stat().st_size,
                  expected_size=expected_total if expected_total is not None else "",
                  sha256=computed_sha256, expected_sha256=expected_sha256)

        # Atomic replace
        tmp_final = final_path.with_suffix(".tmp")
        part_path.replace(tmp_final)
        tmp_final.replace(final_path)
        state = self._load_state()
        state[model_id] = {
            "path": str(final_path),
            "license": meta.get("license"),
            "filename": meta.get("filename"),
        }
        self._save_state(state)
        prog.status = "done"
        prog.message = "installed"
        log_event("model_installed", model_id=model_id)
        if progress_cb:
            progress_cb(prog)
        return prog


def default_models_dir() -> Path:
    """Resolve AppData models dir without importing desktop at module import time."""
    override = os.environ.get("KARRIEREKRAKE_MODELS_DIR")
    if override:
        return Path(override)
    try:
        from desktop.paths import ensure_app_dirs

        dirs = ensure_app_dirs()
        path = dirs["root"] / "models"
        path.mkdir(parents=True, exist_ok=True)
        return path
    except Exception:
        path = Path(tempfile.gettempdir()) / "Karrierekrake" / "models"
        path.mkdir(parents=True, exist_ok=True)
        return path
