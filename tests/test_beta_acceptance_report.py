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


def test_beta_summary_never_approves_incomplete_matrix():
    from scripts.beta_acceptance_report import summarize
    result = summarize([{"test_id": "B01", "status": "pass"}])
    assert result["approved"] is False
    assert result["not_tested"] == 9
    assert "B10" in result["missing_test_ids"]


def test_beta_summary_approves_only_all_ten_passes():
    from scripts.beta_acceptance_report import summarize
    rows = [{"test_id": f"B{i:02d}", "status": "pass"} for i in range(1, 11)]
    assert summarize(rows)["approved"] is True
    rows[-1]["status"] = "blocked"
    assert summarize(rows)["approved"] is False


def test_beta_summary_rejects_duplicate_case():
    from scripts.beta_acceptance_report import summarize
    with pytest.raises(ValueError, match="duplicate_test"):
        summarize([{"test_id": "B01", "status": "pass"}] * 2)
