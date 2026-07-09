"""Performance attribution — factor decomposition and Brinson-style attribution.

Decomposes portfolio returns into factor exposures (market, size, value,
momentum, quality) and provides allocation/selection effect analysis.

Usage:
    from numeraire.attribution import factor_returns, brinson_attribution
"""

from __future__ import annotations

import math
from typing import Any

# ── Statistics helpers ──────────────────────────────────────────────────────


def _mean(vals: list[float]) -> float:
    return sum(vals) / len(vals) if vals else 0.0


def _variance(vals: list[float]) -> float:
    if len(vals) < 2:
        return 0.0
    m = _mean(vals)
    return sum((v - m) ** 2 for v in vals) / (len(vals) - 1)


def _std(vals: list[float]) -> float:
    return math.sqrt(_variance(vals))


def _covariance(a: list[float], b: list[float]) -> float:
    n = min(len(a), len(b))
    if n < 2:
        return 0.0
    ma, mb = _mean(a[:n]), _mean(b[:n])
    return sum((a[i] - ma) * (b[i] - mb) for i in range(n)) / (n - 1)


# ── Factor model ────────────────────────────────────────────────────────────


def factor_returns(
    portfolio_returns: list[float], factor_exposures: dict[str, list[float]], risk_free: float = 0.0
) -> dict[str, Any]:
    """Decompose portfolio returns into factor contributions.

    Uses a simple single-regression-per-factor approach (beta estimation).
    For a full multi-factor regression, use the Numeraire signals engine.

    Args:
        portfolio_returns: periodic portfolio returns (e.g., daily or monthly)
        factor_exposures: {factor_name: periodic_returns}
        risk_free: periodic risk-free rate (same period as returns)

    Returns:
        {
            "alpha": annualized alpha,
            "factor_loadings": {factor: beta},
            "explained_variance": R-squared,
            "specific_risk": tracking error (annualized),
        }
    """
    if not portfolio_returns or not factor_exposures:
        return {"error": "insufficient data"}

    n = len(portfolio_returns)
    excess_returns = [r - risk_free for r in portfolio_returns]

    factor_loadings: dict[str, float] = {}
    total_explained_var = 0.0
    residual = list(excess_returns)

    for factor_name, factor_ret in factor_exposures.items():
        if len(factor_ret) < n:
            continue

        cov = _covariance(excess_returns[:n], factor_ret[:n])
        var_f = _variance(factor_ret[:n])
        if var_f <= 0:
            factor_loadings[factor_name] = 0.0
            continue

        beta = cov / var_f
        factor_loadings[factor_name] = round(beta, 4)

        # Explained variance contribution
        explained = beta * cov
        total_explained_var += max(0, explained)

        # Residual
        for i in range(n):
            residual[i] -= beta * factor_ret[i]

    # R-squared
    total_var = _variance(excess_returns)
    r_squared = min(1.0, total_explained_var / total_var) if total_var > 0 else 0.0

    # Alpha (annualized)
    alpha = _mean(residual) * 252  # Assuming daily data

    # Tracking error (annualized)
    te = _std(residual) * math.sqrt(252)

    return {
        "alpha": round(alpha, 4),
        "factor_loadings": factor_loadings,
        "r_squared": round(r_squared, 4),
        "tracking_error": round(te, 4),
        "specific_risk": round(te, 4),
        "n_periods": n,
    }


# ── Brinson Attribution ─────────────────────────────────────────────────────


