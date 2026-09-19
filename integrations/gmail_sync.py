"""Gmail sync helpers — list/get/parse adapted from ejobtrack gmail.ts (Apache-2.0).

Adds resumable incremental sync via users.history.list (Gmail historyId).
Production Google compliance verification = PR43.

Never log mail bodies, subjects with PII dumps, or OAuth tokens.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from integrations.email_normalize import (
    extract_from_gmail_parts,
    normalize_email_text,
)

logger = logging.getLogger("karrierekrake.gmail")

CURSOR_SCHEMA_VERSION = 1
CURSOR_META_KEY = "gmail_sync_cursor_v1"
DEFAULT_SYNC_QUERY = (
    "newer_than:90d (bewerbung OR application OR interview OR absage OR offer)"
)


@dataclass
class ParsedEmail:
    id: str
    thread_id: str = ""
    subject: str = ""
    sender: str = ""
    snippet: str = ""
    body_text: str = ""
    internal_date: str = ""
    label_ids: list[str] = field(default_factory=list)


@dataclass
class SyncCursor:
    schema_version: int = CURSOR_SCHEMA_VERSION
    history_id: str = ""
    account_key: str = "default"
    resume_page_token: str = ""
    sync_mode: str = ""
    last_error: str = ""
    pending_message_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": int(self.schema_version),
            "history_id": self.history_id or "",
            "account_key": self.account_key or "default",
            "resume_page_token": self.resume_page_token or "",
            "sync_mode": self.sync_mode or "",
            "last_error": self.last_error or "",
            "pending_message_ids": list(self.pending_message_ids or []),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> SyncCursor:
        if not data:
            return cls()
        return cls(
            schema_version=int(data.get("schema_version") or CURSOR_SCHEMA_VERSION),
            history_id=str(data.get("history_id") or ""),
            account_key=str(data.get("account_key") or "default"),
            resume_page_token=str(data.get("resume_page_token") or ""),
            sync_mode=str(data.get("sync_mode") or ""),
            last_error=str(data.get("last_error") or ""),
            pending_message_ids=[
                str(x) for x in (data.get("pending_message_ids") or []) if x
            ],
        )


@dataclass
class SyncResult:
    mode: str
    fetched: int = 0
    processed: int = 0
    skipped_duplicates: int = 0
    new_history_id: str = ""
    resumed: bool = False
    partial: bool = False
    errors: list[str] = field(default_factory=list)
    needs_reauth: bool = False


class CursorStore(Protocol):
    def load(self) -> SyncCursor: ...

    def save(self, cursor: SyncCursor) -> None: ...


class DatabaseCursorStore:
    """Versioned Gmail sync cursor in app_meta (no mail wipe on migration)."""

    def __init__(self, db: Any, *, meta_key: str = CURSOR_META_KEY):
        self._db = db
        self._meta_key = meta_key

    def load(self) -> SyncCursor:
        raw = self._db.get_meta(self._meta_key)
        if not raw:
            return SyncCursor()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Gmail sync cursor corrupt — starting fresh cursor")
            return SyncCursor()
        if not isinstance(data, dict):
            return SyncCursor()
        cursor = SyncCursor.from_dict(data)
        if cursor.schema_version != CURSOR_SCHEMA_VERSION:
            logger.info(
                "Gmail cursor schema %s incompatible with %s — full sync",
                cursor.schema_version,
                CURSOR_SCHEMA_VERSION,
            )
            return SyncCursor(
                schema_version=CURSOR_SCHEMA_VERSION,
                account_key=cursor.account_key,
                history_id="",
                sync_mode="full",
            )
        return cursor

    def save(self, cursor: SyncCursor) -> None:
        payload = cursor.to_dict()
        payload["schema_version"] = CURSOR_SCHEMA_VERSION
        self._db.set_meta(self._meta_key, json.dumps(payload, ensure_ascii=False))


def _header(headers: list[dict[str, str]], name: str) -> str:
    target = name.lower()
    for h in headers or []:
        if (h.get("name") or "").lower() == target:
            return h.get("value") or ""
    return ""


def parse_message(msg: dict[str, Any]) -> ParsedEmail:
    payload = msg.get("payload") or {}
    headers = payload.get("headers") or []
    subject = _header(headers, "Subject")
    sender = _header(headers, "From")
    body_html_or_text = ""
    if payload.get("parts"):
        body_html_or_text = extract_from_gmail_parts(payload["parts"])
    else:
        data = (payload.get("body") or {}).get("data")
        if data:
            from integrations.email_normalize import decode_gmail_body_data

            body_html_or_text = decode_gmail_body_data(data)
    body_text = normalize_email_text(subject, body_html_or_text)
    if not body_text and msg.get("snippet"):
        body_text = str(msg.get("snippet") or "")
    return ParsedEmail(
        id=str(msg.get("id") or ""),
        thread_id=str(msg.get("threadId") or ""),
        subject=subject,
        sender=sender,
        snippet=str(msg.get("snippet") or ""),
        body_text=body_text,
        internal_date=str(msg.get("internalDate") or ""),
        label_ids=list(msg.get("labelIds") or []),
    )


def is_transient_error(exc: BaseException) -> bool:
    if isinstance(exc, (ConnectionError, TimeoutError, OSError)):
        return True
    status = _http_status(exc)
    return status in {408, 429, 500, 502, 503, 504}


def is_history_invalid_error(exc: BaseException) -> bool:
    return _http_status(exc) == 404


def _http_status(exc: BaseException) -> int | None:
    resp = getattr(exc, "resp", None)
    if resp is not None:
        try:
            return int(getattr(resp, "status", None) or 0) or None
        except (TypeError, ValueError):
            return None
    text = str(exc)
    if "404" in text:
        return 404
    if "429" in text:
        return 429
    return None


def _call_with_retry(
    fn: Callable[[], Any],
    *,
    attempts: int = 5,
    wait_seconds: float = 0.5,
    on_error: Callable[[Exception], None] | None = None,
) -> Any:
    """Retry transient Gmail/API errors (tenacity when available)."""
    try:
        from tenacity import (
            retry,
            retry_if_exception,
            stop_after_attempt,
            wait_exponential,
            wait_none,
        )

        wait = (
            wait_none()
            if not wait_seconds
            else wait_exponential(
                multiplier=wait_seconds,
                min=wait_seconds,
                max=max(wait_seconds * 8, wait_seconds),
            )
        )

        @retry(
            reraise=True,
            stop=stop_after_attempt(max(1, attempts)),
            wait=wait,
            retry=retry_if_exception(is_transient_error),
            before_sleep=lambda rs: logger.info(
                "Gmail transient error %s — retry",
                type(rs.outcome.exception()).__name__
                if rs.outcome and rs.outcome.failed
                else "error",
            ),
        )
        def _inner():
            return fn()

        try:
            return _inner()
        except Exception as exc:
            if on_error:
                on_error(exc)
            raise
    except ImportError:
        last: Exception | None = None
        for i in range(max(1, attempts)):
            try:
                return fn()
            except Exception as exc:
                last = exc
                if not is_transient_error(exc) or i >= attempts - 1:
                    if on_error:
                        on_error(exc)
                    raise
                sleep_for = wait_seconds * (2**i) if wait_seconds else 0
                logger.info(
                    "Gmail transient error %s — retry %s/%s",
                    type(exc).__name__,
                    i + 1,
                    attempts,
                )
                if sleep_for:
                    time.sleep(sleep_for)
        assert last is not None
        raise last


def list_message_ids(
    service,
    *,
    query: str = "newer_than:90d",
    max_results: int = 50,
    page_token: str | None = None,
) -> tuple[list[str], str | None]:
    kwargs: dict[str, Any] = {
        "userId": "me",
        "q": query,
        "maxResults": max_results,
    }
    if page_token:
        kwargs["pageToken"] = page_token

    def _execute():
        return service.users().messages().list(**kwargs).execute()

    resp = _call_with_retry(_execute, attempts=1)
    ids = [m["id"] for m in (resp.get("messages") or []) if m.get("id")]
    return ids, resp.get("nextPageToken")


def get_message(service, message_id: str) -> dict[str, Any]:
    return (
        service.users()
        .messages()
        .get(userId="me", id=message_id, format="full")
        .execute()
    )


def get_profile_history_id(service) -> str:
    profile = service.users().getProfile(userId="me").execute()
    return str(profile.get("historyId") or "")


def list_history_page(
    service,
    *,
    start_history_id: str,
    page_token: str | None = None,
    max_results: int = 100,
) -> tuple[list[dict[str, Any]], str | None, str]:
    kwargs: dict[str, Any] = {
        "userId": "me",
        "startHistoryId": start_history_id,
        "historyTypes": ["messageAdded"],
        "maxResults": max_results,
    }
    if page_token:
        kwargs["pageToken"] = page_token
    resp = service.users().history().list(**kwargs).execute()
    records = list(resp.get("history") or [])
    return records, resp.get("nextPageToken"), str(resp.get("historyId") or start_history_id)


def extract_history_message_ids(history_records: list[dict[str, Any]]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for record in history_records or []:
        for added in record.get("messagesAdded") or []:
            msg = added.get("message") or {}
            mid = msg.get("id")
            if not mid or mid in seen:
                continue
            seen.add(mid)
            ordered.append(str(mid))
    return ordered


def sync_recent(
    service,
    *,
    query: str = DEFAULT_SYNC_QUERY,
    max_results: int = 40,
    on_error: Callable[[Exception], None] | None = None,
) -> list[ParsedEmail]:
    """Fetch and parse recent messages. No classification here."""
    out: list[ParsedEmail] = []
    try:
        ids, _ = list_message_ids(service, query=query, max_results=max_results)
    except Exception as exc:
        if on_error:
            on_error(exc)
        else:
            logger.warning("Gmail list failed: %s", type(exc).__name__)
        return out
    for mid in ids:
        try:
            raw = get_message(service, mid)
            out.append(parse_message(raw))
        except Exception as exc:
            if on_error:
                on_error(exc)
            else:
                logger.warning("Gmail get failed for %s: %s", mid, type(exc).__name__)
    return out


def sender_is_excluded(sender: str, excluded: list[str]) -> bool:
    """CareerSync shouldExcludeEmail adapted (MIT)."""
    from integrations.email_normalize import extract_sender_email

    if not excluded:
        return False
    email = extract_sender_email(sender).lower()
    for rule in excluded:
        r = (rule or "").lower().strip()
        if not r:
            continue
        if email == r:
            return True
        if r.startswith("*@"):
            if email.endswith("@" + r[2:]):
                return True
        elif r.startswith("@") and email.endswith(r):
            return True
        elif r in email:
            return True
    return False


def _deliver_ids(
    service,
    message_ids: list[str],
    *,
    is_known: Callable[[str], bool],
    on_message: Callable[[ParsedEmail], None] | None,
    result: SyncResult,
    seen_batch: set[str],
) -> list[str]:
    """Fetch+deliver; returns remaining ids not yet processed (for crash resume)."""
    remaining = list(message_ids)
    while remaining:
        mid = remaining[0]
        if mid in seen_batch or is_known(mid):
            result.skipped_duplicates += 1
            remaining.pop(0)
            seen_batch.add(mid)
            continue
        result.fetched += 1
        try:
            raw = _call_with_retry(
                lambda m=mid: get_message(service, m),
                attempts=1,
            )
            parsed = parse_message(raw)
        except Exception as exc:
            result.errors.append(f"get:{type(exc).__name__}")
            logger.warning("Gmail get failed for id=%s: %s", mid, type(exc).__name__)
            remaining.pop(0)
            continue
        if on_message is not None:
            try:
                on_message(parsed)
            except Exception as exc:
                result.errors.append(f"on_message:{type(exc).__name__}")
                logger.warning(
                    "Gmail on_message failed for id=%s: %s", mid, type(exc).__name__
                )
                remaining.pop(0)
                continue
        seen_batch.add(mid)
        result.processed += 1
        remaining.pop(0)
    return remaining


def run_robust_sync(
    service,
    *,
    cursor_store: CursorStore,
    is_known: Callable[[str], bool],
    on_message: Callable[[ParsedEmail], None] | None = None,
    account_key: str = "default",
    query: str = DEFAULT_SYNC_QUERY,
    max_results_per_page: int = 50,
    max_pages: int | None = None,
    retry_attempts: int = 5,
    retry_wait_seconds: float = 0.4,
) -> SyncResult:
    """Initial or incremental sync with pagination, resume, and dedupe.

    Idempotent: known gmail_ids are skipped (no duplicate lifecycle callbacks).
    Invalid historyId → controlled full sync (emails retained).
    """
    cursor = cursor_store.load()
    resumed = bool(cursor.resume_page_token or cursor.pending_message_ids)
    result = SyncResult(mode="initial", resumed=resumed)
    seen_batch: set[str] = set()

    if cursor.history_id and cursor.account_key and cursor.account_key != account_key:
        logger.warning("Gmail account_key mismatch — forcing full sync")
        cursor = SyncCursor(
            schema_version=CURSOR_SCHEMA_VERSION,
            account_key=account_key,
            history_id="",
            sync_mode="full",
        )
        cursor_store.save(cursor)

    if cursor.schema_version != CURSOR_SCHEMA_VERSION:
        cursor = SyncCursor(
            schema_version=CURSOR_SCHEMA_VERSION,
            account_key=account_key,
            history_id="",
            sync_mode="full",
        )

    if cursor.pending_message_ids:
        result.mode = cursor.sync_mode or "initial"
        result.resumed = True
        remaining = _deliver_ids(
            service,
            list(cursor.pending_message_ids),
            is_known=is_known,
            on_message=on_message,
            result=result,
            seen_batch=seen_batch,
        )
        cursor.pending_message_ids = remaining
        if remaining:
            cursor.last_error = "partial_pending"
            cursor_store.save(cursor)
            result.partial = True
            return result
        cursor_store.save(cursor)

    use_incremental = bool(cursor.history_id) and not cursor.resume_page_token

    if use_incremental:
        result.mode = "incremental"
        try:
            page_token: str | None = None
            latest_history = cursor.history_id
            while True:

                def _hist(pt=page_token):
                    return list_history_page(
                        service,
                        start_history_id=cursor.history_id,
                        page_token=pt,
                    )

                try:
                    records, next_token, latest_history = _call_with_retry(
                        _hist,
                        attempts=retry_attempts,
                        wait_seconds=retry_wait_seconds,
                    )
                except Exception as exc:
                    if is_history_invalid_error(exc):
                        logger.info("Gmail historyId invalid — full sync fallback")
                        cursor.history_id = ""
                        cursor.resume_page_token = ""
                        cursor.sync_mode = "full"
                        cursor_store.save(cursor)
                        return _run_full_sync(
                            service,
                            cursor_store=cursor_store,
                            is_known=is_known,
                            on_message=on_message,
                            account_key=account_key,
                            query=query,
                            max_results_per_page=max_results_per_page,
                            max_pages=max_pages,
                            retry_attempts=retry_attempts,
                            retry_wait_seconds=retry_wait_seconds,
                            mode="full_fallback",
                            prior_result=result,
                        )
                    result.errors.append(f"history:{type(exc).__name__}")
                    logger.warning("Gmail history list failed: %s", type(exc).__name__)
                    cursor.last_error = type(exc).__name__
                    cursor_store.save(cursor)
                    return result

                ids = extract_history_message_ids(records)
                remaining = _deliver_ids(
                    service,
                    ids,
                    is_known=is_known,
                    on_message=on_message,
                    result=result,
                    seen_batch=seen_batch,
                )
                if remaining:
                    cursor.pending_message_ids = remaining
                    cursor.sync_mode = "incremental"
                    cursor_store.save(cursor)
                    result.partial = True
                    return result
                if not next_token:
                    break
                page_token = next_token

            cursor.history_id = latest_history or cursor.history_id
            cursor.account_key = account_key
            cursor.resume_page_token = ""
            cursor.pending_message_ids = []
            cursor.sync_mode = "incremental"
            cursor.last_error = ""
            cursor_store.save(cursor)
            result.new_history_id = cursor.history_id
            return result
        except Exception as exc:
            result.errors.append(type(exc).__name__)
            cursor.last_error = type(exc).__name__
            cursor_store.save(cursor)
            return result

    return _run_full_sync(
        service,
        cursor_store=cursor_store,
        is_known=is_known,
        on_message=on_message,
        account_key=account_key,
        query=query,
        max_results_per_page=max_results_per_page,
        max_pages=max_pages,
        retry_attempts=retry_attempts,
        retry_wait_seconds=retry_wait_seconds,
        mode="full" if cursor.sync_mode == "full" else "initial",
        resume_token=cursor.resume_page_token or None,
        prior_result=result if resumed else None,
    )


def _run_full_sync(
    service,
    *,
    cursor_store: CursorStore,
    is_known: Callable[[str], bool],
    on_message: Callable[[ParsedEmail], None] | None,
    account_key: str,
    query: str,
    max_results_per_page: int,
    max_pages: int | None,
    retry_attempts: int,
    retry_wait_seconds: float,
    mode: str,
    resume_token: str | None = None,
    prior_result: SyncResult | None = None,
) -> SyncResult:
    result = prior_result or SyncResult(mode=mode, resumed=bool(resume_token))
    result.mode = mode
    if resume_token:
        result.resumed = True
    seen_batch: set[str] = set()
    page_token: str | None = resume_token
    pages = 0

    while True:
        pages += 1
        try:

            def _list_retry(pt=page_token):
                kwargs: dict[str, Any] = {
                    "userId": "me",
                    "q": query,
                    "maxResults": max_results_per_page,
                }
                if pt:
                    kwargs["pageToken"] = pt
                return service.users().messages().list(**kwargs).execute()

            resp = _call_with_retry(
                _list_retry,
                attempts=retry_attempts,
                wait_seconds=retry_wait_seconds,
            )
            ids = [m["id"] for m in (resp.get("messages") or []) if m.get("id")]
            next_token = resp.get("nextPageToken")
        except Exception as exc:
            result.errors.append(f"list:{type(exc).__name__}")
            logger.warning("Gmail list failed: %s", type(exc).__name__)
            cursor = cursor_store.load()
            cursor.resume_page_token = page_token or ""
            cursor.account_key = account_key
            cursor.sync_mode = mode
            cursor.last_error = type(exc).__name__
            cursor_store.save(cursor)
            return result

        remaining = _deliver_ids(
            service,
            ids,
            is_known=is_known,
            on_message=on_message,
            result=result,
            seen_batch=seen_batch,
        )
        if remaining:
            cursor = SyncCursor(
                schema_version=CURSOR_SCHEMA_VERSION,
                history_id="",
                account_key=account_key,
                resume_page_token=page_token or "",
                sync_mode=mode,
                pending_message_ids=remaining,
                last_error="partial_page",
            )
            cursor_store.save(cursor)
            result.partial = True
            return result

        if max_pages is not None and pages >= max_pages and next_token:
            cursor = SyncCursor(
                schema_version=CURSOR_SCHEMA_VERSION,
                history_id="",
                account_key=account_key,
                resume_page_token=str(next_token),
                sync_mode=mode,
                last_error="",
            )
            cursor_store.save(cursor)
            result.partial = True
            return result

        if not next_token:
            break
        page_token = next_token

    try:
        history_id = _call_with_retry(
            lambda: get_profile_history_id(service),
            attempts=retry_attempts,
            wait_seconds=retry_wait_seconds,
        )
    except Exception as exc:
        result.errors.append(f"profile:{type(exc).__name__}")
        history_id = ""

    cursor = SyncCursor(
        schema_version=CURSOR_SCHEMA_VERSION,
        history_id=history_id,
        account_key=account_key,
        resume_page_token="",
        sync_mode="incremental" if history_id else mode,
        pending_message_ids=[],
        last_error="",
    )
    cursor_store.save(cursor)
    result.new_history_id = history_id
    return result
