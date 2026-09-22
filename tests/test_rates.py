from datetime import date
from unittest.mock import Mock, patch

import pytest
import requests

from mortgage_agent.rates import (
    FreddieMacPMMSSource,
    RateParseError,
    StaticFallbackSource,
    get_rate_snapshot,
)

SAMPLE_HTML = """
<html><body>
<div class="rate">30-Yr FRM <span>6.850%</span></div>
<div class="rate">15-Yr FRM <span>6.100%</span></div>
<p>Rates current as of March 14, 2024</p>
</body></html>
"""


def test_parses_rate_and_date_from_html():
    source = FreddieMacPMMSSource()
    snapshot = source._parse(SAMPLE_HTML)
    assert snapshot.rate_30yr_percent == 6.85
    assert snapshot.as_of == date(2024, 3, 14)
    assert snapshot.is_live is True


def test_parse_raises_when_rate_missing():
    source = FreddieMacPMMSSource()
    with pytest.raises(RateParseError):
        source._parse("<html><body>no rates here</body></html>")


def test_fetch_uses_requests_get():
    source = FreddieMacPMMSSource()
    mock_response = Mock()
    mock_response.text = SAMPLE_HTML
    mock_response.raise_for_status = Mock()
    with patch("mortgage_agent.rates.requests.get", return_value=mock_response) as mock_get:
        snapshot = source.fetch()
    mock_get.assert_called_once()
    assert snapshot.rate_30yr_percent == 6.85


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


def test_static_fallback_program_rate_adjustments():
    snapshot = StaticFallbackSource().fetch()
    assert snapshot.program_rate("fha") < snapshot.rate_30yr_percent
    assert snapshot.program_rate("va") < snapshot.program_rate("fha")
    assert snapshot.program_rate("conventional_97") > snapshot.rate_30yr_percent
