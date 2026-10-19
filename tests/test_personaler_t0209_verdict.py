"""Personaler T02.09 verdict helper (scripts/personaler_t0209_verdict.py).

Synthetic data only: the session JSONs are built in tmp_path in the shape the
Performance-Optimizer harness (thinkpad_cv_bench.py, schema kk-cv-speed-bench/1)
writes, the extract is a hand-written DE_01 extract taken from the Sollwerte
sheet. Gold files and Sollwerte are read, never written.

User-path strings are assembled at runtime so this file itself stays clean for
scripts/privacy_scan.py.
"""

from __future__ import annotations

import copy
import importlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

HARNESS = "a" * 64
OTHER_HARNESS = "b" * 64
DE01 = "DE_01_Klassisch.pdf"


@pytest.fixture()
def v():
    return importlib.import_module("personaler_t0209_verdict")


def good_parsed() -> dict:
    """DE_01 extract that matches the Sollwerte sheet (synthetic CV)."""
    return {
        "personal": {
            "first_name": "Mara",
            "last_name": "König",
            "street": "Buchenweg",
            "house_number": "14",
            "postal_code": "48143",
            "city": "Münster",
            "date_of_birth": "07.11.1994",
        },
        "emails": ["mara.koenig@example.com"],
        "phones": ["+49 151 20003000"],
        "languages": [
            {"language": "Deutsch", "level": "Muttersprache (C2)"},
            {"language": "Englisch", "level": "C1"},
            {"language": "Französisch", "level": "B1"},
        ],
        "driving_license": ["B"],
        "education": [
            {
                "qualification": "Kauffrau für Büromanagement (IHK)",
                "institution": "Berufskolleg Münster / BüroPartner West GmbH",
                "start_date": "08/2013",
                "end_date": "06/2016",
            }
        ],
        "work_experience": [
            {"title": "Teamkoordinatorin Kundenservice", "company": "Westfalen Service GmbH"},
            {"title": "Sachbearbeiterin Auftragsmanagement", "company": "HanseKontor Handel KG"},
            {"title": "Kaufmännische Mitarbeiterin", "company": "Rheinblick Versand GmbH"},
        ],
        "software": ["Microsoft 365", "SAP Business One", "Salesforce", "Jira", "Confluence", "DocuWare"],
        "skills": [
            "Kundenservice",
            "Auftragsmanagement",
            "KPI-Reporting",
            "Prozessoptimierung",
            "Reklamationsmanagement",
        ],
        "certificates": [
            {"name": "IHK Beschwerdemanagement", "issuer": "", "year": "2024"},
            {"name": "Power BI Grundlagen", "issuer": "", "year": "2023"},
            {"name": "Ersthelferin", "issuer": "", "year": "2025"},
        ],
        "source_path": DE01,
    }


def base_session(**over) -> dict:
    s = {
        "schema": "kk-cv-speed-bench/1",
        "label": "fixture-4b-q2kxl-gsq",
        "harness_sha256": HARNESS,
        "mode": "import",
        "model": {"path": "<MODELS_DIR>/Qwen3.5-4B-Q2_K_XL.gguf", "sha256": "c" * 64},
        "cwd": "<KK_REPO>",
        "native_scrub": {"enabled": True, "source": "env KK_BENCH_NATIVE_SCRUB"},
        "evidence_eligible": True,
        "power_state_consistent": True,
        "runs": [],
    }
    s.update(over)
    return s


def write_session(tmp_path: Path, session: dict, parsed: dict | None = None, *, name="s") -> Path:
    d = tmp_path / name
    stem = Path(DE01).stem
    (d / "extracts" / stem).mkdir(parents=True, exist_ok=True)
    s = copy.deepcopy(session)
    if parsed is not None and not s["runs"]:
        (d / "extracts" / stem / "run1.parsed.json").write_text(
            json.dumps(parsed, ensure_ascii=False), encoding="utf-8"
        )
        s["runs"] = [
            {
                "cv": DE01,
                "tag": "run1",
                "kind": "measured",
                "ok": True,
                "files": {"parsed": f"extracts/{stem}/run1.parsed.json"},
                "parsed_sha256": "d" * 64,
            }
        ]
    p = d / "session.json"
    p.write_text(json.dumps(s, ensure_ascii=False), encoding="utf-8")
    return p


def row_for(rows: list[dict], cv: str) -> dict:
    hits = [r for r in rows if r["cv"] == cv]
    assert len(hits) == 1, rows
    return hits[0]


