"""Top-level orchestrator: fetch current rates, then score an applicant."""

from __future__ import annotations

from mortgage_agent.eligibility import evaluate_all_programs
from mortgage_agent.models import AgentReport, Applicant
from mortgage_agent.rates import RateSource, get_rate_snapshot


class MortgageEligibilityAgent:
    """Scrapes current mortgage rates and estimates first-time buyer eligibility."""

    def __init__(self, rate_source: RateSource | None = None):
        self._rate_source = rate_source

    def evaluate(self, applicant: Applicant, offline: bool = False) -> AgentReport:
        snapshot = get_rate_snapshot(offline=offline, source=self._rate_source)
        results = evaluate_all_programs(applicant, snapshot)
        return AgentReport(
            applicant=applicant,
            rates_as_of=snapshot.as_of,
            rate_source=snapshot.source,
            results=results,
        )
