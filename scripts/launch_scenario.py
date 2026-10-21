"""12-month planning arithmetic. Inputs are assumptions, never revenue evidence.

Usage: python scripts/launch_scenario.py config/launch_scenario.example.json
Outputs JSON to stdout; does not query services or change application data.
"""
from __future__ import annotations
import argparse
from decimal import Decimal, ROUND_HALF_UP
import json
from pathlib import Path


def project(value):
    def number(key, rate=False):
        result = Decimal(str(value[key]))
        if not result.is_finite() or result < 0 or (rate and result > 1):
            raise ValueError('invalid_assumption:' + key)
        return result
    users = number('initial_users')
    growth = number('monthly_user_growth', True)
    conversion = number('premium_share', True)
    price = number('monthly_gross_price')
    tax = number('tax_rate', True)
    fee = number('provider_fee_rate', True)
    fixed_fee = number('provider_fixed_fee')
    refunds = number('refund_reserve_rate', True)
    support = number('support_cost_per_active_user')
    fixed = number('monthly_fixed_cost')
    cash = number('starting_cash') - number('one_time_cost')
    downloads = number('download_cost_per_new_user')
    sponsor = number('monthly_sponsor_revenue')
    def money(n):
        return str(n.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))
    rows = []
    for month in range(1, 13):
        previous = users
        if month > 1:
            users *= 1 + growth
        paid = users * conversion
        gross = paid * price
        net_sales = gross / (1 + tax)
        provider = gross * fee + paid * fixed_fee
        reserve = gross * refunds
        operating = fixed + users * support + max(Decimal(0), users - previous) * downloads
        contribution = net_sales - provider - reserve + sponsor - operating
        cash += contribution
        rows.append({'month': month, 'active_users': money(users), 'paid_users': money(paid),
                     'gross_sales': money(gross), 'sales_excluding_tax': money(net_sales),
                     'provider_cost': money(provider), 'refund_reserve': money(reserve),
                     'operating_cost': money(operating), 'sponsor_revenue': money(sponsor),
                     'monthly_balance': money(contribution), 'cash_balance': money(cash)})
    return {'status': 'ASSUMPTIONS_NOT_ACTUALS', 'currency': 'EUR', 'months': rows,
            'limitations': ['No tax or investment advice', 'No external fees verified',
                           'Premium share is a scenario, not a retention model',
                           'Payment timing and owner salary only included if entered in costs']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('assumptions', type=Path)
    args = parser.parse_args()
    print(json.dumps(project(json.loads(args.assumptions.read_text(encoding='utf-8'))), indent=2))


if __name__ == '__main__':
    main()
