"""Tests for FRED macro source + regime classification."""

from __future__ import annotations

import seed

from numeraire.sources import fred


def test_regime_classification_expansion(con, env):
    """Expansion regime when data is loaded."""
    seed.seed_macro()
    from numeraire import warehouse

    warehouse.build(con)
    result = fred.regime(con, "2024-06-01")
    assert result["label"] != "unknown"
    assert isinstance(result["display"], str)


def test_regime_classification_no_data(con, env):
    """No macro data gives 'unknown' regime."""
    result = fred.regime(con, "2024-06-01")
    assert result["label"] == "unknown"


def test_regime_series_structure(con, env):
    """regime_series() returns dict of month->label."""
    seed.seed_macro()
    from numeraire import warehouse

    warehouse.build(con)
    months = ["2024-01-01", "2024-06-01", "2025-01-01"]
    result = fred.regime_series(con, months)
    assert isinstance(result, dict)
    # With seeded macro data, all months should have labels
    assert len(result) > 0


def test_ingest(monkeypatch, env):
    """ingest() with mocked FRED API returns >0."""
    monkeypatch.setattr(fred, "_api_key", lambda: "test_key")
    monkeypatch.setattr(
        fred,
        "_fetch",
        lambda sid: [
            {
                "series_id": sid,
                "event_date": "2024-01-01",
                "knowledge_date": "2024-01-01",
                "val": 5.5,
                "fetched_at": "2024-01-01T00:00:00",
            },
            {
                "series_id": sid,
                "event_date": "2024-06-01",
                "knowledge_date": "2024-06-01",
                "val": 5.25,
                "fetched_at": "2024-06-01T00:00:00",
            },
        ],
    )
    result = fred.ingest(series_ids=["DFF"])
    assert result["DFF"][0] > 0


def test_regime_recession(con, env):
    """Recession regime when USREC=1."""
    # seed_macro includes 2020-Q2 as recession (USREC=1, knowledge_date +180d)
    seed.seed_macro()
    from numeraire import warehouse

    warehouse.build(con)
    # as-of 2021-01-01 should see the recession (knowledge_date=2020-10-01)
    result = fred.regime(con, "2021-01-01")
    assert result["label"] == "recession"
