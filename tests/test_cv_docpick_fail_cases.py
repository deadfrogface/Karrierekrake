"""Fail-case + matching-contract tests for Docpick CV import (no live LLM required)."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.cv_docpick_import import (
    CV_IMPORT_PEAK_RSS_BYTES_MAX,
    CV_IMPORT_PEAK_RSS_MB_MAX,
    PARSED_CV_CONTRACT_VERSION,
    PARSED_CV_PERSONAL_KEYS,
    PARSED_CV_TOP_LEVEL_KEYS,
    CvImportError,
    _enforce_peak_rss,
    _enforce_timeout,
    import_cv_docpick,
    suggestion_to_parsed,
)


def test_empty_cv_zero_byte_hard_fails(tmp_path: Path) -> None:
    empty = tmp_path / "empty.pdf"
    empty.write_bytes(b"")
    with pytest.raises(CvImportError) as ei:
        import_cv_docpick(empty)
    assert ei.value.code == "empty_cv"


def test_corrupt_cv_garbage_hard_fails(tmp_path: Path) -> None:
    bad = tmp_path / "corrupt.pdf"
    bad.write_bytes(b"\x00\x01\x02NOT_A_PDF_FILE!!!!")
    with pytest.raises(CvImportError) as ei:
        import_cv_docpick(bad)
    assert ei.value.code == "unreadable_cv"


def test_timeout_hard_fails_without_hang(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("core.cv_docpick_import.CV_IMPORT_TIMEOUT_S", 0.01)
    with pytest.raises(CvImportError) as ei:
        _enforce_timeout(0.0, stage="unit")
    assert ei.value.code == "timeout"
    assert "Timeout" in str(ei.value) or "timeout" in str(ei.value).lower()


def test_peak_rss_above_3_3gb_hard_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "core.cv_docpick_import.cv_path_peak_rss_bytes",
        lambda: 9_000_000_000,
    )
    with pytest.raises(CvImportError) as ei:
        _enforce_peak_rss(stage="unit")
    assert ei.value.code == "peak_rss_exceeded"
    assert CV_IMPORT_PEAK_RSS_BYTES_MAX == 3_300_000_000
    assert CV_IMPORT_PEAK_RSS_MB_MAX == 3_300_000_000 / (1024.0 * 1024.0)


def test_parsed_cv_matching_contract_stable() -> None:
    """No silent schema drift vs profile/matching consumers."""
    assert PARSED_CV_CONTRACT_VERSION == 1
    parsed = suggestion_to_parsed(
        {
            "name": {"first_name": "A", "last_name": "B"},
            "email": "a@example.com",
            "phone": "+491234",
            "employment": [],
            "education": [],
            "skills": ["x"],
            "software": ["y"],
            "certificates": [],
            "languages": [{"language": "Deutsch", "level": "C2"}],
            "licenses": ["B"],
        }
    )
    assert PARSED_CV_TOP_LEVEL_KEYS <= frozenset(parsed)
    assert PARSED_CV_PERSONAL_KEYS <= frozenset(parsed["personal"])
    # Qualification sections used by profile_patch / matching stay present.
    for key in (
        "languages",
        "education",
        "work_experience",
        "certificates",
        "skills",
        "software",
        "driving_license",
    ):
        assert key in parsed
