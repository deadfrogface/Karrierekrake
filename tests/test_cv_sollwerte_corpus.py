"""Regression: production CV import vs CV_Parser_Sollwerte_Vollstaendig.txt (10 PDFs)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from run_cv_sollwerte_corpus import PDFS, run  # noqa: E402

CORPUS = Path(__file__).parent / "fixtures" / "cv_corpus"

pytest.importorskip("docling", reason="Docpick production path requires docling; no DET fallback in CI")


@pytest.mark.parametrize("pdf_name", PDFS)
def test_sollwerte_pdf_fixture_present(pdf_name: str):
    assert (CORPUS / pdf_name).is_file(), f"missing corpus PDF: {pdf_name}"


def test_sollwerte_authoritative_file_present():
    assert (CORPUS / "CV_Parser_Sollwerte_Vollstaendig.txt").is_file()


def test_sollwerte_corpus_production_path_all_pass():
    report = run(phi=False)
    if report.get("skipped"):
        pytest.skip(report.get("skip_reason") or "docpick deps missing")
    assert report["total"] == 10
    assert report["passed"] == 10, {
        name: doc.get("fails") or doc.get("error")
        for name, doc in report["documents"].items()
        if not doc.get("ok")
    }
