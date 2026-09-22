"""Fetches current mortgage rate benchmarks and derives per-program rates.

There is no single published "first-time home buyer rate": actual rates
depend on the loan program, the applicant's credit score, and their down
payment. This module scrapes the Freddie Mac Primary Mortgage Market
Survey (PMMS) for the national-average 30-year fixed conventional rate,
then applies well-known industry rate adjustments to approximate the rate
for each first-time-buyer-friendly program (FHA, VA, USDA, Conventional 97).

If the live source is unreachable (no network access, the page layout
changed, etc.) the agent automatically falls back to a bundled static
snapshot so the rest of the pipeline keeps working, and it always reports
which source was actually used.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Protocol

import requests

PMMS_URL = "https://www.freddiemac.com/pmms"
REQUEST_TIMEOUT_SECONDS = 10

# Bundled fallback used when the live source can't be reached. Values are a
# representative long-run snapshot, not live data -- callers are told via
# RateSnapshot.source / is_live when this was used.
FALLBACK_30YR_RATE = 6.75
FALLBACK_15YR_RATE = 6.00
FALLBACK_AS_OF = date(2024, 1, 1)

# Approximate rate adjustments relative to the conventional 30-yr average,
# based on typical lender rate sheets. Real quotes vary by lender, credit
# score, LTV and loan size -- these are directional estimates only.
PROGRAM_RATE_ADJUSTMENT_PERCENT = {
    "conventional_97": 0.125,  # high-LTV loan-level price adjustment
    "fha": -0.25,
    "va": -0.375,
    "usda": -0.125,
}


class RateSnapshot:
    """The 30-year benchmark rate plus the source it came from."""

    def __init__(self, rate_30yr_percent: float, as_of: date, source: str, is_live: bool):
        self.rate_30yr_percent = rate_30yr_percent
        self.as_of = as_of
        self.source = source
        self.is_live = is_live

    def program_rate(self, program: str) -> float:
        adjustment = PROGRAM_RATE_ADJUSTMENT_PERCENT.get(program, 0.0)
        return round(self.rate_30yr_percent + adjustment, 3)


class RateSource(Protocol):
    def fetch(self) -> RateSnapshot: ...


class FreddieMacPMMSSource:
    """Scrapes the weekly Freddie Mac PMMS page for the 30-yr FRM average."""

    def __init__(self, url: str = PMMS_URL, timeout: int = REQUEST_TIMEOUT_SECONDS):
        self.url = url
        self.timeout = timeout

    def fetch(self) -> RateSnapshot:
        response = requests.get(
            self.url,
            timeout=self.timeout,
            headers={"User-Agent": "mortgage-eligibility-agent/1.0"},
        )
        response.raise_for_status()
        return self._parse(response.text)

    def _parse(self, html: str) -> RateSnapshot:
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"\s+", " ", text)

        rate = self._extract_rate(text, r"30[\s-]*Yr\.?\s*FRM")
        if rate is None:
            raise RateParseError(
                "Could not find the 30-year fixed rate on the PMMS page; "
                "the page layout may have changed."
            )

        as_of = self._extract_date(text) or date.today()
        return RateSnapshot(rate, as_of, source=self.url, is_live=True)

    @staticmethod
    def _extract_rate(text: str, label_pattern: str) -> float | None:
        match = re.search(label_pattern + r".{0,40}?(\d{1,2}\.\d{1,3})\s*%", text)
        if match:
            return float(match.group(1))
        return None

    @staticmethod
    def _extract_date(text: str) -> date | None:
        match = re.search(r"(January|February|March|April|May|June|July|"
                           r"August|September|October|November|December)\s+\d{1,2},?\s+\d{4}", text)
        if not match:
            return None
        try:
            return datetime.strptime(match.group(0).replace(",", ""), "%B %d %Y").date()
        except ValueError:
            return None


class StaticFallbackSource:
    """Bundled snapshot used when the live source is unreachable or disabled."""

    def fetch(self) -> RateSnapshot:
        return RateSnapshot(
            FALLBACK_30YR_RATE, FALLBACK_AS_OF, source="bundled-fallback", is_live=False
        )


class RateParseError(RuntimeError):
    """Raised when the live page was fetched but couldn't be parsed."""


def get_rate_snapshot(offline: bool = False, source: RateSource | None = None) -> RateSnapshot:
    """Fetches the current benchmark rate, falling back to static data on failure.

    Any network or parsing error is swallowed here by design -- eligibility
    estimation should still run (using the fallback snapshot) even when the
    live source is unavailable, since that's expected in sandboxed or
    offline environments.
    """
    if offline:
        return StaticFallbackSource().fetch()

    live_source = source or FreddieMacPMMSSource()
    try:
        return live_source.fetch()
    except (requests.RequestException, RateParseError):
        return StaticFallbackSource().fetch()
