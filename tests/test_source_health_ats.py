"""Unit tests for source health classification and ATS coverage helpers."""

from apply.detector import ATSDetector, ats_coverage_bucket, classify_ats_support
from core.source_health import SourceHealthStatus


def test_source_health_empty_vs_results():
    assert (
        SourceHealthStatus.from_outcome(jobs_found=12, source_id="indeed")
        == SourceHealthStatus.OK_WITH_RESULTS
    )
    assert (
        SourceHealthStatus.from_outcome(jobs_found=0, source_id="stepstone")
        == SourceHealthStatus.OK_EMPTY
    )
    assert (
        SourceHealthStatus.from_outcome(jobs_found=0, source_id="company_sites")
        == SourceHealthStatus.OK_EMPTY
    )


def test_source_health_timeout_and_network():
    assert (
        SourceHealthStatus.from_outcome(jobs_found=0, error="Timeout after 120s")
        == SourceHealthStatus.TIMEOUT
    )
    assert (
        SourceHealthStatus.from_outcome(
            jobs_found=0, error="connection refused", detail_stage="network"
        )
        == SourceHealthStatus.NETWORK_ERROR
    )


def test_ats_detect_extended():
    assert ATSDetector.detect("https://jobs.ashbyhq.com/acme/123") == "ashby"
    assert ATSDetector.detect("https://acme.bamboohr.com/careers") == "bamboohr"
    assert ATSDetector.detect("https://unknown.example/jobs/1") == "unknown"


def test_ats_classify_and_buckets():
    support, note = classify_ats_support("greenhouse", "https://boards.greenhouse.io/x")
    assert support == "supported"
    support, note = classify_ats_support("personio", "https://acme.jobs.personio.de/job/1")
    assert support == "partially_supported"
    assert "teilweise" in note.lower() or "partial" in note.lower()
    support, note = classify_ats_support("bamboohr", "https://x.bamboohr.com")
    assert support == "known_unsupported"
    assert "manuell" in note.lower() or "manual" in note.lower()
    assert ats_coverage_bucket("unknown") == "unknown"
    assert ats_coverage_bucket("greenhouse") == "supported"
    assert ats_coverage_bucket("personio") == "partially_supported"
    assert ats_coverage_bucket("taleo") == "detected_unsupported"
