"""Secure local token storage for Gmail/Calendar OAuth (PR40).

Refresh/access tokens live in the **OS credential store** via
`keyring` (https://github.com/jaraco/keyring) — Windows Credential Locker,
macOS Keychain, or Secret Service.

**No plaintext fallback.** If the keyring is unavailable, callers must
force re-login rather than writing `oauth_*.json`.

Legacy mode-0600 JSON files are migrated into the keyring once, then deleted.
If migration is impossible, the insecure file is wiped and the user re-auths.

Never log token values (see `core.security.redaction`).
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from core.security.redaction import install_redaction_filter, safe_exc_str

logger = logging.getLogger("karrierekrake.tokens")
install_redaction_filter("karrierekrake")

SERVICE_NAME = "Karrierekrake"


class SecureStorageError(RuntimeError):
    """Base for token persistence failures."""


class KeyringUnavailable(SecureStorageError):
    """STOP: cannot persist secrets without OS credential storage."""


def _keyring():
    try:
        import keyring  # type: ignore

        return keyring
    except Exception:
        return None


def keyring_available() -> bool:
    kr = _keyring()
    if kr is None:
        return False
    try:
        # Probe with a harmless get — backends may raise on first use.
        kr.get_password(SERVICE_NAME, "__kk_probe__")
        return True
    except Exception:
        # Some backends error on missing keys; treat import success as available
        # unless set_password also fails (checked at store time).
        return True


def legacy_token_path(account: str, fallback_dir: Path) -> Path:
    return Path(fallback_dir) / f"oauth_{account}.json"


def _wipe_file(path: Path) -> None:
    if not path.is_file():
        return
    try:
        size = path.stat().st_size
        with path.open("wb") as fh:
            fh.write(b"\x00" * min(max(size, 1), 1024 * 1024))
            fh.flush()
            try:
                os.fsync(fh.fileno())
            except OSError:
                pass
        path.unlink(missing_ok=True)
    except OSError:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def _keyring_set(account: str, raw: str) -> None:
    kr = _keyring()
    if kr is None:
        raise KeyringUnavailable("keyring package unavailable")
    try:
        kr.set_password(SERVICE_NAME, account, raw)
    except Exception as exc:
        raise KeyringUnavailable(safe_exc_str(exc)) from None


def _keyring_get(account: str) -> str | None:
    kr = _keyring()
    if kr is None:
        return None
    try:
        return kr.get_password(SERVICE_NAME, account)
    except Exception as exc:
        logger.warning("keyring load failed: %s", type(exc).__name__)
        return None


def _keyring_delete(account: str) -> None:
    kr = _keyring()
    if kr is None:
        return
    try:
        kr.delete_password(SERVICE_NAME, account)
    except Exception:
        pass


def migrate_legacy_file_to_keyring(account: str, *, fallback_dir: Path) -> str:
    """Migrate legacy JSON once. Returns status code.

    Statuses: ``migrated`` | ``already_keyring`` | ``wiped_relogin`` | ``absent``
    """
    path = legacy_token_path(account, fallback_dir)
    existing = _keyring_get(account)
    if existing:
        if path.is_file():
            _wipe_file(path)
        return "already_keyring"
    if not path.is_file():
        return "absent"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            _wipe_file(path)
            return "wiped_relogin"
    except (OSError, json.JSONDecodeError):
        _wipe_file(path)
        return "wiped_relogin"

    try:
        raw = json.dumps(data, ensure_ascii=False)
        _keyring_set(account, raw)
        verify = _keyring_get(account)
        if not verify:
            raise KeyringUnavailable("keyring verify read returned empty")
        _wipe_file(path)
        return "migrated"
    except KeyringUnavailable:
        # STOP — do not keep plaintext. Force re-login.
        _wipe_file(path)
        return "wiped_relogin"


def store_token(account: str, payload: dict[str, Any], *, fallback_dir: Path) -> str:
    """Persist token dict to OS keyring only. Returns ``'keyring'``.

    ``fallback_dir`` is retained for API compatibility (legacy wipe path) —
    **new** plaintext files are never written.
    """
    if not isinstance(payload, dict):
        raise TypeError("payload must be a dict")
    raw = json.dumps(payload, ensure_ascii=False)
    _keyring_set(account, raw)
    # Successful keyring write → destroy any leftover legacy file.
    _wipe_file(legacy_token_path(account, fallback_dir))
    return "keyring"


def load_token(account: str, *, fallback_dir: Path) -> dict[str, Any] | None:
    """Load from keyring; attempt one-shot legacy migration; never return file-only secrets."""
    status = migrate_legacy_file_to_keyring(account, fallback_dir=fallback_dir)
    if status == "wiped_relogin":
        logger.info("legacy token wiped — re-login required")
    raw = _keyring_get(account)
    if not raw:
        # Ensure no plaintext remnant remains even if keyring empty.
        _wipe_file(legacy_token_path(account, fallback_dir))
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("corrupt keyring payload — clearing")
        _keyring_delete(account)
        return None
    return data if isinstance(data, dict) else None


def delete_token(account: str, *, fallback_dir: Path) -> None:
    _keyring_delete(account)
    _wipe_file(legacy_token_path(account, fallback_dir))
