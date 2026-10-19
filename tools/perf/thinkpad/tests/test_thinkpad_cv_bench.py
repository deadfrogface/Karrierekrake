import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import thinkpad_cv_bench as h  # noqa: E402


def _mk(d: Path, label: str, parsed: dict, raw: str, tag="run1", commit="c" * 40):
    x = d / label / "extracts" / "DE_01_Klassisch"
    x.mkdir(parents=True)
    (x / f"{tag}.parsed.json").write_text(h.canon_json(parsed), encoding="utf-8")
    (x / f"{tag}.call1.primary_extract.raw.txt").write_text(raw, encoding="utf-8")
    (x / "_messages.0123456789abcdef.json").write_text("[]", encoding="utf-8")
    (d / label / "session.json").write_text(json.dumps({"label": label, "repo_commit": commit,
                                                        "llama": {"llama_cpp_python_version": "0.3.35"},
                                                        "model": {"sha256": "m"}}), encoding="utf-8")
    return d / label


def test_diff_identical_and_different(tmp_path, capsys):
    a = _mk(tmp_path, "a", {"personal": {"first_name": "Mara"}, "x": [1, 2]}, '{"a":1}')
    b = _mk(tmp_path, "b", {"personal": {"first_name": "Mara"}, "x": [1, 2]}, '{"a":1}')
    c = _mk(tmp_path, "c", {"personal": {"first_name": "Maria"}, "x": [1]}, '{"a":2}')
    assert h.main(["diff", str(a), str(b)]) == 0
    out = tmp_path / "d.json"
    assert h.main(["diff", str(a), str(c), "--json-out", str(out)]) == 1
    rep = json.loads(out.read_text(encoding="utf-8"))
    ent = rep["cvs"]["DE_01_Klassisch"][0]
    paths = {d["path"] for d in ent["parsed_json_diff"]}
    assert paths == {"$.personal.first_name", "$.x[1]"}
    assert ent["raw"][0]["identical"] is False and ent["raw"][0]["first_diff_offset"] == 5


def test_diff_warns_on_commit_mismatch(tmp_path, capsys):
    a = _mk(tmp_path, "a", {"k": 1}, "r")
    b = _mk(tmp_path, "b", {"k": 1}, "r", commit="d" * 40)
    assert h.main(["diff", str(a), str(b)]) == 0
    assert "repo commits differ" in capsys.readouterr().out


def test_normalise_parsed_drops_volatile():
    p, vol = h.normalise_parsed({"source_path": "C:\\x\\DE_01.pdf", "peak_rss_mb_at_end": 1.5, "a": 1})
    assert p == {"source_path": "DE_01.pdf", "a": 1}
    assert "peak_rss_mb_at_end" not in p and vol["peak_rss_mb_at_end"] == 1.5


def test_preflight_excludes_self_and_parents():
    import os
    found = h.other_python_llama_processes()
    assert all(f["pid"] != os.getpid() for f in found)


def _mk_spec(d: Path, label: str, raw: str, spec="off", seed=4294967295, temp=0.0, ok=True):
    x = d / label / "extracts" / "DE_01_Klassisch"
    x.mkdir(parents=True)
    (x / "run1.parsed.json").write_text(h.canon_json({"k": 1}), encoding="utf-8")
    (x / "run1.call1.primary_extract.raw.txt").write_text(raw, encoding="utf-8")
    run = {"cv": "DE_01_Klassisch.pdf", "tag": "run1", "kind": "measured", "ok": ok, "error": None,
           "llm_calls": [{"chat_kwargs": {"temperature": temp}, "llama_effective": {"seed": seed}}]}
    (d / label / "session.json").write_text(json.dumps({
        "label": label, "repo_commit": "c" * 40, "mode": "import",
        "variant": {"spec": spec, "max_tokens": None, "thinking": "off"},
        "llama": {"llama_cpp_python_version": "0.3.35"}, "model": {"sha256": "m"}, "runs": [run]}), encoding="utf-8")
    return d / label


def test_spec_check_identical_and_raw_deviation(tmp_path):
    base = _mk_spec(tmp_path, "8b-base", '{"a":1}')
    good = _mk_spec(tmp_path, "8b-spec-ok", '{"a":1}', spec="prompt-lookup")
    bad = _mk_spec(tmp_path, "8b-spec-bad", '{"a":2}', spec="prompt-lookup")   # parsed same, raw differs
    assert h.main(["spec-check", str(base), str(good)]) == 0
    assert h.main(["spec-check", str(base), str(bad)]) == 4
    s = json.loads((bad / "session.json").read_text(encoding="utf-8"))
    assert s["spec_identity_check"]["label"] == h.SPEC_DEFECT_LABEL
    assert s["spec_identity_check"]["speed_gain_counted"] is False
    assert h.speed_gain_status(s) is False
    assert h.speed_gain_status(json.loads((good / "session.json").read_text(encoding="utf-8"))) is True


def test_spec_check_flags_seed_temperature_and_failed_run(tmp_path):
    base = _mk_spec(tmp_path, "b", "r")
    assert not h.spec_identity_check(base, _mk_spec(tmp_path, "s1", "r", spec="prompt-lookup", seed=1))["ok"]
    assert not h.spec_identity_check(base, _mk_spec(tmp_path, "s2", "r", spec="prompt-lookup", temp=0.7))["ok"]
    assert not h.spec_identity_check(base, _mk_spec(tmp_path, "s3", "r", spec="prompt-lookup", ok=False))["ok"]
    u = _mk_spec(tmp_path, "s4", "r", spec="prompt-lookup")
    assert h.speed_gain_status(json.loads((u / "session.json").read_text(encoding="utf-8"))) == "unchecked"


