import pytest

from mortgage_agent.tax import estimate_annual_tax, estimate_net_monthly_income


def test_tax_on_45000_matches_published_bracket_value():
    # Known 2024-25 resident tax (excl. Medicare levy) on $45,000 taxable income is $4,288.
    tax_excl_medicare = estimate_annual_tax(45_000) - 45_000 * 0.02
    assert tax_excl_medicare == pytest.approx(4_288, abs=0.5)


def test_tax_on_135000_matches_published_bracket_value():
    # Known 2024-25 resident tax (excl. Medicare levy) on $135,000 taxable income is $31,288.
    tax_excl_medicare = estimate_annual_tax(135_000) - 135_000 * 0.02
    assert tax_excl_medicare == pytest.approx(31_288, abs=0.5)


def test_tax_free_threshold_has_no_income_tax_component():
    # Below $18,200 there's no income tax, but this simplified model still
    # applies the flat 2% Medicare levy (it ignores the low-income levy
    # reduction/exemption by design -- see module docstring).
    income_tax_only = estimate_annual_tax(15_000) - 15_000 * 0.02
    assert income_tax_only == pytest.approx(0.0)


def test_net_monthly_income_is_less_than_gross_monthly():
    gross_monthly = 100_000 / 12
    assert estimate_net_monthly_income(100_000) < gross_monthly


def test_zero_income_has_zero_tax():
    assert estimate_annual_tax(0) == 0.0
