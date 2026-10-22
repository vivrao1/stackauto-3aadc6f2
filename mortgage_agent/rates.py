"""Fetches the RBA cash rate target and derives indicative home loan rates.

There is no single published "first home buyer rate" in Australia either:
lenders price off the cash rate with their own margins, and the Home
Guarantee Scheme changes which costs apply (e.g. waiving LMI), not the
rate itself. This module scrapes the Reserve Bank of Australia's cash
rate target, then applies typical lender margins to approximate current
owner-occupier principal & interest rates (variable and 3-year fixed).

If the live source is unreachable (no network access, the page layout
changed, etc.) the agent automatically falls back to a bundled static
snapshot so the rest of the pipeline keeps working, and it always
reports which source was actually used.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Protocol

import requests

RBA_CASH_RATE_URL = "https://www.rba.gov.au/statistics/cash-rate/"
REQUEST_TIMEOUT_SECONDS = 10

_MONTHS = (
    "January|February|March|April|May|June|July|August|September|October|November|December"
)

# Bundled fallback used when the live source can't be reached. This is a
# representative snapshot, not live data -- callers are told via
# RateSnapshot.source / is_live when this was used.
FALLBACK_CASH_RATE_PERCENT = 3.60
FALLBACK_AS_OF = date(2025, 8, 1)

# Typical lender margins over the cash rate for an owner-occupier P&I loan.
# Real bank pricing varies by lender, LVR and borrower profile -- these are
# directional estimates only.
VARIABLE_RATE_MARGIN_PERCENT = 1.85
FIXED_3YR_RATE_MARGIN_PERCENT = 1.65


class RateSnapshot:
    """The RBA cash rate target plus the source it came from."""

    def __init__(self, cash_rate_percent: float, as_of: date, source: str, is_live: bool):
        self.cash_rate_percent = cash_rate_percent
        self.as_of = as_of
        self.source = source
        self.is_live = is_live

    @property
    def variable_rate_percent(self) -> float:
        return round(self.cash_rate_percent + VARIABLE_RATE_MARGIN_PERCENT, 3)

    @property
    def fixed_3yr_rate_percent(self) -> float:
        return round(self.cash_rate_percent + FIXED_3YR_RATE_MARGIN_PERCENT, 3)


class RateSource(Protocol):
    def fetch(self) -> RateSnapshot: ...


class RBACashRateSource:
    """Scrapes the RBA's published cash rate target page."""

    def __init__(self, url: str = RBA_CASH_RATE_URL, timeout: int = REQUEST_TIMEOUT_SECONDS):
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

        rate = self._extract_rate(text)
        if rate is None:
            raise RateParseError(
                "Could not find the cash rate target on the RBA page; "
                "the page layout may have changed."
            )

        as_of = self._extract_date(text) or date.today()
        return RateSnapshot(rate, as_of, source=self.url, is_live=True)

    @staticmethod
    def _extract_rate(text: str) -> float | None:
        patterns = [
            r"[Cc]ash [Rr]ate [Tt]arget.{0,40}?(\d{1,2}\.\d{1,2})\s*(?:per cent|%)",
            r"target.{0,15}?of\s*(\d{1,2}\.\d{1,2})\s*(?:per cent|%)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return float(match.group(1))
        return None

    @staticmethod
    def _extract_date(text: str) -> date | None:
        match = re.search(rf"(\d{{1,2}}) ({_MONTHS}) (\d{{4}})", text)
        if not match:
            return None
        try:
            return datetime.strptime(match.group(0), "%d %B %Y").date()
        except ValueError:
            return None


class StaticFallbackSource:
    """Bundled snapshot used when the live source is unreachable or disabled."""

    def fetch(self) -> RateSnapshot:
        return RateSnapshot(
            FALLBACK_CASH_RATE_PERCENT, FALLBACK_AS_OF, source="bundled-fallback", is_live=False
        )


class RateParseError(RuntimeError):
    """Raised when the live page was fetched but couldn't be parsed."""


def get_rate_snapshot(offline: bool = False, source: RateSource | None = None) -> RateSnapshot:
    """Fetches the current cash rate, falling back to static data on failure.

    Any network or parsing error is swallowed here by design -- eligibility
    estimation should still run (using the fallback snapshot) even when the
    live source is unavailable, since that's expected in sandboxed or
    offline environments.
    """
    if offline:
        return StaticFallbackSource().fetch()

    live_source = source or RBACashRateSource()
    try:
        return live_source.fetch()
    except (requests.RequestException, RateParseError):
        return StaticFallbackSource().fetch()
