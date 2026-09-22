"""Tests for evidence grounding, verify/repair, and PHI prompt separation."""

from __future__ import annotations

from pathlib import Path

from core.cv_evidence import evidence_in_source, ground_language_entries, is_language_fact
from core.cv_parser import parse_cv_text
from core.cv_verify_repair import MAX_REPAIR_ATTEMPTS, apply_verify_repair_pipeline, verify_parsed
from guenther.prompts import SYSTEM_PHI_EXTRACT, SYSTEM_PHI_WRITE, build_layers


def test_phi_extract_and_write_prompts_differ():
    assert "FAKTEN" in SYSTEM_PHI_EXTRACT or "extrahieren" in SYSTEM_PHI_EXTRACT.lower()
    assert "verifizierten" in SYSTEM_PHI_WRITE.lower() or "VERIFIZIERTEN" in SYSTEM_PHI_WRITE
    assert SYSTEM_PHI_EXTRACT != SYSTEM_PHI_WRITE
    sys_e, _, _ = build_layers(
        task="extract", schema_hint="{}", trusted="", untrusted="cv", system_core=SYSTEM_PHI_EXTRACT
    )
    sys_w, _, _ = build_layers(
        task="write", schema_hint="{}", trusted="profile", untrusted="job", system_core=SYSTEM_PHI_WRITE
    )
    assert "PHI_EXTRACT" in sys_e or "FAKTEN" in sys_e
    assert "PHI_WRITE" in sys_w or "VERIFIZIERTEN" in sys_w
    assert "FAKTEN" not in sys_w or "PHI_WRITE" in sys_w


def test_python_not_language_fact():
    assert is_language_fact("Deutsch")
    assert is_language_fact("Englisch")
    assert not is_language_fact("Python")
    assert not is_language_fact("Excel")
    assert not is_language_fact("Lean Management")


def test_ground_languages_rejects_skills():
    source = "Sprachen\nDeutsch C2\nEnglisch B2\nKenntnisse\nPython Fortgeschritten\nExcel Sehr gut"
    langs = [
        {"language": "Deutsch", "level": "C2"},
        {"language": "Englisch", "level": "B2"},
        {"language": "Python", "level": "Fortgeschritten"},
        {"language": "Excel", "level": "Sehr gut"},
    ]
    kept, _findings, rejected = ground_language_entries(langs, source)
    names = {e["language"] for e in kept}
    assert names == {"Deutsch", "Englisch"}
    assert {r["language"] for r in rejected} >= {"Python", "Excel"}


def test_verify_repair_moves_non_languages():
    text = """
Max Muster
Sprachen
Deutsch – Muttersprache
Englisch – C1
Python – Fortgeschritten
Excel – Sehr gut
Lean Management
"""
    parsed = parse_cv_text(text)
    # Force pollution if parser already cleaned — inject bad entries
    langs = list(parsed.get("languages") or [])
    langs.extend(
        [
            {"language": "Python", "level": "Fortgeschritten"},
            {"language": "Excel", "level": "Sehr gut"},
            {"language": "Lean Management", "level": ""},
        ]
    )
    parsed["languages"] = langs
    out = apply_verify_repair_pipeline(parsed, text)
    lang_names = {e["language"] for e in out.get("languages") or []}
    assert "Python" not in lang_names
    assert "Excel" not in lang_names
    assert "Lean Management" not in lang_names
    assert MAX_REPAIR_ATTEMPTS >= 1
    assert "verify_repair" in out


def test_evidence_in_source():
    assert evidence_in_source("Englisch C1", "Sprachen Englisch - C1 Deutsch")
    assert not evidence_in_source("Französisch", "Sprachen Englisch Deutsch")


def test_document_backends_current_available():
    from core.cv_document_backends import list_backends

    meta = list_backends()
    assert meta["current"]["available"] is True
