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
