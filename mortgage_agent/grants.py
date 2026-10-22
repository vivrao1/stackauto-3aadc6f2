"""Indicative First Home Owner Grant (FHOG) estimates by state.

FHOG is a one-off state-government grant (separate from the Commonwealth
Home Guarantee Scheme) typically limited to new or substantially
renovated homes below a price cap. Amounts, caps, and "new home" rules
are each set independently by the relevant state/territory revenue
office and are revised periodically -- treat this as a rough pointer,
not a quote. Verify directly with the applicant's state revenue office
before relying on it.
"""

from __future__ import annotations

from mortgage_agent.models import AU_STATES, GrantEstimate

POLICY_SNAPSHOT_NOTE = (
    "Figures are indicative as of this build and change periodically -- "
    "verify the current amount and rules with the state revenue office."
)

# amount: one-off grant ($AUD); price_cap: None means no price cap applied;
# new_home_only: whether the grant is restricted to new/substantially
# renovated homes (most states) vs. also covering established homes.
FHOG_RULES = {
    "NSW": {"amount": 10_000, "price_cap": 750_000, "new_home_only": True},
    "VIC": {"amount": 10_000, "price_cap": 750_000, "new_home_only": True},
    "QLD": {"amount": 30_000, "price_cap": 750_000, "new_home_only": True},
    "WA": {"amount": 10_000, "price_cap": 750_000, "new_home_only": True},
    "SA": {"amount": 15_000, "price_cap": 650_000, "new_home_only": True},
    "TAS": {"amount": 10_000, "price_cap": 750_000, "new_home_only": True},
    "ACT": {"amount": 0, "price_cap": None, "new_home_only": True},
    "NT": {"amount": 10_000, "price_cap": None, "new_home_only": False},
}


def estimate_fhog(state: str, is_new_home: bool, home_price: float) -> GrantEstimate:
    state = state.upper()
    if state not in AU_STATES:
        raise ValueError(f"Unknown state '{state}'; expected one of {sorted(AU_STATES)}")

    rules = FHOG_RULES[state]
    notes = [POLICY_SNAPSHOT_NOTE]

    if rules["amount"] == 0:
        notes.append(
            f"{state} does not currently offer a First Home Owner Grant "
            "(it may offer a stamp duty concession instead)."
        )
        return GrantEstimate(state=state, amount=0, eligible=False, notes=notes)

    eligible = True
    if rules["new_home_only"] and not is_new_home:
        eligible = False
        notes.append(f"{state}'s grant applies to new or substantially renovated homes only.")

    if rules["price_cap"] is not None and home_price > rules["price_cap"]:
        eligible = False
        notes.append(f"Property price ${home_price:,.0f} exceeds the ${rules['price_cap']:,.0f} cap.")

    return GrantEstimate(state=state, amount=rules["amount"] if eligible else 0, eligible=eligible, notes=notes)
