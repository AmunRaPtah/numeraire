"""Tests for Yahoo price connector."""

from __future__ import annotations

import json

from numeraire.sources import prices


def test_ingest_basic(monkeypatch, env):
    """ingest() should parse a minimal price response."""
    response = {
        "chart": {
            "result": [{
                "timestamp": [1700000000, 1700086400],
                "indicators": {
                    "quote": [{
                        "open": [100.0, 101.0],
                        "high": [102.0, 103.0],
                        "low": [99.0, 100.0],
                        "close": [101.0, 102.0],
                        "volume": [1000000, 1200000],
                    }],
                    "adjclose": [{"adjclose": [101.0, 102.0]}],
                },
            }]
        }
    }
    monkeypatch.setattr(prices.net, "request",
                        lambda url, **kw: json.dumps(response).encode())
    ptot, atot = prices.ingest("AAPL")
    assert ptot > 0
    assert atot == 0  # no dividends/splits


def test_ingest_no_data(monkeypatch, env):
    """ingest() on an empty response should produce nothing."""
    monkeypatch.setattr(prices.net, "request",
                        lambda url, **kw: json.dumps({"chart": {"result": []}}).encode())
    ptot, atot = prices.ingest("FAKE")
    assert ptot == 0


def test_ingest_error(monkeypatch, env):
    """ingest() on network error should return (0,0)."""
    from numeraire import net
    monkeypatch.setattr(prices.net, "request",
                        lambda url, **kw: (_ for _ in ()).throw(net.NetworkError("fail")))
    ptot, atot = prices.ingest("AAPL")
    assert ptot == 0
