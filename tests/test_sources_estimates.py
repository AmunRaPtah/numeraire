"""Tests for analyst estimates connector."""

from __future__ import annotations


def test_ingest_no_bootstrap(monkeypatch, env):
    """ingest() returns empty tuple when no bootstrap."""
    import numeraire.sources.estimates as est

    # Clear any cached state
    est._opener_cache = None

    def mocked_bootstrap():
        return (None, None)

    monkeypatch.setattr(est, "_bootstrap", mocked_bootstrap)
    result = est.ingest("AAPL")
    assert result == ("", 0, 0)


def test_ingest_no_trends(monkeypatch, env):
    """ingest() with no trend data returns empty tuple."""
    from unittest.mock import MagicMock

    import numeraire.sources.estimates as est

    est._opener_cache = None

    resp = MagicMock()
    resp.read.return_value = b'{"quoteSummary": {"result": [{}]}}'
    opener = MagicMock()
    opener.open.return_value = resp

    def mocked_bootstrap():
        return (opener, "crumb123")

    monkeypatch.setattr(est, "_bootstrap", mocked_bootstrap)
    result = est.ingest("FAKE")
    assert result == ("", 0, 0)
