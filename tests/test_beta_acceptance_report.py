import pytest
from scripts.beta_acceptance_report import validate


def test_beta_result_sanitizes_extra_data():
    assert validate({"test_id": "B01", "status": "pass", "email": "private@example.org"}) == {"test_id": "B01", "status": "pass"}


@pytest.mark.parametrize("test_id", ["B00", "B11", "../B01"])
def test_beta_result_rejects_unknown_test(test_id):
    with pytest.raises(ValueError):
        validate({"test_id": test_id, "status": "pass"})


def test_beta_result_rejects_unknown_status():
    with pytest.raises(ValueError):
        validate({"test_id": "B01", "status": "pretend_pass"})
