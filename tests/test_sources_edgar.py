"""Tests for EDGAR source connector."""

from __future__ import annotations

import json

from numeraire.sources import edgar


def test_ingest_no_network(monkeypatch, env):
    """ingest() should gracefully handle network errors."""
    monkeypatch.setattr(edgar, "_tickers", lambda: {
        "0": {"ticker": "AAPL", "cik_str": 320193, "title": "Apple Inc."},
    })
    monkeypatch.setattr(edgar.net, "request",
                        lambda url, **kw: (_ for _ in ()).throw(edgar.net.NetworkError("fail")))
    result = edgar.ingest("AAPL")
    assert result == ("", 0, 0)


def test_ingest_success(monkeypatch, env):
    """ingest() should parse and land XBRL data."""
    mock_data = {
        "entityName": "APPLE INC",
        "facts": {
            "us-gaap": {
                "NetIncomeLoss": {
                    "units": {
                        "USD": [{
                            "val": 10000000, "end": "2024-01-01",
                            "accn": "0000320193-24-000001", "filed": "2024-02-01",
                            "fy": "2024", "fp": "Q1", "form": "10-Q",
                        }]
                    }
                }
            }
        }
    }
    monkeypatch.setattr(edgar, "_tickers", lambda: {
        "0": {"ticker": "AAPL", "cik_str": 320193, "title": "Apple Inc."},
    })
    monkeypatch.setattr(edgar.net, "request",
                        lambda url, **kw: json.dumps(mock_data).encode())
    result = edgar.ingest("AAPL")
    path, total, added = result
    assert total > 0
    assert added > 0
    assert path.endswith(".jsonl")


def test_ingest_unknown_ticker(monkeypatch, env):
    """Unknown ticker returns empty."""
    monkeypatch.setattr(edgar, "_tickers", lambda: {})
    result = edgar.ingest("FAKE")
    assert result == ("", 0, 0)


def test_cik_for(monkeypatch):
    monkeypatch.setattr(edgar, "_tickers", lambda: {
        "0": {"ticker": "AAPL", "cik_str": 320193},
        "1": {"ticker": "MSFT", "cik_str": 789019},
    })
    assert edgar.cik_for("AAPL") == 320193
    assert edgar.cik_for("msft") == 789019  # case insensitive
    assert edgar.cik_for("JNJ") is None


def test_tickers_structure(monkeypatch):
    """_tickers() should parse and cache."""
    call_count = 0

    def mock_get_json(url, **kw):
        nonlocal call_count
        call_count += 1
        return {"0": {"ticker": "AAPL", "cik_str": 320193, "title": "Apple Inc."}}

    # Fresh test: no cache
    monkeypatch.setattr(edgar, "_tickers_cache", None)
    monkeypatch.setattr(edgar.net, "get_json", mock_get_json)

    result = edgar._tickers()
    assert result["0"]["ticker"] == "AAPL"
    assert call_count == 1
    # Second call should use cache, not network
    result2 = edgar._tickers()
    assert call_count == 1
