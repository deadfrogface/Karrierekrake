"""Repeatability: deterministic CV parse must be stable across runs."""

from __future__ import annotations

from pathlib import Path

from core.cv_extract import extract_text
from core.cv_parser import parse_cv_text

CORPUS = Path(__file__).parent / "fixtures" / "cv_corpus"
PDF = CORPUS / "DE_01_Klassisch.pdf"


def test_deterministic_parse_repeatability():
    text = extract_text(PDF)
    runs = [parse_cv_text(text) for _ in range(3)]
    keys = ("emails", "phones", "skills", "software", "languages", "education", "work_experience")
    for key in keys:
        a, b, c = runs[0].get(key), runs[1].get(key), runs[2].get(key)
        assert a == b == c, f"non-deterministic field {key}"
