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
    from core.cv_docpick_import import reset_import_timeout

    reset_import_timeout()
    monkeypatch.setattr("core.cv_docpick_import.CV_IMPORT_TIMEOUT_S", 0.01)
    with pytest.raises(CvImportError) as ei:
        _enforce_timeout(0.0, stage="unit")
    assert ei.value.code == "llm_timeout"
    assert str(ei.value) == "llm_timeout: llm_timeout"


def test_unmeasured_private_commit_is_not_a_pass(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    from core.cv_docpick_import import reset_private_commit_high_water

    reset_private_commit_high_water()
    monkeypatch.setattr(
        "core.cv_docpick_import.cv_path_peak_rss_bytes",
        lambda **_kwargs: 0,
    )
    with caplog.at_level("ERROR"):
        with pytest.raises(CvImportError) as ei:
            _enforce_peak_rss(stage="unit")
    assert ei.value.code == "peak_rss_unmeasured"
    assert "unmeasured" in caplog.text
    assert "not a pass" in caplog.text
    monkeypatch.setattr(
        "core.cv_docpick_import.cv_path_peak_rss_bytes",
        lambda **_kwargs: None,
    )
    with pytest.raises(CvImportError) as ei2:
        _enforce_peak_rss(stage="unit")
    assert ei2.value.code == "peak_rss_unmeasured"


def test_peak_rss_above_3_3gb_hard_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "core.cv_docpick_import.cv_path_peak_rss_bytes",
        lambda **_kwargs: 9_000_000_000,
    )
    with pytest.raises(CvImportError) as ei:
        _enforce_peak_rss(stage="unit")
    assert ei.value.code == "peak_rss_exceeded"
    from core.cv_docpick_import import reset_private_commit_high_water

    reset_private_commit_high_water()
    assert CV_IMPORT_PEAK_RSS_BYTES_MAX == 3_300_000_000
    assert CV_IMPORT_PEAK_RSS_MB_MAX == 3_300_000_000 / (1024.0 * 1024.0)


def test_child_budget_is_never_negative() -> None:
    from core.cv_docpick_import import (
        CV_IMPORT_CHILD_MIN_AFTER_LOAD_BYTES,
        CV_IMPORT_FRESH_APP_PRIVATE_BYTES,
        child_budget_for_app_private,
        child_start_allowed,
        fresh_app_child_budget_bytes,
    )

    assert CV_IMPORT_FRESH_APP_PRIVATE_BYTES == 167_272_448
    assert CV_IMPORT_CHILD_MIN_AFTER_LOAD_BYTES == 1_698_168_832
    fresh = fresh_app_child_budget_bytes()
    assert fresh == 3_300_000_000 - 167_272_448
    assert child_budget_for_app_private(3_300_000_000) == 0
    assert child_budget_for_app_private(4_000_000_000) == 0
    assert child_budget_for_app_private(-1) == 3_300_000_000
    allowed, budget = child_start_allowed(3_200_000_000)
    assert budget == 100_000_000
    assert budget < CV_IMPORT_CHILD_MIN_AFTER_LOAD_BYTES
    assert allowed is False


def test_over_current_budget_but_under_fresh_is_app_share(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    from core.cv_docpick_import import (
        CV_IMPORT_CHILD_MIN_AFTER_LOAD_BYTES,
        fresh_app_child_budget_bytes,
        reset_private_commit_high_water,
    )

    reset_private_commit_high_water()
    sample = CV_IMPORT_CHILD_MIN_AFTER_LOAD_BYTES + 1
    assert sample < fresh_app_child_budget_bytes()
    monkeypatch.setenv(
        "KARRIEREKRAKE_CV_CHILD_BUDGET_BYTES",
        str(CV_IMPORT_CHILD_MIN_AFTER_LOAD_BYTES),
    )
    monkeypatch.setenv("KARRIEREKRAKE_CV_APP_PRIVATE_BYTES", "1601831168")
    monkeypatch.setattr(
        "core.cv_docpick_import.cv_path_peak_rss_bytes",
        lambda **_kwargs: sample,
    )
    with caplog.at_level("INFO"):
        with pytest.raises(CvImportError) as ei:
            _enforce_peak_rss(stage="after_load")
    assert ei.value.code == "memory_budget_app_share"
    assert "app_private=1601831168" in caplog.text
    assert f"child_bytes={sample}" in caplog.text
    reset_private_commit_high_water()


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
