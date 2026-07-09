"""Portfolio optimization engine — mean-variance, risk-parity, and Kelly criterion.

All computations use pure Python (math/stdlib only). Covariance estimation
reads from the Numeraire DuckDB prices table.

Usage:
    from numeraire.optimizer import mean_variance, risk_parity, kelly_criterion
    cov = cov_matrix(["AAPL", "MSFT", "GOOGL"])
    weights = mean_variance({"AAPL": 0.15, "MSFT": 0.12, "GOOGL": 0.10}, cov)
"""

from __future__ import annotations

import math
from datetime import date
from typing import Any


# ── Covariance estimation ───────────────────────────────────────────────────


def _returns_series(prices: list[float]) -> list[float]:
    """Compute period-over-period returns from a price series."""
    return [(prices[i] - prices[i - 1]) / prices[i - 1]
            for i in range(1, len(prices)) if prices[i - 1] > 0]


def _mean(vals: list[float]) -> float:
    return sum(vals) / len(vals) if vals else 0.0


def _variance(vals: list[float], mean: float | None = None) -> float:
    if len(vals) < 2:
        return 0.0
    m = mean if mean is not None else _mean(vals)
    return sum((v - m) ** 2 for v in vals) / (len(vals) - 1)


def _std(vals: list[float]) -> float:
    return math.sqrt(_variance(vals))


def _covariance(vals_a: list[float], vals_b: list[float],
                mean_a: float | None = None, mean_b: float | None = None) -> float:
    """Sample covariance between two lists."""
    if len(vals_a) < 2 or len(vals_b) < 2:
        return 0.0
    n = min(len(vals_a), len(vals_b))
    ma = mean_a if mean_a is not None else _mean(vals_a[:n])
    mb = mean_b if mean_b is not None else _mean(vals_b[:n])
    return sum((vals_a[i] - ma) * (vals_b[i] - mb) for i in range(n)) / (n - 1)


def cov_matrix(symbols: list[str] | None = None,
               lookback_days: int = 252, asof: str | None = None,
               con=None) -> dict[str, dict[str, float]]:
    """Covariance matrix for a set of symbols from Numeraire prices.

    Returns {symbol_a: {symbol_b: covariance}} — upper-triangular, symmetric.
    Uses the last ``lookback_days`` of daily returns for each symbol.
    """
    asof = asof or date.today().isoformat()
    owns = con is None
    if con is None:
        from .storage import connect
        con = connect()
    try:
        from .warehouse import _load_aux
        _load_aux(con)

        # Fetch price series
        price_data: dict[str, list[float]] = {}
        candidates = symbols
        if candidates is None:
            rows = con.execute(
                "SELECT DISTINCT ticker FROM prices ORDER BY ticker LIMIT 200"
            ).fetchall()
            candidates = [r[0] for r in rows]

        for sym in candidates:
            rows = con.execute(
                "SELECT event_date, close FROM prices "
                "WHERE ticker = ? AND event_date <= CAST(? AS DATE) "
                "AND close IS NOT NULL AND close > 0 "
                "ORDER BY event_date DESC LIMIT ?",
                [sym, asof, lookback_days + 1],
            ).fetchall()
            if len(rows) >= 20:  # Need at least 20 data points
                price_data[sym] = [float(r[1]) for r in reversed(rows)]

        if len(price_data) < 2:
            return {}

        # Compute return series
        return_data: dict[str, list[float]] = {}
        for sym, prices in price_data.items():
            rets = _returns_series(prices)
            if len(rets) >= 20:
                return_data[sym] = rets

        if len(return_data) < 2:
            return {}

        # Build covariance matrix
        symbols_list = sorted(return_data.keys())
        matrix: dict[str, dict[str, float]] = {}
        for i, sa in enumerate(symbols_list):
            matrix[sa] = {}
            for sb in symbols_list[i:]:
                ra = return_data[sa]
                rb = return_data[sb]
                cov = _covariance(ra, rb)
                matrix[sa][sb] = round(cov, 8)
                if sa != sb:
                    matrix[sb] = matrix.get(sb, {})
                    matrix[sb][sa] = round(cov, 8)

        return matrix
    finally:
        if owns:
            con.close()


# ── Matrix helpers ──────────────────────────────────────────────────────────


def _mat_vec_mul(mat: dict[str, dict[str, float]],
                 vec: dict[str, float]) -> dict[str, float]:
    """Multiply matrix * vector. Matrix and vector indexed by symbol."""
    result: dict[str, float] = {}
    for sa in mat:
        total = 0.0
        for sb in mat[sa]:
            total += mat[sa][sb] * vec.get(sb, 0.0)
        result[sa] = total
    return result


