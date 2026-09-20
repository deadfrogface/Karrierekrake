"""Shared pytest fixtures for Karrierekrake tests."""

from __future__ import annotations

import pytest


class _MemoryKeyringBackend:
    """Process-local keyring so Linux CI can exercise OS-credential paths."""

    priority = 1

    def __init__(self) -> None:
        self._data: dict[str, str] = {}

    def set_password(self, service: str, account: str, password: str) -> None:
        self._data[f"{service}:{account}"] = password

    def get_password(self, service: str, account: str) -> str | None:
        return self._data.get(f"{service}:{account}")

    def delete_password(self, service: str, account: str) -> None:
        self._data.pop(f"{service}:{account}", None)


@pytest.fixture(autouse=True)
def _default_memory_keyring(monkeypatch: pytest.MonkeyPatch):
    """Prefer in-memory keyring unless a test replaces ``secure_tokens._keyring``."""
    try:
        from integrations import secure_tokens
    except Exception:
        yield
        return
    backend = _MemoryKeyringBackend()
    monkeypatch.setattr(secure_tokens, "_keyring", lambda: backend)
    yield backend
