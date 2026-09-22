"""First-time home buyer loan eligibility rules and affordability math.

Program thresholds (minimum credit score, minimum down payment, max DTI)
reflect commonly published agency guidelines (HUD/FHA handbook, Fannie
Mae Conventional 97, VA lending guidelines, USDA Rural Development). Actual
lender overlays vary; treat results as an estimate, not a loan commitment.
"""

from __future__ import annotations

from dataclasses import dataclass

from mortgage_agent.models import Applicant, LoanProgram, ProgramResult
from mortgage_agent.rates import RateSnapshot


@dataclass(frozen=True)
class ProgramRules:
    program: LoanProgram
    min_credit_score: int
    min_down_payment_percent: float
    max_front_end_dti_percent: float
    max_back_end_dti_percent: float
    requires_veteran: bool = False
    requires_rural: bool = False
    requires_income_limit_check: bool = False


PROGRAM_RULES: dict[LoanProgram, ProgramRules] = {
    LoanProgram.CONVENTIONAL_97: ProgramRules(
        program=LoanProgram.CONVENTIONAL_97,
        min_credit_score=620,
        min_down_payment_percent=3.0,
        max_front_end_dti_percent=36.0,
        max_back_end_dti_percent=45.0,
    ),
    LoanProgram.FHA: ProgramRules(
        program=LoanProgram.FHA,
        min_credit_score=580,
        min_down_payment_percent=3.5,
        max_front_end_dti_percent=31.0,
        max_back_end_dti_percent=43.0,
    ),
    LoanProgram.VA: ProgramRules(
        program=LoanProgram.VA,
        min_credit_score=580,
        min_down_payment_percent=0.0,
        max_front_end_dti_percent=100.0,  # VA has no fixed front-end cap
        max_back_end_dti_percent=41.0,
        requires_veteran=True,
    ),
    LoanProgram.USDA: ProgramRules(
        program=LoanProgram.USDA,
        min_credit_score=640,
        min_down_payment_percent=0.0,
        max_front_end_dti_percent=29.0,
        max_back_end_dti_percent=41.0,
        requires_rural=True,
        requires_income_limit_check=True,
    ),
}

# FHA allows a lower down payment (10%) with credit scores between 500-579.
FHA_LOW_SCORE_MIN = 500
FHA_LOW_SCORE_MIN_DOWN_PERCENT = 10.0

# USDA's income limit is 115% of the area median income for the household size.
USDA_INCOME_LIMIT_MULTIPLIER = 1.15


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