def brinson_attribution(
    portfolio_weights: dict[str, float],
    portfolio_returns: dict[str, float],
    benchmark_weights: dict[str, float],
    benchmark_returns: dict[str, float],
    sectors: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Brinson-style performance attribution.

    Decomposes active return into allocation effect and selection effect,
    optionally at the sector level.

    Args:
        portfolio_weights: {ticker: weight_in_portfolio}
        portfolio_returns: {ticker: period_return}
        benchmark_weights: {ticker: weight_in_benchmark}
        benchmark_returns: {ticker: benchmark_return}
        sectors: {ticker: sector_name} — optional sector breakdown

    Returns:
        {
            "total_active_return": float,
            "allocation_effect": float,
            "selection_effect": float,
            "interaction_effect": float,
            "sector_breakdown": {sector: {allocation, selection, total}} | None
        }
    """
    all_tickers = set(portfolio_weights) | set(benchmark_weights)

    p_ret = sum(portfolio_weights.get(t, 0) * portfolio_returns.get(t, 0) for t in all_tickers)
    b_ret = sum(benchmark_weights.get(t, 0) * benchmark_returns.get(t, 0) for t in all_tickers)
    active = p_ret - b_ret

    # Brinson decomposition
    alloc_effect = 0.0
    select_effect = 0.0
    interact_effect = 0.0

    for t in all_tickers:
        pw = portfolio_weights.get(t, 0)
        bw = benchmark_weights.get(t, 0)
        pr = portfolio_returns.get(t, 0)
        br = benchmark_returns.get(t, 0)

        alloc_effect += (pw - bw) * br
        select_effect += bw * (pr - br)
        interact_effect += (pw - bw) * (pr - br)

    result: dict[str, Any] = {
        "total_active_return": round(active, 6),
        "allocation_effect": round(alloc_effect, 6),
        "selection_effect": round(select_effect, 6),
        "interaction_effect": round(interact_effect, 6),
    }

    # Sector-level breakdown
    if sectors:
        sector_map: dict[str, dict[str, float]] = {}
        for t in all_tickers:
            sector = sectors.get(t, "Other")
            if sector not in sector_map:
                sector_map[sector] = {"p_w": 0, "b_w": 0, "p_r": 0, "b_r": 0, "count": 0}
            sm = sector_map[sector]
            sm["p_w"] += portfolio_weights.get(t, 0)
            sm["b_w"] += benchmark_weights.get(t, 0)
            sm["p_r"] += portfolio_returns.get(t, 0) * (
                portfolio_weights.get(t, 0) if t in portfolio_weights else 0
            )
            sm["b_r"] += benchmark_returns.get(t, 0) * (
                benchmark_weights.get(t, 0) if t in benchmark_weights else 0
            )
            sm["count"] += 1

        sector_breakdown: dict[str, dict] = {}
        for sector, sm in sector_map.items():
            if sm["count"] == 0:
                continue
            sector_breakdown[sector] = {
                "allocation": round(
                    (sm["p_w"] - sm["b_w"]) * (sm["b_r"] / sm["count"] if sm["count"] else 0), 6
                ),
                "selection": round(sm["b_w"] * (sm["p_r"] - sm["b_r"]), 6) if sm["count"] else 0,
                "total": round(
                    (sm["p_w"] - sm["b_w"]) * (sm["b_r"] / sm["count"] if sm["count"] else 0)
                    + sm["b_w"] * (sm["p_r"] - sm["b_r"]),
                    6,
                ),
            }

        result["sector_breakdown"] = sector_breakdown

    return result


# ── Rolling Alpha ───────────────────────────────────────────────────────────


def rolling_alpha(
    returns: list[float], benchmark_returns: list[float], window: int = 63
) -> list[dict[str, Any]]:
    """Rolling alpha estimate over a sliding window.

    Args:
        returns: asset/portfolio returns (e.g., daily)
        benchmark_returns: benchmark returns (same frequency)
        window: rolling window in periods (default 63 = ~3 months daily)

    Returns:
        [{date_idx: int, alpha: float, beta: float, r_squared: float}]
    """
    results = []
    n = min(len(returns), len(benchmark_returns))

    for i in range(window, n):
        rets = returns[i - window : i]
        bench = benchmark_returns[i - window : i]

        cov = _covariance(rets, bench)
        var_b = _variance(bench)
        if var_b <= 0:
            continue

        beta = cov / var_b
        alpha = _mean(rets) - beta * _mean(bench)

        # R-squared
        explained = beta * cov
        total_var = _variance(rets)
        r2 = min(1.0, explained / total_var) if total_var > 0 else 0.0

        results.append(
            {
                "date_idx": i,
                "alpha": round(alpha, 6),
                "beta": round(beta, 4),
                "r_squared": round(r2, 4),
            }
        )

    return results


# ── Simple return statistics ────────────────────────────────────────────────


def return_statistics(
    returns: list[float], risk_free_rate: float = 0.0, periods_per_year: int = 252
) -> dict[str, Any]:
    """Compute key return statistics for a return series.

    Args:
        returns: periodic returns
        risk_free_rate: periodic risk-free rate
        periods_per_year: 252 for daily, 12 for monthly, 52 for weekly

    Returns:
        {total_return, annualized_return, annualized_vol, sharpe,
         sortino, max_drawdown, calmar_ratio}
    """
    if not returns:
        return {}

    n = len(returns)
    total_ret = math.prod(1 + r for r in returns) - 1
    ann_ret = (1 + total_ret) ** (periods_per_year / n) - 1 if n > 0 else 0
    ann_vol = _std(returns) * math.sqrt(periods_per_year)
    excess = [r - risk_free_rate for r in returns]
    sharpe = _mean(excess) / _std(excess) * math.sqrt(periods_per_year) if _std(excess) > 0 else 0

    # Sortino (downside deviation)
    downside = [r - risk_free_rate for r in returns if r < risk_free_rate]
    dd = math.sqrt(_variance(downside)) * math.sqrt(periods_per_year) if downside else 0
    sortino = (_mean(excess) * periods_per_year / dd) if dd > 0 else 0

    # Max drawdown
    peak = 1.0
    max_dd = 0.0
    eq_curve = 1.0
    for r in returns:
        eq_curve *= 1 + r
        peak = max(peak, eq_curve)
        dd_pct = (eq_curve - peak) / peak
        max_dd = min(max_dd, dd_pct)

    calmar = ann_ret / abs(max_dd) if max_dd < 0 else 0

    return {
        "total_return": round(total_ret, 4),
        "annualized_return": round(ann_ret, 4),
        "annualized_volatility": round(ann_vol, 4),
        "sharpe_ratio": round(sharpe, 4),
        "sortino_ratio": round(sortino, 4),
        "max_drawdown": round(max_dd, 4),
        "calmar_ratio": round(calmar, 4),
        "n_periods": n,
    }
