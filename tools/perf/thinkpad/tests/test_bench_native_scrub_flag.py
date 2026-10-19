"""Every result file records whether native console scrubbing was on (Kritiker): a run with
KK_BENCH_NATIVE_SCRUB=0 is not evidence-eligible, and the matrix summary shows the flag per run."""
import csv
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_bench_result_privacy as rp  # noqa: E402
from test_bench_result_privacy import fake_home  # noqa: E402,F401  (fixture)

SRC = "env KK_BENCH_NATIVE_SCRUB"
REAL_PY = sys.executable          # fake_home swaps sys.executable for a sentinel path


def _check(doc: dict, enabled: bool):
    assert doc["native_scrub"] == {"enabled": enabled, "source": SRC}
    if enabled:
        assert doc.get("evidence_eligible", True) is not False
    else:
        assert doc["evidence_eligible"] is False
        assert "native_scrub_disabled" in doc["evidence_ineligible_reasons"]


def _set(monkeypatch, enabled: bool):
    if enabled:
        monkeypatch.delenv("KK_BENCH_NATIVE_SCRUB", raising=False)
    else:
        monkeypatch.setenv("KK_BENCH_NATIVE_SCRUB", "0")


@pytest.mark.parametrize("enabled", [True, False])
def test_cv_bench_session_and_summary_record_native_scrub(enabled, fake_home, monkeypatch, capsys):
    import thinkpad_cv_bench as h

    _set(monkeypatch, enabled)
    rp.test_cv_bench_session_has_no_home_repo_or_model_dirs(fake_home, monkeypatch)
    _home, k = fake_home
    d = k / "results" / "t"
    _check(json.loads((d / "session.json").read_text(encoding="utf-8")), enabled)
    capsys.readouterr()
    csv_p = k / "summary.csv"
    assert h.main(["summarize", str(d), "--csv", str(csv_p)]) == 0
    flag = "on" if enabled else "off"
    assert f"native_scrub={flag}" in capsys.readouterr().out                 # summary.txt (stdout)
    rows = list(csv.DictReader(csv_p.open(encoding="utf-8")))
    assert rows and all(r["native_scrub"] == flag for r in rows)
    assert all(r["evidence_eligible"] == ("True" if enabled else "False") for r in rows)


@pytest.mark.parametrize("enabled", [True, False])
def test_speed_bench_results_record_native_scrub(enabled, fake_home, monkeypatch, capsys):
    import thinkpad_speed_bench as sb

    _set(monkeypatch, enabled)
    rp.test_speed_bench_results_have_no_home_or_model_dirs(fake_home, monkeypatch)
    _home, k = fake_home
    d = k / "results-speed" / "t"
    _check(json.loads((d / "results.json").read_text(encoding="utf-8")), enabled)
    capsys.readouterr()
    assert sb.main(["summarize", str(d)]) == 0
    assert f"native_scrub={'on' if enabled else 'off'}" in capsys.readouterr().out


@pytest.mark.parametrize("enabled", [True, False])
def test_peak_raw_session_records_native_scrub(enabled, fake_home, monkeypatch):
    import thinkpad_cv_bench as bench
    import thinkpad_peak_raw as pr

    _set(monkeypatch, enabled)
    monkeypatch.setattr(sys, "executable", REAL_PY)   # peak_raw really starts the (fake) repo script
    _home, k = fake_home
    repo = k / "repo-47e8f83b"
    (repo / "scripts").mkdir(parents=True)
    (repo / "scripts" / "run_i3_peak_job_benchmark.py").write_text(
        "import json, sys\n"
        "out = sys.argv[sys.argv.index('--json-out') + 1]\n"
        "json.dump({'peak_bytes': 123, 'method': 'fake', 'ship_evidence': False,"
        " 'import_result': {'ok': True, 'kind': 'llm'}}, open(out, 'w'))\n", encoding="utf-8")
    (repo / "REPO_COMMIT").write_text("c" * 40 + "\n", encoding="utf-8")
    monkeypatch.setattr(bench, "corpus_documents", lambda r: [("DE_01_Klassisch.pdf", {})])
    monkeypatch.setattr(bench.psutil, "cpu_percent", lambda *a, **kw: 0.0)
    out = k / "results-peak"
    assert pr.main(["--repo", str(repo), "--model", str(k / "models" / rp.MODEL_NAME), "--out", str(out),
                    "--allow-concurrent"]) == 0
    _check(json.loads((out / "peak_raw_session.json").read_text(encoding="utf-8")), enabled)


