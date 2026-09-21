"""Human-readable status labels mapped from stored DB enums (values unchanged)."""

from __future__ import annotations

from desktop.i18n import tr

# Canonical stored values → i18n keys. Never rewrite DB enums.
_STATUS_KEYS: dict[str, str] = {
    "new": "status_label.new",
    "matched": "status_label.matched",
    "queued": "status_label.queued",
    "applying": "status_label.applying",
    "applied": "status_label.applied",
    "failed": "status_label.failed",
    "needs_review": "status_label.needs_review",
    "captcha": "status_label.captcha",
    "closed": "status_label.closed",
    "skipped": "status_label.skipped",
    "unsupported_ats": "status_label.unsupported_ats",
    "duplicate": "status_label.duplicate",
    "ignored": "status_label.ignored",
}


def status_label(raw: str | None) -> str:
    """Return a localized human label for a stored status enum string."""
    key = (raw or "").strip().lower()
    i18n_key = _STATUS_KEYS.get(key)
    if i18n_key:
        return tr(i18n_key)
    return raw or "—"


def status_label_with_cue(raw: str | None) -> str:
    """Status text with a non-color glyph prefix (PR44 — never color-only)."""
    from desktop.design_system.icons import status_glyph

    kind_map = {
        "ok": "success",
        "warn": "warning",
        "danger": "error",
        "muted": "muted",
        "info": "info",
    }
    kind = kind_map.get(status_badge_kind(raw), "info")
    return f"{status_glyph(kind)}: {status_label(raw)}"


def status_badge_kind(raw: str | None) -> str:
    """Simple badge kind for styling hints: ok / warn / danger / muted / info."""
    key = (raw or "").strip().lower()
    if key in {"applied", "matched"}:
        return "ok"
    if key in {"needs_review", "captcha", "queued", "applying"}:
        return "warn"
    if key in {"failed", "unsupported_ats"}:
        return "danger"
    if key in {"closed", "skipped", "duplicate", "ignored"}:
        return "muted"
    return "info"
