import pytest
from core.commercial.growth_scenarios import example_scenarios, gross_order_value


def test_documented_scenarios_are_reproducible():
    assert example_scenarios() == {"conservative": "20.00", "medium": "500.00", "optimistic": "8000.00"}


@pytest.mark.parametrize("share", ["-0.1", "1.01", "NaN", "Infinity"])
def test_invalid_conversion_rejected(share):
    with pytest.raises(ValueError):
        gross_order_value(100, share, "10")