def all_rows_verdict(rows: list[dict]) -> set[str]:
    return {r["verdict"] for r in rows}


# ---------------------------------------------------------------- eligible


def test_eligible_clean_extract_is_interview_ready(v, tmp_path):
    p = write_session(tmp_path, base_session(), good_parsed())
    rows = v.judge_session(p, HARNESS)
    r = row_for(rows, DE01)
    assert r["verdict"] == v.INTERVIEW_READY, r
    assert r["model"].startswith("Qwen3.5-4B-Q2_K_XL")


def test_cvs_without_run_are_blockiert(v, tmp_path):
    p = write_session(tmp_path, base_session(), good_parsed())
    rows = v.judge_session(p, HARNESS)
    cvs = {r["cv"] for r in rows}
    assert "EN_05_Skills_Heavy.pdf" in cvs and len(cvs) == 10
    r = row_for(rows, "EN_05_Skills_Heavy.pdf")
    assert r["verdict"] == v.BLOCKIERT and "kein Lauf" in r["reason"]


# ---------------------------------------------------------------- session gates


def test_true_with_reasons_is_blockiert(v, tmp_path):
    s = base_session(evidence_ineligible_reasons=["native_scrub_disabled"])
    rows = v.judge_session(write_session(tmp_path, s, good_parsed()), HARNESS)
    assert all_rows_verdict(rows) == {v.BLOCKIERT}
    assert "native_scrub_disabled" in rows[0]["reason"]


def test_true_with_user_named_evidence_reasons_key_is_blockiert(v, tmp_path):
    s = base_session(evidence_reasons=["power"])
    rows = v.judge_session(write_session(tmp_path, s, good_parsed()), HARNESS)
    assert all_rows_verdict(rows) == {v.BLOCKIERT}


def test_reasons_not_a_list_is_blockiert(v, tmp_path):
    s = base_session(evidence_ineligible_reasons="x")
    rows = v.judge_session(write_session(tmp_path, s, good_parsed()), HARNESS)
    assert all_rows_verdict(rows) == {v.BLOCKIERT}


@pytest.mark.parametrize("val", ["True", "true", 1, None])
def test_non_bool_evidence_eligible_is_blockiert(v, tmp_path, val):
    s = base_session(evidence_eligible=val)
    rows = v.judge_session(write_session(tmp_path, s, good_parsed()), HARNESS)
    assert all_rows_verdict(rows) == {v.BLOCKIERT}
    assert "evidence_eligible" in rows[0]["reason"]


def test_missing_evidence_eligible_is_blockiert(v, tmp_path):
    s = base_session()
    del s["evidence_eligible"]
    rows = v.judge_session(write_session(tmp_path, s, good_parsed()), HARNESS)
    assert all_rows_verdict(rows) == {v.BLOCKIERT}


@pytest.mark.parametrize(
    "ns", [{"enabled": False}, {"enabled": "True"}, None, "on", {}]
)
def test_native_scrub_not_on_is_blockiert(v, tmp_path, ns):
    s = base_session(native_scrub=ns)
    rows = v.judge_session(write_session(tmp_path, s, good_parsed()), HARNESS)
    assert all_rows_verdict(rows) == {v.BLOCKIERT}
    assert "native_scrub" in rows[0]["reason"]


def test_harness_mismatch_is_not_judged(v, tmp_path):
    s = base_session(harness_sha256=OTHER_HARNESS)
    rows = v.judge_session(write_session(tmp_path, s, good_parsed()), HARNESS)
    assert all_rows_verdict(rows) == {v.OTHER_HARNESS}
    assert v.OTHER_HARNESS == "anderer Harness"


def test_harness_missing_is_not_judged(v, tmp_path):
    s = base_session()
    del s["harness_sha256"]
    rows = v.judge_session(write_session(tmp_path, s, good_parsed()), HARNESS)
    assert all_rows_verdict(rows) == {v.OTHER_HARNESS}


def test_power_inconsistent_is_blockiert(v, tmp_path):
    s = base_session(power_state_consistent=False)
    rows = v.judge_session(write_session(tmp_path, s, good_parsed()), HARNESS)
    assert all_rows_verdict(rows) == {v.BLOCKIERT}


