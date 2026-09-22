"""Data structures shared across the mortgage agent."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum


class LoanProgram(str, Enum):
    """First-time home buyer friendly loan programs supported by the agent."""

    CONVENTIONAL_97 = "conventional_97"
    FHA = "fha"
    VA = "va"
    USDA = "usda"


@dataclass(frozen=True)
class RateQuote:
    """A single mortgage rate data point."""

    program: str
    term_years: int
    rate_percent: float
    as_of: date
    source: str


@dataclass
class Applicant:
    """Financial profile of a prospective first-time home buyer."""

    annual_income: float
    monthly_debts: float
    credit_score: int
    down_payment: float
    home_price: float
    is_veteran: bool = False
    is_rural_property: bool = False
    household_size: int = 1
    # Household income limit for the applicant's area, used for USDA's
    # 115%-of-AMI test. If unknown, USDA eligibility is reported as
    # "needs verification" rather than pass/fail.
    area_median_income: float | None = None
    annual_property_tax_rate: float = 0.011  # ~1.1% of home price/yr (US avg)
    annual_insurance_rate: float = 0.0035  # ~0.35% of home price/yr

    @property
    def monthly_income(self) -> float:
        return self.annual_income / 12

    @property
    def loan_amount(self) -> float:
        return max(self.home_price - self.down_payment, 0.0)

    @property
    def down_payment_percent(self) -> float:
        if self.home_price <= 0:
            return 0.0
        return self.down_payment / self.home_price * 100


@dataclass
class ProgramResult:
    """Eligibility outcome for a single loan program."""

    program: LoanProgram
    eligible: bool
    needs_verification: bool
    reasons: list[str]
    interest_rate_percent: float | None
    loan_amount: float
    down_payment_percent: float
    monthly_principal_interest: float | None
    monthly_piti: float | None
    front_end_dti_percent: float | None
    back_end_dti_percent: float | None
    max_affordable_home_price: float | None


@dataclass
class AgentReport:
    """Full output of a MortgageEligibilityAgent run."""

    applicant: Applicant
    rates_as_of: date
    rate_source: str
    results: list[ProgramResult] = field(default_factory=list)

    @property
    def eligible_programs(self) -> list[ProgramResult]:
        return [r for r in self.results if r.eligible]

    @property
    def best_program(self) -> ProgramResult | None:
        candidates = [r for r in self.eligible_programs if r.monthly_piti is not None]
        if not candidates:
            return None
        return min(candidates, key=lambda r: r.monthly_piti)
