"""Australian first home buyer loan scheme eligibility and serviceability math.

Scheme thresholds (income caps, property price caps, max LVR) reflect the
Australian Government's Home Guarantee Scheme (First Home Guarantee,
Regional First Home Buyer Guarantee, Family Home Guarantee) as
administered by Housing Australia. These caps are reviewed periodically
by government and WILL change -- POLICY_SNAPSHOT_DATE records when these
figures were last checked; verify current settings at
housingaustralia.gov.au before relying on this for a real purchase.

Serviceability uses APRA's mandated minimum interest rate buffer (current
rate + 3 percentage points) applied to standard loan amortization. This
mirrors, but simplifies, the bank-specific calculators lenders actually
use, which also apply the HEM living-expense benchmark and proprietary
risk scoring.
"""

from __future__ import annotations

from datetime import date

from mortgage_agent.models import Applicant, LoanScheme, SchemeResult
from mortgage_agent.rates import RateSnapshot
from mortgage_agent.tax import estimate_net_monthly_income

POLICY_SNAPSHOT_DATE = date(2025, 7, 1)

APRA_SERVICEABILITY_BUFFER_PERCENT = 3.0
HIGH_LOAN_TO_INCOME_RATIO = 6.0

# Household income caps for the Home Guarantee Scheme (annual, gross).
FHBG_INCOME_CAP_SINGLE = 125_000
FHBG_INCOME_CAP_COUPLE = 200_000
FAMILY_HOME_INCOME_CAP = 125_000  # single parent / legal guardian applicants only

MAX_LVR_STANDARD = 95.0
MAX_LVR_GUARANTEE = 95.0
MAX_LVR_FAMILY_HOME_GUARANTEE = 98.0

# Indicative property price caps ($AUD) under the Home Guarantee Scheme,
# split by capital city vs. rest-of-state. Must be checked against the
# current Housing Australia caps for the applicant's specific region.
PRICE_CAPS = {
    "NSW": {"capital": 900_000, "regional": 750_000},
    "VIC": {"capital": 800_000, "regional": 650_000},
    "QLD": {"capital": 700_000, "regional": 550_000},
    "WA": {"capital": 600_000, "regional": 450_000},
    "SA": {"capital": 600_000, "regional": 450_000},
    "TAS": {"capital": 600_000, "regional": 450_000},
    "ACT": {"capital": 750_000, "regional": 750_000},
    "NT": {"capital": 600_000, "regional": 600_000},
}

# Rough LMI premium as a percentage of the loan amount, by LVR band.
# Actual premiums vary by lender, insurer, and loan size.
LMI_PREMIUM_BANDS = [  # (max LVR inclusive, premium % of loan)
    (85.0, 1.0),
    (90.0, 1.8),
    (95.0, 3.5),
    (100.0, 4.5),
]


def price_cap_for(state: str, is_regional: bool) -> float:
    caps = PRICE_CAPS[state]
    return caps["regional"] if is_regional else caps["capital"]


def estimate_lmi_premium(loan_amount: float, lvr_percent: float) -> float:
    for max_lvr, premium_percent in LMI_PREMIUM_BANDS:
        if lvr_percent <= max_lvr:
            return loan_amount * premium_percent / 100
    return loan_amount * LMI_PREMIUM_BANDS[-1][1] / 100


def monthly_principal_and_interest(loan_amount: float, annual_rate_percent: float, term_years: int = 30) -> float:
    """Standard amortizing loan payment formula."""
    if loan_amount <= 0:
        return 0.0
    monthly_rate = annual_rate_percent / 100 / 12
    num_payments = term_years * 12
    if monthly_rate == 0:
        return loan_amount / num_payments
    factor = (1 + monthly_rate) ** num_payments
    return loan_amount * monthly_rate * factor / (factor - 1)


def max_loan_for_payment(max_monthly_payment: float, annual_rate_percent: float, term_years: int = 30) -> float:
    """Inverse of monthly_principal_and_interest: largest loan a given payment supports."""
    if max_monthly_payment <= 0:
        return 0.0
    monthly_rate = annual_rate_percent / 100 / 12
    num_payments = term_years * 12
    if monthly_rate == 0:
        return max_monthly_payment * num_payments
    factor = (1 + monthly_rate) ** num_payments
    return max_monthly_payment * (factor - 1) / (monthly_rate * factor)