def test_unreadable_session_is_blockiert(v, tmp_path):
    p = tmp_path / "broken.json"
    p.write_text("{not json", encoding="utf-8")
    rows = v.judge_session(p, HARNESS)
    assert all_rows_verdict(rows) == {v.BLOCKIERT}


# ---------------------------------------------------------------- user paths

_SEP = "\\"


def _win_user_path() -> str:
    return "C:" + _SEP + "Users" + _SEP + "maxmuster" + _SEP + "kk" + _SEP + "run"


def _unix_user_path() -> str:
    return "/" + "home" + "/maxmuster/" + "Desktop" + "/kk"


@pytest.mark.parametrize("where", ["cwd", "argv"])
def test_windows_user_path_in_session_is_rejected(v, tmp_path, where):
    s = base_session()
    s[where] = _win_user_path() if where == "cwd" else ["bench.py", "--out", _win_user_path()]
    rows = v.judge_session(write_session(tmp_path, s, good_parsed()), HARNESS)
    assert all_rows_verdict(rows) == {v.BLOCKIERT}
    assert "Nutzerpfad" in rows[0]["reason"]


def test_json_escaped_user_path_is_rejected(v, tmp_path):
    s = base_session(notes=_win_user_path().replace(_SEP, "\\u005c"))
    rows = v.judge_session(write_session(tmp_path, s, good_parsed()), HARNESS)
    assert all_rows_verdict(rows) == {v.BLOCKIERT}


def test_unix_home_user_path_in_extract_is_rejected(v, tmp_path):
    parsed = good_parsed()
    parsed["source_path"] = _unix_user_path() + "/DE_01_Klassisch.pdf"
    rows = v.judge_session(write_session(tmp_path, base_session(), parsed), HARNESS)
    assert row_for(rows, DE01)["verdict"] == v.BLOCKIERT
    assert "Nutzerpfad" in row_for(rows, DE01)["reason"]


def test_scrubbed_placeholders_are_not_user_paths(v, tmp_path):
    s = base_session(cwd="<KK_REPO>", notes="C:" + _SEP + "Users" + _SEP + "%USERNAME%" + _SEP + "x")
    rows = v.judge_session(write_session(tmp_path, s, good_parsed()), HARNESS)
    assert row_for(rows, DE01)["verdict"] == v.INTERVIEW_READY


# ---------------------------------------------------------------- per-CV findings


def test_native_dropped_is_papierkorb(v, tmp_path):
    parsed = good_parsed()
    parsed["languages"][0]["level"] = "C2"
    rows = v.judge_session(write_session(tmp_path, base_session(), parsed), HARNESS)
    r = row_for(rows, DE01)
    assert r["verdict"] == v.PAPIERKORB and "native_dropped" in r["reason"], r
    assert "Deutsch" in r["native_dropped"]


def test_invented_native_is_papierkorb(v, tmp_path):
    parsed = good_parsed()
    parsed["languages"][1]["level"] = "native"
    rows = v.judge_session(write_session(tmp_path, base_session(), parsed), HARNESS)
    r = row_for(rows, DE01)
    assert r["verdict"] == v.PAPIERKORB and "invented_native" in r["reason"], r
    assert "Englisch" in r["invented_native"]


def test_invented_certificate_is_papierkorb(v, tmp_path):
    parsed = good_parsed()
    parsed["certificates"].append({"name": "Scrum Master PSM I", "issuer": "", "year": ""})
    r = row_for(v.judge_session(write_session(tmp_path, base_session(), parsed), HARNESS), DE01)
    assert r["verdict"] == v.PAPIERKORB and "Scrum Master PSM I" in r["reason"], r


def test_language_level_as_licence_is_papierkorb(v, tmp_path):
    parsed = good_parsed()
    parsed["driving_license"] = ["B", "C1"]
    r = row_for(v.judge_session(write_session(tmp_path, base_session(), parsed), HARNESS), DE01)
    assert r["verdict"] == v.PAPIERKORB and "C1" in r["reason"], r


def test_invented_employer_is_papierkorb(v, tmp_path):
    parsed = good_parsed()
    parsed["work_experience"].append({"title": "Kassiererin", "company": "Phantasia Markt AG"})
    r = row_for(v.judge_session(write_session(tmp_path, base_session(), parsed), HARNESS), DE01)
    assert r["verdict"] == v.PAPIERKORB and "Phantasia Markt AG" in r["reason"], r