def _vec_dot(a: dict[str, float], b: dict[str, float]) -> float:
    """Dot product of two vectors."""
    return sum(a.get(k, 0.0) * b.get(k, 0.0) for k in set(a) | set(b))


def _portfolio_variance(weights: dict[str, float],
                        cov: dict[str, dict[str, float]]) -> float:
    """Compute portfolio variance given weights and covariance matrix."""
    var = 0.0
    for sa in weights:
        for sb in weights:
            var += weights[sa] * weights[sb] * cov.get(sa, {}).get(sb, 0.0)
    return var


# ── Mean-Variance Optimization ──────────────────────────────────────────────


def mean_variance(expected_returns: dict[str, float],
                  cov: dict[str, dict[str, float]],
                  risk_free: float = 0.05,
                  max_weight: float = 0.10,
                  target_vol: float | None = None) -> dict[str, float]:
    """Mean-variance optimal portfolio (Markowitz).

    Uses a simple gradient-free approach: samples along the efficient frontier
    and picks the portfolio with the highest Sharpe ratio.

    Args:
        expected_returns: {symbol: annualized return}
        cov: covariance matrix from cov_matrix()
        risk_free: risk-free rate (annualized, e.g. 0.05 = 5%%)
        max_weight: maximum allocation to any single asset
        target_vol: if set, find portfolio with this volatility (annualized)

    Returns:
        {symbol: weight} — weights sum to 1.0
    """
    symbols = sorted(set(expected_returns) & set(cov))
    if len(symbols) < 2:
        return {s: 1.0 / max(len(symbols), 1) for s in symbols}  # equal weight

    n = len(symbols)
    ew = 1.0 / n

    # Simple grid search over a few weight distributions
    best_sharpe = -1e9
    best_weights: dict | None = None

    for _ in range(1000):
        # Generate random weights with max_weight constraint
        raw = {}
        remaining = 1.0
        for i, sym in enumerate(symbols):
            if i == n - 1:
                w = remaining
            else:
                w = min(max_weight, remaining * (0.5 + 0.5 * (i / n)))
                w = max(0, w)
            raw[sym] = w
            remaining -= w
            if remaining <= 0:
                break

        if remaining > 0.01:
            # Distribute remaining weight
            for sym in symbols:
                add = remaining / n
                raw[sym] = min(max_weight, raw.get(sym, 0) + add)

        # Normalize
        total = sum(raw.values())
        if total <= 0:
            continue
        weights = {s: w / total for s, w in raw.items()}

        # Compute portfolio stats
        p_ret = sum(weights[s] * expected_returns.get(s, 0) for s in weights)
        p_var = _portfolio_variance(weights, cov)
        if p_var <= 0:
            continue
        p_vol = math.sqrt(p_var)

        if target_vol:
            score = -abs(p_vol - target_vol)
        else:
            # Sharpe ratio
            excess = p_ret - risk_free
            score = excess / p_vol if p_vol > 0 else -1e9

        if score > best_sharpe:
            best_sharpe = score
            best_weights = dict(weights)

    if best_weights is None:
        return {s: ew for s in symbols}

    return best_weights


# ── Risk Parity ─────────────────────────────────────────────────────────────


def _risk_contribution(weights: dict[str, float],
                       cov: dict[str, dict[str, float]]) -> dict[str, float]:
    """Compute each asset's marginal risk contribution."""
    p_var = _portfolio_variance(weights, cov)
    if p_var <= 0:
        return {s: 1.0 / max(len(weights), 1) for s in weights}

    p_vol = math.sqrt(p_var)
    contrib = {}
    for sa in weights:
        mc = sum(weights[sb] * cov.get(sa, {}).get(sb, 0) for sb in weights)
        contrib[sa] = (weights[sa] * mc) / p_vol if p_vol > 0 else 0.0
    return contrib


