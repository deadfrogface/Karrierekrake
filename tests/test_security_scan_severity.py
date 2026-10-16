"""Regression checks for fail-closed vulnerability scan classification."""
from scripts.run_security_scans import _osv_max_score


def test_unknown_osv_severity_requires_review():
    assert _osv_max_score({"id": "GHSA-example", "severity": []}) >= 7.0


def test_unparsed_cvss_vector_requires_review():
    assert _osv_max_score({
        "severity": [{"type": "CVSS_V3", "score": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:L/I:L/A:L"}]
    }) >= 7.0


def test_explicit_low_severity_is_not_misclassified():
    assert _osv_max_score({"database_specific": {"severity": "LOW"}}) == 2.0


def test_explicit_high_severity_is_blocking():
    assert _osv_max_score({"database_specific": {"severity": "HIGH"}}) >= 7.0


def test_runtime_freeze_includes_diskcache(monkeypatch, tmp_path):
    """Shipped llama-cpp dependency must remain visible to OSV scanning."""
    from scripts import run_security_scans as scans
    monkeypatch.setattr(scans.subprocess, "check_output", lambda *args, **kwargs: (
        "pip==24.0\\ndiskcache==5.6.3\\nllama-cpp-python==0.3.0\\npytest==8.0\\n"
    ))
    output = scans._write_runtime_freeze(tmp_path / "freeze.txt").read_text(encoding="utf-8")
    assert "diskcache==5.6.3" in output
    assert "llama-cpp-python==0.3.0" in output
    assert "pytest==" not in output
