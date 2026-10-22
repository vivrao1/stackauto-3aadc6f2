"""Top-level orchestrator: fetch current rates, then score an applicant."""

from __future__ import annotations

from mortgage_agent.eligibility import evaluate_all_schemes
from mortgage_agent.grants import estimate_fhog
from mortgage_agent.models import AgentReport, Applicant
from mortgage_agent.rates import RateSource, get_rate_snapshot


class MortgageEligibilityAgent:
    """Scrapes the RBA cash rate and estimates Australian first home buyer eligibility."""

    def __init__(self, rate_source: RateSource | None = None):
        self._rate_source = rate_source

    def evaluate(self, applicant: Applicant, offline: bool = False) -> AgentReport:
        snapshot = get_rate_snapshot(offline=offline, source=self._rate_source)
        results = evaluate_all_schemes(applicant, snapshot)
        grant = estimate_fhog(applicant.state, applicant.is_new_home, applicant.home_price)
        return AgentReport(
            applicant=applicant,
            rate_as_of=snapshot.as_of,
            rate_source=snapshot.source,
            cash_rate_percent=snapshot.cash_rate_percent,
            variable_rate_percent=snapshot.variable_rate_percent,
            fixed_3yr_rate_percent=snapshot.fixed_3yr_rate_percent,
            results=results,
            estimated_fhog=grant,
        )
