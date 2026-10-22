"""Simplified Australian resident individual income tax estimate.

Uses the 2024-25 resident tax brackets (post Stage 3 cuts) plus the
standard 2% Medicare levy, to approximate take-home pay for a
serviceability estimate. It intentionally ignores the Medicare levy
low-income threshold/reduction, HECS-HELP repayments, private health
insurance surcharge, and other offsets -- it is not a payslip.
"""

from __future__ import annotations

# (bracket start, marginal rate applied to income within this bracket)
TAX_BRACKETS = [
    (0, 0.0),
    (18_200, 0.16),
    (45_000, 0.30),
    (135_000, 0.37),
    (190_000, 0.45),
]
MEDICARE_LEVY_RATE = 0.02


def estimate_annual_tax(gross_annual_income: float) -> float:
    income = max(gross_annual_income, 0.0)
    tax = 0.0
    for i, (threshold, rate) in enumerate(TAX_BRACKETS):
        if income <= threshold:
            break
        next_threshold = TAX_BRACKETS[i + 1][0] if i + 1 < len(TAX_BRACKETS) else float("inf")
        taxable_in_band = min(income, next_threshold) - threshold
        tax += taxable_in_band * rate
    return tax + income * MEDICARE_LEVY_RATE


def estimate_net_monthly_income(gross_annual_income: float) -> float:
    return (gross_annual_income - estimate_annual_tax(gross_annual_income)) / 12
