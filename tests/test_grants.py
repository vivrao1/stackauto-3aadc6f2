import pytest

from mortgage_agent.grants import estimate_fhog


def test_nsw_new_home_under_cap_is_eligible():
    result = estimate_fhog("NSW", is_new_home=True, home_price=500_000)
    assert result.eligible is True
    assert result.amount == 10_000


def test_nsw_established_home_is_ineligible():
    result = estimate_fhog("NSW", is_new_home=False, home_price=500_000)
    assert result.eligible is False
    assert result.amount == 0


def test_price_over_cap_is_ineligible():
    result = estimate_fhog("NSW", is_new_home=True, home_price=900_000)
    assert result.eligible is False


def test_act_has_no_grant():
    result = estimate_fhog("ACT", is_new_home=True, home_price=400_000)
    assert result.eligible is False
    assert result.amount == 0


def test_nt_allows_established_homes():
    result = estimate_fhog("NT", is_new_home=False, home_price=400_000)
    assert result.eligible is True


def test_unknown_state_raises():
    with pytest.raises(ValueError):
        estimate_fhog("XX", is_new_home=True, home_price=400_000)