# ---------------------------------------------------------------- power state consistency (Kritiker)
BAL = {"scheme_guid": "381b4222-f694-41f0-9685-ff5bb260df2e", "scheme_name": "Ausbalanciert", "scheme_source": "mock"}
AC = {"ac_online": True, "battery_percent": 100, "ac_source": "mock"}


def _readers(seq):
    """seq: list of (scheme, ac) dicts returned one per sample."""
    it = iter(seq)
    cur = {}

    def rs():
        cur["v"] = next(it)
        return dict(cur["v"][0])

    def ra():
        return dict(cur["v"][1])
    return rs, ra


def test_parse_powercfg_de_en():
    assert h.parse_powercfg_active("GUID des Energieschemas: 381b4222-f694-41f0-9685-ff5bb260df2e  (Ausbalanciert)") == \
        ("381b4222-f694-41f0-9685-ff5bb260df2e", "Ausbalanciert")
    assert h.parse_powercfg_active("Power Scheme GUID: 8C5E7FDA-E8BF-4A96-9A85-A6E23A8C635C  (High performance) *") == \
        ("8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c", "High performance")
    assert h.parse_powercfg_active("") == (None, None)


def test_power_guard_consistent_and_battery_drift_ok():
    g = h.PowerGuard("on", None, "", readers=_readers([(BAL, AC), (BAL, {**AC, "battery_percent": 99}), (BAL, AC)]))
    assert g.sample("variant start") == [] and g.sample("before EN_01") == [] and g.sample("variant end") == []
    assert g.consistent is True and g.record()["power_state_consistent"] is True


def test_power_guard_flags_scheme_change_and_ac_loss():
    hp = {**BAL, "scheme_guid": "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c", "scheme_name": "Höchstleistung"}
    g = h.PowerGuard("on", None, "", readers=_readers([(BAL, AC), (hp, AC)]))
    g.sample("variant start")
    probs = g.sample("before DE_02")
    assert any("scheme_guid changed" in p for p in probs) and g.consistent is False
    g2 = h.PowerGuard("on", {**BAL, **AC}, "ref.json", readers=_readers([(BAL, {**AC, "ac_online": False})]))
    assert any("AC not connected" in p for p in g2.sample("variant start")) and g2.consistent is False
    # record mode (box / non-Windows): problems are recorded, no abort, verdict None
    g3 = h.PowerGuard("record", None, "", readers=_readers([({"scheme_guid": None, "scheme_name": None},
                                                             {"ac_online": None})]))
    assert g3.sample("variant start") == [] and g3.consistent is None and g3.problems


def test_power_ref_mismatch_against_session_start():
    ref = {**BAL, **AC}
    assert h.power_problems(ref, {**BAL, **AC, "battery_percent": 97}) == []
    assert any("scheme_name changed" in p for p in h.power_problems(ref, {**BAL, **AC, "scheme_name": "Balanced"}))


def test_summarize_flags_inconsistent_power(tmp_path, capsys):
    good = _mk_spec(tmp_path, "base", "r")
    bad = _mk_spec(tmp_path, "var", "r")
    for d, psc, ref in ((good, True, {**BAL, **AC}), (bad, False, {**BAL, **AC})):
        s = json.loads((d / "session.json").read_text(encoding="utf-8"))
        s["summary"] = h.summarize_session(s)
        s["power_state_consistent"] = psc
        s["model"]["path"] = "Qwen3.5-4B-Q4_K_M.gguf"
        s["power"] = {"reference": ref, "problems": [] if psc else [{"where": "before DE_02", "problems": ["x"]}]}
        (d / "session.json").write_text(json.dumps(s), encoding="utf-8")
    csv_p = tmp_path / "s.csv"
    assert h.main(["summarize", str(good), str(bad), "--csv", str(csv_p)]) == 0
    assert "var: power_state_consistent=False" in capsys.readouterr().out
    rows = csv_p.read_text(encoding="utf-8").splitlines()
    hdr = rows[0].split(",")
    i = hdr.index("power_state_consistent")
    assert [r.split(",")[i] for r in rows[1:]] == ["True", "False"]


def test_scripts_never_change_power_plan():
    import re
    root = Path(__file__).resolve().parents[1]
    for f in ("thinkpad_cv_bench.py", "thinkpad_peak_raw.py", "run_cv_matrix.ps1"):
        for line in (root / f).read_text(encoding="utf-8").splitlines():
            if re.search(r"powercfg", line, re.I) and not line.lstrip().startswith("#"):
                assert re.search(r"(/|-)(setactive|s\b|change|x\b|set(ac|dc)valueindex|duplicatescheme|import|delete)",
                                 line, re.I) is None, line


# --- privacy: result JSON must never carry the machine name (Teamlead decision 2026-10-19)
import importlib  # noqa: E402
import platform  # noqa: E402

import pytest  # noqa: E402

_HOST_SENTINEL = "SHOULD-NOT-APPEAR"


@pytest.mark.parametrize("modname", ["thinkpad_cv_bench", "thinkpad_speed_bench"])
def test_system_info_hostname_is_placeholder(modname, monkeypatch):
    mod = importlib.import_module(modname)
    monkeypatch.setattr(platform, "node", lambda: _HOST_SENTINEL)
    monkeypatch.setattr(mod.psutil, "cpu_percent", lambda *a, **k: 0.0)  # skip the 1 s sample
    info = mod.system_info()
    assert info["hostname"] == "<HOSTNAME>"
    assert _HOST_SENTINEL not in json.dumps(info, default=str)


@pytest.mark.parametrize("fname", ["thinkpad_cv_bench.py", "thinkpad_speed_bench.py"])
def test_bench_sources_do_not_call_platform_node(fname):
    src = (Path(__file__).resolve().parents[1] / fname).read_text(encoding="utf-8")
    assert "platform.node(" not in src