def evaluate_scheme(applicant: Applicant, snapshot: RateSnapshot, scheme: LoanScheme) -> SchemeResult:
    reasons: list[str] = []
    eligible = True

    rate = snapshot.variable_rate_percent
    loan_amount = applicant.loan_amount
    lvr = applicant.lvr_percent

    if scheme == LoanScheme.FAMILY_HOME_GUARANTEE:
        max_lvr = MAX_LVR_FAMILY_HOME_GUARANTEE
    elif scheme in (LoanScheme.FIRST_HOME_GUARANTEE, LoanScheme.REGIONAL_FIRST_HOME_GUARANTEE):
        max_lvr = MAX_LVR_GUARANTEE
    else:
        max_lvr = MAX_LVR_STANDARD

    if lvr > max_lvr + 1e-9:
        eligible = False
        min_deposit_percent = 100 - max_lvr
        reasons.append(
            f"Deposit of {applicant.deposit_percent:.1f}% is below the minimum "
            f"{min_deposit_percent:.1f}% required (LVR would be {lvr:.1f}%)."
        )

    requires_lmi = False
    estimated_lmi_premium = None

    if scheme == LoanScheme.STANDARD:
        if lvr > 80.0:
            requires_lmi = True
            estimated_lmi_premium = round(estimate_lmi_premium(loan_amount, lvr), 2)
    else:
        # Home Guarantee Scheme products waive LMI for eligible borrowers.
        if scheme != LoanScheme.FAMILY_HOME_GUARANTEE and not applicant.is_first_home_buyer:
            eligible = False
            reasons.append("This guarantee requires the applicant to be a first home buyer.")
        if not applicant.is_owner_occupier:
            eligible = False
            reasons.append("The property must be owner-occupied, not an investment.")
        if not applicant.is_australian_citizen_or_pr:
            eligible = False
            reasons.append("Applicant must be an Australian citizen or permanent resident.")

        if scheme == LoanScheme.REGIONAL_FIRST_HOME_GUARANTEE and not applicant.is_regional:
            eligible = False
            reasons.append("The Regional First Home Buyer Guarantee requires a regional property.")

        if scheme == LoanScheme.FAMILY_HOME_GUARANTEE:
            if not applicant.is_single_parent:
                eligible = False
                reasons.append("The Family Home Guarantee requires a single parent or legal guardian.")
            income_cap = FAMILY_HOME_INCOME_CAP
        else:
            income_cap = FHBG_INCOME_CAP_COUPLE if applicant.is_couple else FHBG_INCOME_CAP_SINGLE

        if applicant.annual_income > income_cap:
            eligible = False
            reasons.append(
                f"Household income ${applicant.annual_income:,.0f} exceeds the "
                f"${income_cap:,.0f} cap for this scheme."
            )

        price_cap = price_cap_for(applicant.state, applicant.is_regional)
        if applicant.home_price > price_cap:
            eligible = False
            region = "regional" if applicant.is_regional else "capital city"
            reasons.append(
                f"Property price ${applicant.home_price:,.0f} exceeds the indicative "
                f"${price_cap:,.0f} cap for {applicant.state} ({region})."
            )

    # Serviceability: APRA buffer rate applied to the actual proposed loan.
    assessed_rate = rate + APRA_SERVICEABILITY_BUFFER_PERCENT
    monthly_repayment = monthly_principal_and_interest(loan_amount, rate)
    assessed_monthly_repayment = monthly_principal_and_interest(loan_amount, assessed_rate)

    net_monthly_income = estimate_net_monthly_income(applicant.annual_income)
    available_monthly = net_monthly_income - applicant.monthly_living_expenses - applicant.monthly_other_debts
    monthly_surplus_at_assessed_rate = available_monthly - assessed_monthly_repayment

    if monthly_surplus_at_assessed_rate < 0:
        eligible = False
        reasons.append(
            f"Estimated repayment at the assessed rate of {assessed_rate:.2f}% "
            f"(actual rate + {APRA_SERVICEABILITY_BUFFER_PERCENT:.1f}pp APRA buffer) "
            f"exceeds income after living expenses and other debts by "
            f"${-monthly_surplus_at_assessed_rate:,.2f}/month."
        )

    loan_to_income_ratio = loan_amount / applicant.annual_income if applicant.annual_income > 0 else None
    if loan_to_income_ratio is not None and loan_to_income_ratio > HIGH_LOAN_TO_INCOME_RATIO:
        reasons.append(
            f"Loan-to-income ratio of {loan_to_income_ratio:.1f}x exceeds "
            f"{HIGH_LOAN_TO_INCOME_RATIO:.0f}x gross income; lenders often apply extra "
            f"scrutiny or caps above this level."
        )

    max_affordable_loan = max_loan_for_payment(max(available_monthly, 0.0), assessed_rate)
    max_affordable_home_price = round(max_affordable_loan + applicant.deposit, 2)

    return SchemeResult(
        scheme=scheme,
        eligible=eligible,
        reasons=reasons,
        interest_rate_percent=round(rate, 3),
        loan_amount=loan_amount,
        lvr_percent=round(lvr, 2),
        requires_lmi=requires_lmi,
        estimated_lmi_premium=estimated_lmi_premium,
        monthly_repayment=round(monthly_repayment, 2),
        assessed_monthly_repayment=round(assessed_monthly_repayment, 2),
        monthly_surplus_at_assessed_rate=round(monthly_surplus_at_assessed_rate, 2),
        loan_to_income_ratio=round(loan_to_income_ratio, 2) if loan_to_income_ratio is not None else None,
        max_affordable_home_price=max_affordable_home_price,
    )


def evaluate_all_schemes(applicant: Applicant, snapshot: RateSnapshot) -> list[SchemeResult]:
    return [evaluate_scheme(applicant, snapshot, scheme) for scheme in LoanScheme]
