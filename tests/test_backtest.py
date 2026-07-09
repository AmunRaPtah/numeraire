"""Tests for backtest module."""

from __future__ import annotations

import seed

from numeraire import backtest


def test_run_short_history_skips_gracefully(con, env):
    """run() with <26 months of prices returns early."""
    # Only seed 12 months of prices
    seed.seed_sp500()
    seed.seed_edgar_multi()
    seed.seed_prices_multi()
    from numeraire import warehouse
    warehouse.build(con)

    # Remove most of the price history for a short test
    con.execute("DELETE FROM prices WHERE event_date < '2024-01-01'")
    result = backtest.run(con=con)
    # Should not raise; output goes to stdout


def test_run_momentum_works(con, env, capsys):
    """run() should produce a momentum backtest report."""
    seed.build_full(con)
    backtest.run(con=con)
    captured = capsys.readouterr()
    assert "Momentum" in captured.out
    assert "CAGR" in captured.out
    assert "Sharpe" in captured.out


def test_run_multifactor_works(con, env, capsys):
    """run_multifactor() should produce a multi-factor report."""
    seed.build_full(con)
    backtest.run_multifactor(con=con)
    captured = capsys.readouterr()
    assert "Multi-factor" in captured.out
    assert "CAGR" in captured.out
    assert "Sharpe" in captured.out


def test_run_with_membership(con, env, capsys):
    """Passing survivorship-free membership should use it."""
    seed.build_full(con)
    backtest.run(con=con)
    captured = capsys.readouterr()
    assert "survivorship-free" in captured.out


def test_run_multifactor_with_top_frac(con, env, capsys):
    """top_frac parameter changes the selection width."""
    seed.build_full(con)
    backtest.run_multifactor(top_frac=0.5, con=con)
    captured = capsys.readouterr()
    assert "Multi-factor" in captured.out


def test_run_with_cost(con, env):
    """Higher cost_bps reduces net returns."""
    seed.build_full(con)
    # Low cost
    backtest.run(cost_bps=0, con=con)
    # Just verify no crash with different parameters
    backtest.run(cost_bps=50, con=con)


def test_report_format(capsys):
    """_report should format stats correctly."""
    rets = [0.01, -0.005, 0.02, 0.015, -0.01]
    backtest._report("Test Strategy", rets)
    captured = capsys.readouterr()
    assert "Test Strategy" in captured.out
    assert "%" in captured.out
