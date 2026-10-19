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
