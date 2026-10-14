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


def monthly_contribution(*, users: int, conversion: str, monthly_price_eur: str,
                         tax_share: str, payment_fee_share: str, fee_per_order: str,
                         refund_share: str, variable_cost_per_paid_user: str,
                         fixed_cost: str) -> dict[str, str]:
    """Explicit planning inputs, not current rates or a price recommendation.

    tax_share is the tax portion of the gross order value (not a VAT rate).
    No Maps/cloud cost is assumed for a local-first product.
    """
    gross = gross_order_value(users, conversion, monthly_price_eur)
    values = [Decimal(str(v)) for v in (tax_share, payment_fee_share, fee_per_order,
              refund_share, variable_cost_per_paid_user, fixed_cost)]
    if any(not value.is_finite() or value < 0 for value in values):
        raise ValueError('invalid_cost_assumption')
    tax, payment, fee, refund, variable, fixed = values
    if any(value > 1 for value in (tax, payment, refund)) or tax + refund > 1:
        raise ValueError('invalid_cost_share')
    paid = Decimal(users) * Decimal(str(conversion))
    deductions = gross * (tax + payment + refund) + paid * (fee + variable)
    def money(value):
        return str(value.quantize(Decimal('0.01')))
    return {'gross_order_value': money(gross), 'expected_paid_users': str(paid),
            'variable_deductions': money(deductions), 'fixed_cost': money(fixed),
            'monthly_contribution': money(gross - deductions - fixed)}
