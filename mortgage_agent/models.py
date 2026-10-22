"""Data structures shared across the mortgage agent (Australian market)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum

AU_STATES = {"NSW", "VIC", "QLD", "WA", "SA", "TAS", "ACT", "NT"}


class LoanScheme(str, Enum):
    """A standard home loan plus the Australian Government's Home Guarantee Scheme products."""

    STANDARD = "standard"
    FIRST_HOME_GUARANTEE = "first_home_guarantee"
    REGIONAL_FIRST_HOME_GUARANTEE = "regional_first_home_guarantee"
    FAMILY_HOME_GUARANTEE = "family_home_guarantee"


@dataclass
class Applicant:
    """Financial profile of a prospective Australian first home buyer."""

    annual_income: float  # gross; combined household income if is_couple
    monthly_living_expenses: float
    monthly_other_debts: float
    deposit: float
    home_price: float
    state: str
    is_couple: bool = False
    is_single_parent: bool = False
    is_regional: bool = False
    is_first_home_buyer: bool = True
    is_owner_occupier: bool = True
    is_australian_citizen_or_pr: bool = True
    is_new_home: bool = False  # relevant to the First Home Owner Grant only
    dependents: int = 0

    def __post_init__(self) -> None:
        state = self.state.upper()
        if state not in AU_STATES:
            raise ValueError(f"Unknown state '{self.state}'; expected one of {sorted(AU_STATES)}")
        self.state = state

    @property
    def loan_amount(self) -> float:
        return max(self.home_price - self.deposit, 0.0)

    @property
    def lvr_percent(self) -> float:
        if self.home_price <= 0:
            return 0.0
        return self.loan_amount / self.home_price * 100

    @property
    def deposit_percent(self) -> float:
        if self.home_price <= 0:
            return 0.0
        return self.deposit / self.home_price * 100


@dataclass
class SchemeResult:
    """Eligibility outcome for a single loan scheme."""

    scheme: LoanScheme
    eligible: bool
    reasons: list[str]
    interest_rate_percent: float
    loan_amount: float
    lvr_percent: float
    requires_lmi: bool
    estimated_lmi_premium: float | None
    monthly_repayment: float | None  # principal & interest, at the actual rate
    assessed_monthly_repayment: float | None  # principal & interest, at the APRA buffer rate
    monthly_surplus_at_assessed_rate: float | None
    loan_to_income_ratio: float | None
    max_affordable_home_price: float | None


@dataclass
class GrantEstimate:
    """Indicative First Home Owner Grant outcome for a state."""

    state: str
    amount: float
    eligible: bool
    notes: list[str] = field(default_factory=list)


@dataclass
class AgentReport:
    """Full output of a MortgageEligibilityAgent run."""

    applicant: Applicant
    rate_as_of: date
    rate_source: str
    cash_rate_percent: float
    variable_rate_percent: float
    fixed_3yr_rate_percent: float
    results: list[SchemeResult] = field(default_factory=list)
    estimated_fhog: GrantEstimate | None = None

    @property
    def eligible_schemes(self) -> list[SchemeResult]:
        return [r for r in self.results if r.eligible]

    @property
    def best_scheme(self) -> SchemeResult | None:
        candidates = [r for r in self.eligible_schemes if r.monthly_repayment is not None]
        if not candidates:
            return None
        return min(
            candidates,
            key=lambda r: (r.requires_lmi, r.estimated_lmi_premium or 0.0, r.monthly_repayment),
        )