def test_sollwert_deviation_is_papierkorb(v, tmp_path):
    parsed = good_parsed()
    parsed["work_experience"] = parsed["work_experience"][:2]
    r = row_for(v.judge_session(write_session(tmp_path, base_session(), parsed), HARNESS), DE01)
    assert r["verdict"] == v.PAPIERKORB and "BERUF" in r["reason"], r


def test_failed_run_is_blockiert(v, tmp_path):
    s = base_session(
        runs=[{"cv": DE01, "tag": "run1", "kind": "measured", "ok": False, "files": {},
               "error": {"type": "TimeoutError", "code": "timeout"}}]
    )
    r = row_for(v.judge_session(write_session(tmp_path, s), HARNESS), DE01)
    assert r["verdict"] == v.BLOCKIERT


def test_missing_extract_file_is_blockiert_unsicher(v, tmp_path):
    s = base_session(
        runs=[{"cv": DE01, "tag": "run1", "kind": "measured", "ok": True,
               "files": {"parsed": "extracts/DE_01_Klassisch/run9.parsed.json"}}]
    )
    r = row_for(v.judge_session(write_session(tmp_path, s), HARNESS), DE01)
    assert r["verdict"] == v.BLOCKIERT and "UNSICHER" in r["reason"], r


def test_extract_path_outside_session_dir_is_blockiert(v, tmp_path):
    (tmp_path / "evil.json").write_text(json.dumps(good_parsed()), encoding="utf-8")
    s = base_session(
        runs=[{"cv": DE01, "tag": "run1", "kind": "measured", "ok": True,
               "files": {"parsed": "../evil.json"}}]
    )
    r = row_for(v.judge_session(write_session(tmp_path, s), HARNESS), DE01)
    assert r["verdict"] == v.BLOCKIERT


def test_corpus_eval_native_dropped_without_extract_is_papierkorb(v, tmp_path):
    s = base_session(
        runs=[{"cv": DE01, "tag": "run1", "kind": "measured", "ok": True, "files": {},
               "corpus_eval": {"languages": "FAIL(Deutsch:native_dropped)"}}]
    )
    r = row_for(v.judge_session(write_session(tmp_path, s), HARNESS), DE01)
    assert r["verdict"] == v.PAPIERKORB and "native_dropped" in r["reason"], r


def test_llm_mode_extract_is_unsicher(v, tmp_path):
    parsed = {"_mode": "llm", "llm_json": "{}"}
    s = base_session(mode="llm")
    r = row_for(v.judge_session(write_session(tmp_path, s, parsed), HARNESS), DE01)
    assert r["verdict"] == v.BLOCKIERT and "UNSICHER" in r["reason"], r


def test_warmup_runs_are_ignored(v, tmp_path):
    p = write_session(tmp_path, base_session(), good_parsed())
    s = json.loads(p.read_text(encoding="utf-8"))
    s["runs"].insert(0, {"cv": DE01, "tag": "warmup1", "kind": "warmup", "ok": False, "files": {}})
    p.write_text(json.dumps(s), encoding="utf-8")
    assert row_for(v.judge_session(p, HARNESS), DE01)["verdict"] == v.INTERVIEW_READY


# ---------------------------------------------------------------- output


def test_markdown_table_and_cli(v, tmp_path, capsys):
    good = write_session(tmp_path, base_session(), good_parsed(), name="good")
    bad = write_session(tmp_path, base_session(harness_sha256=OTHER_HARNESS), good_parsed(), name="other")
    rc = v.main([str(good), str(bad), "--harness-sha256", HARNESS])
    out = capsys.readouterr().out
    assert rc == 0
    assert "| Modell | CV | Vorschlag | Begründung |" in out
    assert "Interview-ready" in out and "anderer Harness" in out
    assert "Vorschlag" in out and "Personaler" in out  # final verdict stays human


def test_cli_rejects_malformed_harness_sha(v, tmp_path):
    good = write_session(tmp_path, base_session(), good_parsed())
    with pytest.raises(SystemExit):
        v.main([str(good), "--harness-sha256", "nope"])


def test_gold_files_unchanged_by_run(v, tmp_path):
    corpus = ROOT / "tests" / "fixtures" / "cv_corpus"
    files = [corpus / "expected_results.json", corpus / "CV_Parser_Sollwerte_Vollstaendig.txt"]
    before = [f.read_bytes() for f in files]
    v.judge_session(write_session(tmp_path, base_session(), good_parsed()), HARNESS)
    assert [f.read_bytes() for f in files] == before
