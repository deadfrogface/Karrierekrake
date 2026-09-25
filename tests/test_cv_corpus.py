"""Black-box regression: fictional CV corpus vs expected_results.json."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.run_cv_corpus import evaluate_doc, run_corpus

CORPUS = Path(__file__).parent / "fixtures" / "cv_corpus"
EXPECTED = CORPUS / "expected_results.json"

pytest.importorskip("docling", reason="Docpick production path requires docling; no DET fallback in CI")


@pytest.fixture(scope="module")
def expected_docs() -> dict:
    return json.loads(EXPECTED.read_text(encoding="utf-8"))["documents"]


def test_corpus_fixture_files_present(expected_docs: dict) -> None:
    assert EXPECTED.is_file()
    for name in expected_docs:
        assert (CORPUS / name).is_file(), name


def test_full_corpus_passes() -> None:
    rows, ok = run_corpus()
    failed = [r["cv"] for r in rows if not r.get("pass")]
    assert ok, f"corpus failures: {failed}"


@pytest.mark.parametrize(
    "pdf_name",
    [
        "DE_01_Klassisch.pdf",
        "DE_02_Zweispaltig_Trap.pdf",
        "DE_03_C1_Kontextfalle.pdf",
        "DE_04_Unvollstaendige_Kontaktdaten.pdf",
        "DE_05_Zweiseitig.pdf",
        "EN_01_Classic_Resume.pdf",
        "EN_02_Two_Column_Trap.pdf",
        "EN_03_Missing_Address_Fields.pdf",
        "EN_04_German_Address_English_CV.pdf",
        "EN_05_Skills_Heavy.pdf",
    ],
)
def test_each_corpus_document(pdf_name: str, expected_docs: dict) -> None:
    from core.cv_parser import import_cv

    parsed = import_cv(CORPUS / pdf_name)
    section = evaluate_doc(parsed, expected_docs[pdf_name])
    fails = {k: v for k, v in section.items() if not v[0]}
    assert not fails, fails
