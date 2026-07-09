"""Tests for composite signal ranker."""

from __future__ import annotations

import seed

from numeraire import signals


def test_rank_no_prices_empty(con, env):
    """rank() on empty warehouse returns []."""
    result = signals.rank(con=con)
    assert result == []


def test_rank_returns_ranked_list(con, env):
    """rank() should return a sorted list of dicts."""
    seed.build_full(con)
    result = signals.rank(asof="2025-06-01", con=con)
    assert len(result) > 0
    # Check structure
    r = result[0]
    for key in ("ticker", "composite", "mom", "price", "n_factors"):
        assert key in r
    # Composite should be sorted descending
    composites = [r["composite"] for r in result]
    assert all(composites[i] >= composites[i + 1] for i in range(len(composites) - 1))


def test_rank_top_limit(con, env):
    """top=N should limit results."""
    seed.build_full(con)
    full = signals.rank(asof="2025-06-01", con=con)
    top5 = signals.rank(asof="2025-06-01", top=5, con=con)
    assert len(top5) == min(5, len(full))
    if len(full) > 5:
        assert len(top5) == 5


def test_rank_coverage_counts(con, env):
    """rank() should populate n_factors correctly."""
    seed.build_full(con)
    result = signals.rank(asof="2025-06-01", con=con)
    for r in result:
        assert 1 <= r["n_factors"] <= 5


def test_rank_missing_index_membership(con, env):
    """rank() works without index_membership table."""
    seed.seed_edgar_multi()
    seed.seed_prices_multi()
    from numeraire import warehouse

    warehouse.build(con)
    result = signals.rank(asof="2025-06-01", con=con)
    assert len(result) > 0


def test_signals_print_signals_no_error(con, env, capsys):
    """print_signals() should run without exceptions."""
    seed.build_full(con)
    signals.print_signals(asof="2025-06-01", top=5, con=con)
    captured = capsys.readouterr()
    assert captured.out
    assert "ticker" in captured.out
