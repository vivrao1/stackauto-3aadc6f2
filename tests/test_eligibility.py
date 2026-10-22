from datetime import date

import pytest

from mortgage_agent.eligibility import (
    evaluate_all_schemes,
    evaluate_scheme,
    max_loan_for_payment,
    monthly_principal_and_interest,
)
from mortgage_agent.models import Applicant, LoanScheme
from mortgage_agent.rates import RateSnapshot


def make_snapshot(cash_rate=3.60):
    return RateSnapshot(cash_rate, date(2025, 8, 1), source="test", is_live=False)


def make_applicant(**overrides):
    defaults = dict(
        annual_income=110_000,
        monthly_living_expenses=2_000,
        monthly_other_debts=200,
        deposit=40_000,
        home_price=600_000,
        state="NSW",
    )
    defaults.update(overrides)
    return Applicant(**defaults)


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


def test_strong_applicant_is_eligible_for_standard_loan():
    applicant = make_applicant(annual_income=180_000, deposit=150_000, home_price=600_000)
    result = evaluate_scheme(applicant, make_snapshot(), LoanScheme.STANDARD)
    assert result.eligible is True
    assert result.requires_lmi is False


def test_standard_loan_requires_lmi_above_80_percent_lvr():
    applicant = make_applicant(annual_income=180_000, deposit=40_000, home_price=600_000)  # LVR ~93%
    result = evaluate_scheme(applicant, make_snapshot(), LoanScheme.STANDARD)
    assert result.requires_lmi is True
    assert result.estimated_lmi_premium > 0


def test_deposit_below_minimum_fails_lvr_check():
    applicant = make_applicant(deposit=5_000, home_price=600_000)  # LVR ~99%, above 95% max
    result = evaluate_scheme(applicant, make_snapshot(), LoanScheme.FIRST_HOME_GUARANTEE)
    assert result.eligible is False
    assert any("Deposit" in r for r in result.reasons)


def test_first_home_guarantee_waives_lmi_for_eligible_applicant():
    applicant = make_applicant(
        annual_income=120_000, deposit=60_000, home_price=500_000, is_first_home_buyer=True
    )
    result = evaluate_scheme(applicant, make_snapshot(), LoanScheme.FIRST_HOME_GUARANTEE)
    assert result.eligible is True
    assert result.requires_lmi is False


def test_first_home_guarantee_rejects_over_income_cap():
    applicant = make_applicant(annual_income=150_000, is_couple=False)  # single cap is 125,000
    result = evaluate_scheme(applicant, make_snapshot(), LoanScheme.FIRST_HOME_GUARANTEE)
    assert result.eligible is False
    assert any("income" in r.lower() for r in result.reasons)


def test_first_home_guarantee_couple_uses_higher_income_cap():
    applicant = make_applicant(annual_income=180_000, is_couple=True)  # couple cap is 200,000
    result = evaluate_scheme(applicant, make_snapshot(), LoanScheme.FIRST_HOME_GUARANTEE)
    assert not any("income" in r.lower() for r in result.reasons)


def test_first_home_guarantee_rejects_over_price_cap():
    applicant = make_applicant(home_price=1_000_000, deposit=60_000, state="NSW", is_regional=False)
    result = evaluate_scheme(applicant, make_snapshot(), LoanScheme.FIRST_HOME_GUARANTEE)
    assert result.eligible is False
    assert any("Property price" in r for r in result.reasons)


def test_regional_guarantee_requires_regional_property():
    applicant = make_applicant(is_regional=False)
    result = evaluate_scheme(applicant, make_snapshot(), LoanScheme.REGIONAL_FIRST_HOME_GUARANTEE)
    assert result.eligible is False
    assert any("Regional" in r for r in result.reasons)

    applicant.is_regional = True
    result = evaluate_scheme(applicant, make_snapshot(), LoanScheme.REGIONAL_FIRST_HOME_GUARANTEE)
    assert not any("Regional" in r for r in result.reasons)


def test_family_home_guarantee_requires_single_parent_and_allows_98_percent_lvr():
    applicant = make_applicant(annual_income=120_000, deposit=10_000, home_price=500_000, is_single_parent=False)
    result = evaluate_scheme(applicant, make_snapshot(), LoanScheme.FAMILY_HOME_GUARANTEE)
    assert result.eligible is False
    assert any("single parent" in r.lower() for r in result.reasons)

    applicant.is_single_parent = True
    result = evaluate_scheme(applicant, make_snapshot(), LoanScheme.FAMILY_HOME_GUARANTEE)
    assert result.eligible is True  # 10,000 / 500,000 = 2% deposit, within the 98% LVR max


def test_citizenship_and_owner_occupier_requirements_for_guarantee_schemes():
    applicant = make_applicant(is_australian_citizen_or_pr=False)
    result = evaluate_scheme(applicant, make_snapshot(), LoanScheme.FIRST_HOME_GUARANTEE)
    assert result.eligible is False
    assert any("citizen" in r.lower() for r in result.reasons)

    applicant = make_applicant(is_owner_occupier=False)
    result = evaluate_scheme(applicant, make_snapshot(), LoanScheme.FIRST_HOME_GUARANTEE)
    assert result.eligible is False
    assert any("owner-occupied" in r.lower() for r in result.reasons)


def test_insufficient_serviceability_fails_regardless_of_scheme():
    applicant = make_applicant(
        annual_income=45_000,
        monthly_living_expenses=3_000,
        monthly_other_debts=800,
        deposit=100_000,
        home_price=600_000,
    )
    result = evaluate_scheme(applicant, make_snapshot(), LoanScheme.STANDARD)
    assert result.eligible is False
    assert any("assessed rate" in r.lower() for r in result.reasons)


def test_high_loan_to_income_ratio_adds_a_warning_without_failing():
    applicant = make_applicant(annual_income=400_000, deposit=400_000, home_price=3_200_000)
    result = evaluate_scheme(applicant, make_snapshot(), LoanScheme.STANDARD)
    assert any("loan-to-income" in r.lower() for r in result.reasons)


def test_evaluate_all_schemes_returns_one_result_per_scheme():
    applicant = make_applicant()
    results = evaluate_all_schemes(applicant, make_snapshot())
    assert {r.scheme for r in results} == set(LoanScheme)


def test_unknown_state_is_rejected():
    with pytest.raises(ValueError):
        make_applicant(state="XX")
