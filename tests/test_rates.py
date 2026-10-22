from datetime import date
from unittest.mock import Mock, patch

import pytest
import requests

from mortgage_agent.rates import (
    RateParseError,
    RBACashRateSource,
    StaticFallbackSource,
    get_rate_snapshot,
)

SAMPLE_HTML = """
<html><body>
<p>The Reserve Bank Board decided to leave the Cash Rate Target unchanged at 3.85 per cent.</p>
<p>This decision is effective 6 August 2025.</p>
</body></html>
"""


def test_parses_rate_and_date_from_html():
    source = RBACashRateSource()
    snapshot = source._parse(SAMPLE_HTML)
    assert snapshot.cash_rate_percent == 3.85
    assert snapshot.as_of == date(2025, 8, 6)
    assert snapshot.is_live is True


def test_parse_raises_when_rate_missing():
    source = RBACashRateSource()
    with pytest.raises(RateParseError):
        source._parse("<html><body>no rate here</body></html>")


def test_fetch_uses_requests_get():
    source = RBACashRateSource()
    mock_response = Mock()
    mock_response.text = SAMPLE_HTML
    mock_response.raise_for_status = Mock()
    with patch("mortgage_agent.rates.requests.get", return_value=mock_response) as mock_get:
        snapshot = source.fetch()
    mock_get.assert_called_once()
    assert snapshot.cash_rate_percent == 3.85


def test_get_rate_snapshot_falls_back_on_network_error():
    class FailingSource:
        def fetch(self):
            raise requests.ConnectionError("blocked")

    snapshot = get_rate_snapshot(offline=False, source=FailingSource())
    assert snapshot.is_live is False
    assert snapshot.source == "bundled-fallback"


def test_get_rate_snapshot_falls_back_on_parse_error():
    class BadParseSource:
        def fetch(self):
            raise RateParseError("boom")

    snapshot = get_rate_snapshot(offline=False, source=BadParseSource())
    assert snapshot.is_live is False


def test_get_rate_snapshot_offline_skips_live_source():
    class ShouldNotBeCalled:
        def fetch(self):
            raise AssertionError("live source should not be used in offline mode")

    snapshot = get_rate_snapshot(offline=True, source=ShouldNotBeCalled())
    assert snapshot.source == "bundled-fallback"


def test_static_fallback_derives_variable_and_fixed_rates():
    snapshot = StaticFallbackSource().fetch()
    assert snapshot.variable_rate_percent > snapshot.cash_rate_percent
    assert snapshot.fixed_3yr_rate_percent > snapshot.cash_rate_percent