# --- a result without the evidence_eligible field (e.g. an old run) is NOT evidence -----------------
MISSING = "evidence_eligible_missing"


def _strip_evidence(p: Path) -> None:
    doc = json.loads(p.read_text(encoding="utf-8"))
    for k in ("evidence_eligible", "evidence_ineligible_reasons", "native_scrub"):
        doc.pop(k, None)
    p.write_text(json.dumps(doc), encoding="utf-8")


def test_new_runs_record_evidence_eligible_explicitly(fake_home, monkeypatch):
    _set(monkeypatch, True)
    rp.test_cv_bench_session_has_no_home_repo_or_model_dirs(fake_home, monkeypatch)
    rp.test_speed_bench_results_have_no_home_or_model_dirs(fake_home, monkeypatch)
    _home, k = fake_home
    for p in (k / "results" / "t" / "session.json", k / "results-speed" / "t" / "results.json"):
        assert json.loads(p.read_text(encoding="utf-8"))["evidence_eligible"] is True


def test_cv_bench_summary_missing_evidence_eligible_is_not_evidence(fake_home, monkeypatch, capsys):
    import thinkpad_cv_bench as h

    _set(monkeypatch, True)
    rp.test_cv_bench_session_has_no_home_repo_or_model_dirs(fake_home, monkeypatch)
    _home, k = fake_home
    d = k / "results" / "t"
    _strip_evidence(d / "session.json")
    capsys.readouterr()
    csv_p = k / "summary.csv"
    assert h.main(["summarize", str(d), "--csv", str(csv_p)]) == 0
    out = capsys.readouterr().out                                            # summary.txt (stdout)
    assert "native_scrub=unknown" in out
    assert "evidence_eligible=False" in out
    assert "evidence_eligible=True" not in out
    assert MISSING in out
    rows = list(csv.DictReader(csv_p.open(encoding="utf-8")))
    assert rows and all(r["native_scrub"] == "unknown" for r in rows)
    assert all(r["evidence_eligible"] == "False" for r in rows)
    assert all(MISSING in r.get("evidence_ineligible_reasons", "") for r in rows)


def test_speed_bench_summary_missing_evidence_eligible_is_not_evidence(fake_home, monkeypatch, capsys):
    import thinkpad_speed_bench as sb

    _set(monkeypatch, True)
    rp.test_speed_bench_results_have_no_home_or_model_dirs(fake_home, monkeypatch)
    _home, k = fake_home
    d = k / "results-speed" / "t"
    _strip_evidence(d / "results.json")
    capsys.readouterr()
    assert sb.main(["summarize", str(d)]) == 0
    out = capsys.readouterr().out
    assert "native_scrub=unknown" in out
    assert "evidence_eligible=False" in out
    assert "evidence_eligible=True" not in out
    assert MISSING in out


@pytest.mark.parametrize("doc", [{}, {"native_scrub": {"enabled": True, "source": SRC}},
                                 {"evidence_eligible": None}, {"evidence_eligible": "yes"}])
def test_evidence_status_defaults_to_not_eligible(doc):
    import thinkpad_cv_bench as h

    ok, reasons = h.evidence_status(doc)
    assert ok is False
    assert MISSING in reasons


def test_no_reader_defaults_evidence_eligible_to_true():
    here = Path(__file__).resolve().parent.parent
    for f in ("thinkpad_cv_bench.py", "thinkpad_speed_bench.py", "thinkpad_peak_raw.py"):
        src = (here / f).read_text(encoding="utf-8")
        assert "get('evidence_eligible'" not in src and 'get("evidence_eligible"' not in src, f


# --- mark_native_scrub: True ONLY when the field is absent and no ineligibility reasons exist --------
_ABSENT = object()


@pytest.mark.parametrize("value, reasons, want_ok, want_reasons", [
    (None, None, False, ["evidence_eligible_invalid"]),
    ("no", None, False, ["evidence_eligible_invalid"]),
    ("yes", None, False, ["evidence_eligible_invalid"]),
    (0, None, False, ["evidence_eligible_invalid"]),
    (1, None, False, ["evidence_eligible_invalid"]),
    ("no", ["power_state_inconsistent"], False, ["power_state_inconsistent", "evidence_eligible_invalid"]),
    (_ABSENT, ["power_state_inconsistent"], False, ["power_state_inconsistent"]),
    (True, ["power_state_inconsistent"], False, ["power_state_inconsistent"]),
    (True, None, True, []),
    (True, [], True, []),
    (False, None, False, []),
    (_ABSENT, [], True, []),
    (_ABSENT, None, True, []),
], ids=["None", "str-no", "str-yes", "int0", "int1", "invalid+reasons", "absent+reasons", "true+reasons",
        "true", "true+empty", "false", "absent+empty-list", "absent+no-reasons"])
