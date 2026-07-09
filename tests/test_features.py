"""Tests for PIT factor computation."""

from __future__ import annotations

import math

import seed

from numeraire import features


def test_zscore_normal_distribution():
    """zscore() should normalize a known set correctly."""
    vals = {"A": 10.0, "B": 20.0, "C": 30.0}
    z = features.zscore(vals)
    assert math.isclose(z["A"], -1.0, abs_tol=0.01)
    assert math.isclose(z["B"], 0.0, abs_tol=0.01)
    assert math.isclose(z["C"], 1.0, abs_tol=0.01)


def test_zscore_single_value():
    """Single finite value should produce 0.0 (no cross-section)."""
    z = features.zscore({"A": 10.0})
    assert z["A"] == 0.0


def test_zscore_handles_none_and_nan():
    vals = {"A": 10.0, "B": None, "C": float("nan"), "D": 30.0}
    z = features.zscore(vals)
    assert z["B"] == 0.0
    assert math.isfinite(z["A"])
    assert math.isfinite(z["C"])
    assert math.isfinite(z["D"])


def test_zscore_all_zeros():
    """If all values are zero, don't divide by zero."""
    z = features.zscore({"A": 0.0, "B": 0.0, "C": 0.0})
    assert all(v == 0.0 for v in z.values())


def test_zscore_all_identical():
    z = features.zscore({"A": 5.0, "B": 5.0})
    assert z["A"] == 0.0 and z["B"] == 0.0


def test_ticker_cik_map_mocked(monkeypatch):
    """ticker_cik_map() without network — patch _tickers()."""
    from numeraire.sources import edgar
    monkeypatch.setattr(edgar, "_tickers", lambda: {
        "0": {"ticker": "AAPL", "cik_str": 320193},
        "1": {"ticker": "MSFT", "cik_str": 789019},
    })
    m = features.ticker_cik_map()
    assert m["AAPL"] == 320193
    assert m["MSFT"] == 789019
    assert "JNJ" not in m


def test_compute_with_data(con, env):
    """compute() returns factors for tickers with EDGAR data."""
    seed.build_full(con)
    tk_cik = {"AAPL": 320193, "MSFT": 789019, "GOOGL": 1652044}
    prices = {"AAPL": 150.0, "MSFT": 300.0, "GOOGL": 140.0}
    result = features.compute(con, tk_cik, "2025-06-01", prices)
    for ticker in ("AAPL", "MSFT", "GOOGL"):
        for factor in ("ey", "bp", "roe", "gm"):
            assert ticker in result
            # Should be a finite number (not None) with seeded data
            v = result[ticker][factor]
            assert v is not None and math.isfinite(v), f"{ticker}.{factor} should be finite"


def test_compute_no_data(con, env):
    """Ticker without EDGAR data gets None factors."""
    seed.build_full(con)
    tk_cik = {"FAKE": 999999}
    prices = {"FAKE": 50.0}
    result = features.compute(con, tk_cik, "2025-06-01", prices)
    assert result["FAKE"]["ey"] is None
    assert result["FAKE"]["bp"] is None
    assert result["FAKE"]["roe"] is None
    assert result["FAKE"]["gm"] is None


def test_compute_no_price(con, env):
    """Ticker with no price should get None factors."""
    seed.build_full(con)
    tk_cik = {"AAPL": 320193}
    result = features.compute(con, tk_cik, "2025-06-01", {"AAPL": None})
    assert all(v is None for v in result["AAPL"].values())


def test_compute_empty_warehouse(con, env):
    """compute() on empty warehouse should return all-None."""
    result = features.compute(con, {"AAPL": 320193}, "2025-06-01", {"AAPL": 150.0})
    assert result["AAPL"]["ey"] is None
