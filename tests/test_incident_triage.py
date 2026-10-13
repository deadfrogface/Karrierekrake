import pytest
from core.security.incident_triage import incident_record


def test_incident_record_has_no_freeform_pii_fields():
    result = incident_record(severity="high", component="updater", release="Alpha-1.0")
    assert set(result) == {"schema", "severity", "component", "release", "created_utc", "status"}
    assert result["status"] == "open"


@pytest.mark.parametrize("release", ["../../private", "user@example.com", "line\nsecret"])
def test_incident_rejects_unsafe_identifiers(release):
    with pytest.raises(ValueError):
        incident_record(severity="low", component="other", release=release)
