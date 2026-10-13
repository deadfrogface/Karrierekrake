"""Deterministic growth sensitivity calculator; scenarios are assumptions, not forecasts."""
from __future__ import annotations

from decimal import Decimal


def gross_order_value(users: int, conversion: str, monthly_price_eur: str) -> Decimal:
    if type(users) is not int or users < 0:
        raise ValueError("invalid_user_count")
    share = Decimal(str(conversion))
    price = Decimal(str(monthly_price_eur))
    if not share.is_finite() or not price.is_finite() or not 0 <= share <= 1 or price < 0:
        raise ValueError("invalid_assumption")
    return (Decimal(users) * share * price).quantize(Decimal("0.01"))


def example_scenarios() -> dict[str, str]:
    return {
        "conservative": str(gross_order_value(100, "0.02", "10")),
        "medium": str(gross_order_value(1000, "0.05", "10")),
        "optimistic": str(gross_order_value(10000, "0.08", "10")),
    }