def risk_parity(cov: dict[str, dict[str, float]],
                max_weight: float = 0.10,
                max_iter: int = 100) -> dict[str, float]:
    """Risk parity portfolio (equal risk contribution).

    Uses an iterative Newton-like method to find weights where each asset
    contributes equally to total portfolio risk.

    Args:
        cov: covariance matrix from cov_matrix()
        max_weight: maximum allocation to any single asset
        max_iter: maximum iterations

    Returns:
        {symbol: weight}
    """
    symbols = sorted(cov.keys())
    if len(symbols) < 2:
        return {s: 1.0 / max(len(symbols), 1) for s in symbols}

    n = len(symbols)
    # Initialize with equal weight
    weights: dict[str, float] = {s: 1.0 / n for s in symbols}
    target_rc = 1.0 / n

    for _ in range(max_iter):
        rc = _risk_contribution(weights, cov)
        total_rc = sum(rc.values())
        if total_rc <= 0:
            break

        # Adjust: increase weight for assets with below-target risk contribution
        max_diff = 0.0
        for s in symbols:
            diff = target_rc - (rc.get(s, 0) / total_rc if total_rc > 0 else 0)
            max_diff = max(max_diff, abs(diff))
            adjustment = 0.05 * diff
            weights[s] = max(0, weights[s] * (1 + adjustment))

        # Apply max_weight constraint
        for s in symbols:
            weights[s] = min(max_weight, weights[s])

        # Normalize
        total = sum(weights.values())
        if total <= 0:
            return {s: 1.0 / n for s in symbols}
        weights = {s: w / total for s, w in weights.items()}

        if max_diff < 0.01:
            break

    return weights


# ── Kelly Criterion ─────────────────────────────────────────────────────────


def kelly_criterion(prob_win: float, odds: float,
                    bankroll: float = 1.0,
                    fraction: float = 0.25) -> dict[str, float]:
    """Kelly criterion for position sizing.

    Args:
        prob_win: estimated probability of winning (0-1)
        odds: net odds received on the bet (e.g., 2.0 means double or nothing)
        bankroll: total available capital
        fraction: fractional Kelly (0.25 = 25%% Kelly = conservative)

    Returns:
        {"recommended_bet": float, "fraction_of_bankroll": float,
         "kelly_percentage": float, "message": str}
    """
    kelly_pct = (prob_win * odds - 1) / (odds - 1) if odds > 1 else 0.0
    kelly_pct = max(0.0, min(1.0, kelly_pct))

    # Fractional Kelly
    recommended_pct = kelly_pct * fraction
    recommended_bet = bankroll * recommended_pct

    message = "no bet" if kelly_pct <= 0 else "full Kelly" if fraction >= 1.0 else f"{fraction*100:.0f}% Kelly"

    return {
        "recommended_bet": round(recommended_bet, 2),
        "fraction_of_bankroll": round(recommended_pct, 4),
        "kelly_percentage": round(kelly_pct, 4),
        "message": message,
        "confidence": "high" if kelly_pct > 0.1 else "low" if kelly_pct <= 0 else "medium",
    }


# ── Efficient Frontier ─────────────────────────────────────────────────────


def efficient_frontier(expected_returns: dict[str, float],
                       cov: dict[str, dict[str, float]],
                       n_points: int = 20,
                       max_weight: float = 0.10) -> list[dict[str, Any]]:
    """Compute points along the efficient frontier.

    Returns a list of dicts, each representing a portfolio on the frontier:
        {"ret": annualized_return, "vol": annualized_vol, "sharpe": sharpe,
         "weights": {symbol: weight}}
    """
    symbols = sorted(set(expected_returns) & set(cov))
    if len(symbols) < 2:
        return []

    # Find min-variance and max-return portfolios via grid search
    min_vol = float("inf")
    max_ret = -float("inf")

    frontier: list[dict] = []
    n = len(symbols)

    for _ in range(n_points * 10):  # Dense sampling
        raw = {}
        remaining = 1.0
        for i, sym in enumerate(symbols):
            if i == n - 1:
                raw[sym] = remaining
            else:
                w = min(max_weight, remaining * (0.1 + 0.9 * (i / n)))
                w = max(0, w)
            raw[sym] = w
            remaining -= w
            if remaining <= 0:
                break
        total = sum(raw.values())
        if total <= 0:
            continue
        weights = {s: w / total for s, w in raw.items()}
        p_ret = sum(weights[s] * expected_returns.get(s, 0) for s in weights)
        p_var = _portfolio_variance(weights, cov)
        if p_var <= 0:
            continue
        p_vol = math.sqrt(p_var)
        frontier.append({"ret": p_ret, "vol": p_vol, "weights": dict(weights)})
        min_vol = min(min_vol, p_vol)
        max_ret = max(max_ret, p_ret)

    if not frontier:
        return []

    # Sort by volatility and extract frontier points
    frontier.sort(key=lambda p: p["vol"])

    # Downsample to n_points
    step = max(1, len(frontier) // n_points)
    result = []
    for i in range(0, len(frontier), step):
        p = frontier[i]
        sharpe = (p["ret"] - 0.05) / p["vol"] if p["vol"] > 0 else 0
        result.append({
            "ret": round(p["ret"], 4),
            "vol": round(p["vol"], 4),
            "sharpe": round(sharpe, 4),
            "weights": p["weights"],
        })

    return result