def evaluate_program(applicant: Applicant, snapshot: RateSnapshot, program: LoanProgram) -> ProgramResult:
    rules = PROGRAM_RULES[program]
    reasons: list[str] = []
    needs_verification = False

    min_down_percent = rules.min_down_payment_percent
    if program == LoanProgram.FHA and FHA_LOW_SCORE_MIN <= applicant.credit_score < 580:
        min_down_percent = FHA_LOW_SCORE_MIN_DOWN_PERCENT

    eligible = True

    if rules.requires_veteran and not applicant.is_veteran:
        eligible = False
        reasons.append("VA loans require eligible veteran, service member, or surviving spouse status.")

    if rules.requires_rural and not applicant.is_rural_property:
        eligible = False
        reasons.append("USDA loans require the property to be in an eligible rural area.")

    min_score = FHA_LOW_SCORE_MIN if program == LoanProgram.FHA else rules.min_credit_score
    if applicant.credit_score < min_score:
        eligible = False
        reasons.append(
            f"Credit score {applicant.credit_score} is below the program minimum of {min_score}."
        )
    elif applicant.credit_score < rules.min_credit_score:
        reasons.append(
            f"Credit score {applicant.credit_score} qualifies only with a higher "
            f"{min_down_percent:.1f}% down payment."
        )

    if applicant.down_payment_percent < min_down_percent - 1e-9:
        eligible = False
        reasons.append(
            f"Down payment of {applicant.down_payment_percent:.1f}% is below the "
            f"required {min_down_percent:.1f}%."
        )

    if rules.requires_income_limit_check:
        needs_verification = True
        if applicant.area_median_income is not None:
            limit = applicant.area_median_income * USDA_INCOME_LIMIT_MULTIPLIER
            if applicant.annual_income > limit:
                eligible = False
                needs_verification = False
                reasons.append(
                    f"Household income {applicant.annual_income:,.0f} exceeds the USDA limit of "
                    f"115% of area median income ({limit:,.0f})."
                )
            else:
                needs_verification = False
        else:
            reasons.append(
                "USDA eligibility also requires household income at or below 115% of the "
                "area median income; provide area_median_income to verify."
            )

    interest_rate = snapshot.program_rate(program.value)
    loan_amount = applicant.loan_amount
    monthly_pi = monthly_principal_and_interest(loan_amount, interest_rate) if loan_amount > 0 else 0.0
    monthly_tax = applicant.home_price * applicant.annual_property_tax_rate / 12
    monthly_insurance = applicant.home_price * applicant.annual_insurance_rate / 12
    monthly_piti = monthly_pi + monthly_tax + monthly_insurance

    front_end_dti = back_end_dti = None
    max_affordable_home_price = None
    if applicant.monthly_income > 0:
        front_end_dti = monthly_piti / applicant.monthly_income * 100
        back_end_dti = (monthly_piti + applicant.monthly_debts) / applicant.monthly_income * 100

        if front_end_dti > rules.max_front_end_dti_percent + 1e-9:
            eligible = False
            reasons.append(
                f"Housing-expense ratio {front_end_dti:.1f}% exceeds the program's "
                f"{rules.max_front_end_dti_percent:.1f}% limit."
            )
        if back_end_dti > rules.max_back_end_dti_percent + 1e-9:
            eligible = False
            reasons.append(
                f"Total debt-to-income ratio {back_end_dti:.1f}% exceeds the program's "
                f"{rules.max_back_end_dti_percent:.1f}% limit."
            )

        max_monthly_piti_budget = min(
            applicant.monthly_income * rules.max_front_end_dti_percent / 100,
            applicant.monthly_income * rules.max_back_end_dti_percent / 100 - applicant.monthly_debts,
        )
        max_monthly_piti_budget = max(max_monthly_piti_budget, 0.0)
        tax_insurance_rate_monthly = (
            applicant.annual_property_tax_rate + applicant.annual_insurance_rate
        ) / 12
        # Solve for a home price P such that PI(loan=P-down) + P*tax_ins_rate == budget.
        # Approximate by first estimating a max loan from the full budget, then
        # correcting for the portion consumed by taxes/insurance on that price.
        max_loan_estimate = max_loan_for_payment(max_monthly_piti_budget, interest_rate)
        estimated_price = max_loan_estimate + applicant.down_payment
        for _ in range(5):
            piti_budget_for_pi = max_monthly_piti_budget - estimated_price * tax_insurance_rate_monthly
            piti_budget_for_pi = max(piti_budget_for_pi, 0.0)
            max_loan_estimate = max_loan_for_payment(piti_budget_for_pi, interest_rate)
            estimated_price = max_loan_estimate + applicant.down_payment
        max_affordable_home_price = round(max(estimated_price, 0.0), 2)

    return ProgramResult(
        program=program,
        eligible=eligible,
        needs_verification=needs_verification,
        reasons=reasons,
        interest_rate_percent=interest_rate,
        loan_amount=loan_amount,
        down_payment_percent=applicant.down_payment_percent,
        monthly_principal_interest=round(monthly_pi, 2) if monthly_pi is not None else None,
        monthly_piti=round(monthly_piti, 2) if monthly_piti is not None else None,
        front_end_dti_percent=round(front_end_dti, 2) if front_end_dti is not None else None,
        back_end_dti_percent=round(back_end_dti, 2) if back_end_dti is not None else None,
        max_affordable_home_price=max_affordable_home_price,
    )


def evaluate_all_programs(applicant: Applicant, snapshot: RateSnapshot) -> list[ProgramResult]:
    return [evaluate_program(applicant, snapshot, program) for program in LoanProgram]