def test_mark_native_scrub_only_sets_true_when_absent_and_no_reasons(value, reasons, want_ok, want_reasons,
                                                                    monkeypatch):
    import thinkpad_cv_bench as h

    _set(monkeypatch, True)
    doc = {}
    if value is not _ABSENT:
        doc["evidence_eligible"] = value
    if reasons is not None:
        doc["evidence_ineligible_reasons"] = list(reasons)
    h.mark_native_scrub(doc)
    assert doc["evidence_eligible"] is want_ok
    assert list(doc.get("evidence_ineligible_reasons") or []) == want_reasons


@pytest.mark.parametrize("value", [_ABSENT, True, None, "yes", 1])
def test_mark_native_scrub_disabled_is_never_eligible(value, monkeypatch):
    import thinkpad_cv_bench as h

    _set(monkeypatch, False)
    doc = {} if value is _ABSENT else {"evidence_eligible": value}
    h.mark_native_scrub(doc)
    assert doc["evidence_eligible"] is False
    assert "native_scrub_disabled" in doc["evidence_ineligible_reasons"]


# --- evidence_status (summary reader): recorded reasons always win over an explicit True -------------
@pytest.mark.parametrize("doc, want_ok, want_in", [
    ({"evidence_eligible": True, "evidence_ineligible_reasons": ["power_state_inconsistent"]},
     False, ["power_state_inconsistent"]),
    ({"evidence_eligible": True, "evidence_ineligible_reasons": ["a", "b"]}, False, ["a", "b"]),
    ({"evidence_eligible": True, "evidence_ineligible_reasons": []}, True, []),
    ({"evidence_eligible": True}, True, []),
    ({"evidence_eligible": True, "evidence_ineligible_reasons": "power_state_inconsistent"},
     False, ["evidence_reasons_invalid"]),
    ({"evidence_eligible": True, "evidence_ineligible_reasons": {"x": 1}}, False, ["evidence_reasons_invalid"]),
    ({"evidence_eligible": True, "evidence_ineligible_reasons": 5}, False, ["evidence_reasons_invalid"]),
    ({"evidence_ineligible_reasons": "x"}, False, ["evidence_reasons_invalid", "evidence_eligible_missing"]),
], ids=["true+reason", "true+2reasons", "true+empty", "true", "reasons-str", "reasons-dict", "reasons-int",
        "absent+reasons-str"])
def test_evidence_status_reasons_override_true(doc, want_ok, want_in):
    import thinkpad_cv_bench as h

    ok, reasons = h.evidence_status(doc)
    assert ok is want_ok
    for r in want_in:
        assert r in reasons
    if want_ok:
        assert reasons == []


def test_cv_bench_summary_true_with_reasons_is_not_evidence(fake_home, monkeypatch, capsys):
    import thinkpad_cv_bench as h

    _set(monkeypatch, True)
    rp.test_cv_bench_session_has_no_home_repo_or_model_dirs(fake_home, monkeypatch)
    _home, k = fake_home
    d = k / "results" / "t"
    p = d / "session.json"
    doc = json.loads(p.read_text(encoding="utf-8"))
    doc["evidence_eligible"] = True
    doc["evidence_ineligible_reasons"] = ["power_state_inconsistent"]
    p.write_text(json.dumps(doc), encoding="utf-8")
    capsys.readouterr()
    csv_p = k / "summary.csv"
    assert h.main(["summarize", str(d), "--csv", str(csv_p)]) == 0
    out = capsys.readouterr().out
    assert "evidence_eligible=False" in out and "evidence_eligible=True" not in out
    assert "power_state_inconsistent" in out
    rows = list(csv.DictReader(csv_p.open(encoding="utf-8")))
    assert rows and all(r["evidence_eligible"] == "False" for r in rows)
    assert all("power_state_inconsistent" in r["evidence_ineligible_reasons"] for r in rows)
