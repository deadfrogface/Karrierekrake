"""Load versioned lifecycle E2E fixtures + existing corpora."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "fixtures" / "lifecycle_e2e"


def _load(name: str) -> dict[str, Any] | list[Any]:
    path = FIXTURE_DIR / name
    return json.loads(path.read_text(encoding="utf-8"))


def load_manifest() -> dict[str, Any]:
    return _load("manifest.json")  # type: ignore[return-value]


def load_recruiting_mails() -> list[dict[str, Any]]:
    data = _load("recruiting_mails.json")
    return list(data["items"])  # type: ignore[index]


def load_injection_mails() -> list[dict[str, Any]]:
    data = _load("injection_mails.json")
    return list(data["items"])  # type: ignore[index]


def load_status_transitions() -> list[dict[str, Any]]:
    data = _load("status_transitions.json")
    return list(data["items"])  # type: ignore[index]


def load_calendar_cases() -> list[dict[str, Any]]:
    data = _load("calendar_cases.json")
    return list(data["items"])  # type: ignore[index]


def load_full_lifecycles() -> list[dict[str, Any]]:
    data = _load("full_lifecycles.json")
    return list(data["items"])  # type: ignore[index]


def load_association_scenarios() -> list[dict[str, Any]]:
    path = ROOT / "fixtures" / "association" / "competing_application_corpus.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return list(data.get("scenarios") or [])


def load_reply_scenarios() -> list[dict[str, Any]]:
    path = ROOT / "fixtures" / "replies" / "reply_safety_corpus.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return list(data.get("scenarios") or [])
