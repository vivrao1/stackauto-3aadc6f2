from datetime import date

import pytest

from mortgage_agent.eligibility import (
    evaluate_all_programs,
    evaluate_program,
    max_loan_for_payment,
    monthly_principal_and_interest,
)
from mortgage_agent.models import Applicant, LoanProgram
from mortgage_agent.rates import RateSnapshot


def make_snapshot(rate=6.5):
    return RateSnapshot(rate, date(2024, 1, 1), source="test", is_live=False)


def test_monthly_principal_and_interest_matches_known_value():
    # $300,000 loan, 6% annual, 30 years -> ~$1798.65/mo (standard amortization table value)
    payment = monthly_principal_and_interest(300_000, 6.0, 30)
    assert payment == pytest.approx(1798.65, abs=0.5)


def test_max_loan_for_payment_is_inverse_of_payment_formula():
    loan = 250_000
    rate = 5.5
    payment = monthly_principal_and_interest(loan, rate)
    recovered_loan = max_loan_for_payment(payment, rate)
    assert recovered_loan == pytest.approx(loan, rel=1e-6)


def test_strong_applicant_is_eligible_for_conventional_97():
    applicant = Applicant(
        annual_income=120_000,
        monthly_debts=300,
        credit_score=740,
        down_payment=12_000,
        home_price=400_000,
    )
    result = evaluate_program(applicant, make_snapshot(), LoanProgram.CONVENTIONAL_97)
    assert result.eligible is True
    assert result.reasons == []
    assert result.monthly_piti > 0


def test_low_down_payment_fails_conventional_97():
    applicant = Applicant(
        annual_income=120_000,
        monthly_debts=300,
        credit_score=740,
        down_payment=1_000,  # well under 3%
        home_price=400_000,
    )
    result = evaluate_program(applicant, make_snapshot(), LoanProgram.CONVENTIONAL_97)
    assert result.eligible is False
    assert any("Down payment" in r for r in result.reasons)


def test_fha_allows_low_score_with_higher_down_payment():
    applicant = Applicant(
        annual_income=90_000,
        monthly_debts=200,
        credit_score=560,  # below 580, above 500
        down_payment=25_000,  # 10% of home price
        home_price=250_000,
    )
    result = evaluate_program(applicant, make_snapshot(), LoanProgram.FHA)
    assert result.eligible is True


def test_fha_rejects_score_below_500():
    applicant = Applicant(
        annual_income=90_000,
        monthly_debts=200,
        credit_score=480,
        down_payment=25_000,
        home_price=250_000,
    )
    result = evaluate_program(applicant, make_snapshot(), LoanProgram.FHA)
    assert result.eligible is False


def test_va_requires_veteran_status():
    applicant = Applicant(
        annual_income=90_000,
        monthly_debts=200,
        credit_score=650,
        down_payment=0,
        home_price=250_000,
        is_veteran=False,
    )
    result = evaluate_program(applicant, make_snapshot(), LoanProgram.VA)
    assert result.eligible is False
    assert any("veteran" in r.lower() for r in result.reasons)

    applicant.is_veteran = True
    result = evaluate_program(applicant, make_snapshot(), LoanProgram.VA)
    assert result.eligible is True


def test_usda_requires_rural_property_and_flags_income_verification():
    applicant = Applicant(
        annual_income=60_000,
        monthly_debts=100,
        credit_score=680,
        down_payment=0,
        home_price=180_000,
        is_rural_property=True,
    )
    result = evaluate_program(applicant, make_snapshot(), LoanProgram.USDA)
    assert result.needs_verification is True

    applicant.area_median_income = 70_000
    result = evaluate_program(applicant, make_snapshot(), LoanProgram.USDA)
    assert result.needs_verification is False
    assert result.eligible is True


def test_usda_income_over_limit_is_ineligible():
    applicant = Applicant(
        annual_income=100_000,
        monthly_debts=100,
        credit_score=680,
        down_payment=0,
        home_price=180_000,
        is_rural_property=True,
        area_median_income=70_000,  # limit = 80,500
    )
    result = evaluate_program(applicant, make_snapshot(), LoanProgram.USDA)
    assert result.eligible is False


def test_high_dti_fails_regardless_of_credit_and_down_payment():
    applicant = Applicant(
        annual_income=40_000,
        monthly_debts=1_500,  # already very high relative to income
        credit_score=780,
        down_payment=50_000,
        home_price=500_000,
    )
    result = evaluate_program(applicant, make_snapshot(), LoanProgram.CONVENTIONAL_97)
    assert result.eligible is False
    assert any("debt-to-income" in r.lower() for r in result.reasons)


def test_evaluate_all_programs_returns_one_result_per_program():
    applicant = Applicant(
        annual_income=100_000,
        monthly_debts=300,
        credit_score=700,
        down_payment=20_000,
        home_price=300_000,
    )
    results = evaluate_all_programs(applicant, make_snapshot())
    assert {r.program for r in results} == set(LoanProgram)
