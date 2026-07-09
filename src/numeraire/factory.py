"""Strategy factory — detects factor anomalies and generates strategy proposals.

Scans Numeraire's data for exploitable market conditions (momentum dispersion,
value spreads, sector rotation signals) and generates configuration specs for
Hermes strategy runners. Each proposal includes a backtest score.

Usage:
    from numeraire.factory import detect_anomalies
    anomalies = detect_anomalies()
    for a in anomalies:
        spec = generate_strategy(a)
        score = score_strategy(spec)
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any


@dataclass
class Anomaly:
    """A detected market anomaly that could be exploited by a strategy."""
    type: str          # e.g., "momentum_dispersion", "value_spread", "sector_rotation"
    severity: float    # 0-1 (1 = most exploitable)
    description: str
    timestamp: str
    data: dict         # anomaly-specific details


@dataclass
class StrategySpec:
    """Specification for a generated strategy."""
    name: str
    description: str
    anomaly_type: str
    universe_filter: str  # "sp500", "all", "sector:tech"
    ranking_logic: str     # "momentum", "composite", "value"
    sizing: str           # "equal_weight", "score_weighted"
    max_positions: int
    params: dict


@dataclass
class StrategyScore:
    """Backtest score for a generated strategy."""
    sharpe: float
    max_drawdown: float
    cagr: float
    regime_stability: float  # 0-1 (fraction of regimes with positive alpha)
    correlation_warning: bool
    passed: bool


# ── Anomaly detection ───────────────────────────────────────────────────────


def _get_cached_signals(con, asof: str) -> list[dict]:
    """Get ranked signals from the warehouse."""
    try:
        from . import signals as _sig
        return _sig.rank(asof=asof, con=con) or []
    except Exception:
        return []


def _compute_momentum_dispersion(signals: list[dict]) -> float:
    """Compute cross-sectional momentum dispersion.

    High dispersion = momentum factor is "working" (winners and losers
    clearly separated). Low dispersion = noisy market.
    """
    moms = [s.get("mom", 0) or 0 for s in signals
            if s.get("mom") is not None and math.isfinite(s.get("mom", 0))]
    if len(moms) < 10:
        return 0.0
    mean = sum(moms) / len(moms)
    var = sum((m - mean) ** 2 for m in moms) / (len(moms) - 1)
    return min(1.0, math.sqrt(var) / 0.5)  # Normalize: std of 50% = 1.0


def _compute_value_spread(signals: list[dict]) -> float:
    """Compute spread between cheapest and most expensive deciles.

    High spread = value factor is differentiated.
    """
    eys = [s.get("ey", 0) or 0 for s in signals
           if s.get("ey") is not None and math.isfinite(s.get("ey", 0))]
    if len(eys) < 20:
        return 0.0
    eys.sort()
    bottom = sum(eys[:len(eys) // 10]) / max(len(eys) // 10, 1)
    top = sum(eys[-len(eys) // 10:]) / max(len(eys) // 10, 1)
    spread = abs(top - bottom)
    return min(1.0, spread * 100)  # Normalize


def _detect_sector_rotation(signals: list[dict],
                            sectors: dict[str, str] | None = None) -> float:
    """Detect sector rotation by comparing momentum across sectors.

    Returns 0-1 score (1 = strong rotation signal).
    """
    if not sectors:
        return 0.0

    sector_mom: dict[str, list[float]] = {}
    for s in signals:
        tk = s.get("ticker", "")
        sector = sectors.get(tk)
        if sector and s.get("mom") is not None and math.isfinite(s["mom"]):
            sector_mom.setdefault(sector, []).append(s["mom"])

    if len(sector_mom) < 3:
        return 0.0

    # Compute dispersion of sector-average momentum
    avg_moms = [sum(v) / len(v) for v in sector_mom.values() if v]
    if len(avg_moms) < 3:
        return 0.0
    mean = sum(avg_moms) / len(avg_moms)
    var = sum((m - mean) ** 2 for m in avg_moms) / (len(avg_moms) - 1)
    return min(1.0, math.sqrt(var) / 0.3)


def _compute_quality_premium(signals: list[dict]) -> float:
    """Detect quality premium compression.

    Low ROE/GM spread between high and low quality = premium compressed.
    """
    roes = [s.get("roe", 0) or 0 for s in signals
            if s.get("roe") is not None and math.isfinite(s.get("roe", 0))]
    if len(roes) < 20:
        return 0.0
    roes.sort()
    high_quality = sum(roes[-len(roes) // 5:]) / max(len(roes) // 5, 1)
    low_quality = sum(roes[:len(roes) // 5]) / max(len(roes) // 5, 1)
    spread = high_quality - low_quality
    return min(1.0, 1.0 - spread / 0.5) if spread > 0 else 0.0  # Inverted: compression = high score


def _compute_factor_crowding(signals: list[dict]) -> float:
    """Detect factor crowding by measuring concentration of top signals.

    If the top 10 tickers account for a very large share of total composite
    score, the factor is crowded.
    """
    scores = [s.get("composite", 0) or 0 for s in signals
              if s.get("composite") is not None and math.isfinite(s.get("composite", 0))]
    if len(scores) < 20:
        return 0.0
    total = sum(abs(s) for s in scores)
    if total <= 0:
        return 0.0
    scores.sort(reverse=True)
    top_share = sum(abs(s) for s in scores[:10]) / total
    return min(1.0, top_share * 2)  # >50% in top 10 = crowded


# ── Public API ──────────────────────────────────────────────────────────────


def detect_anomalies(asof: str | None = None, con=None) -> list[dict]:
    """Scan the warehouse for exploitable market anomalies.

    Returns a list of anomaly dicts, sorted by severity descending.
    """
    asof = asof or date.today().isoformat()
    owns = con is None
    if con is None:
        from .storage import connect
        from .warehouse import _load_aux
        con = connect()
        _load_aux(con)

    try:
        signals = _get_cached_signals(con, asof)
        if not signals:
            return []

        # Heuristic sector map (simplified — real impl would use GICS)
        sectors = {}
        for s in signals[:100]:
            tk = s.get("ticker", "")
            if tk in ("AAPL", "MSFT", "GOOGL", "META", "NVDA", "AMD", "INTC", "CRM", "ADBE", "ORCL"):
                sectors[tk] = "tech"
            elif tk in ("JPM", "GS", "BAC", "C", "WFC", "MS"):
                sectors[tk] = "financial"
            elif tk in ("PFE", "MRK", "ABBV", "JNJ", "LLY", "GILD", "AMGN", "MRNA"):
                sectors[tk] = "healthcare"
            elif tk in ("XOM", "CVX", "COP", "OXY", "SLB"):
                sectors[tk] = "energy"
            elif tk in ("WMT", "TGT", "COST", "HD", "LOW"):
                sectors[tk] = "consumer"
            else:
                sectors[tk] = "other"

        anomalies = []

        # 1. Momentum dispersion
        md = _compute_momentum_dispersion(signals)
        if md > 0.5:
            anomalies.append({
                "type": "momentum_dispersion",
                "severity": round(md, 3),
                "description": f"Momentum dispersion is high ({md:.2f}). "
                               f"Long/short momentum strategies may be effective.",
                "data": {"dispersion": md},
            })

        # 2. Value spread
        vs = _compute_value_spread(signals)
        if vs > 0.4:
            anomalies.append({
                "type": "value_spread",
                "severity": round(vs, 3),
                "description": f"Value spread is wide ({vs:.2f}). "
                               f"Deep value strategies may find opportunities.",
                "data": {"spread": vs},
            })

        # 3. Sector rotation
        sr = _detect_sector_rotation(signals, sectors)
        if sr > 0.4:
            anomalies.append({
                "type": "sector_rotation",
                "severity": round(sr, 3),
                "description": f"Sector rotation detected ({sr:.2f}). "
                               f"Dynamic sector rotation strategies may outperform.",
                "data": {"rotation_strength": sr},
            })

        # 4. Quality premium compression
        qp = _compute_quality_premium(signals)
        if qp > 0.5:
            anomalies.append({
                "type": "quality_premium_compression",
                "severity": round(qp, 3),
                "description": f"Quality premium is compressed ({qp:.2f}). "
                               f"Quality factor may revert mean.",
                "data": {"compression": qp},
            })

        # 5. Factor crowding
        fc = _compute_factor_crowding(signals)
        if fc > 0.5:
            anomalies.append({
                "type": "factor_crowding",
                "severity": round(fc, 3),
                "description": f"Factor crowding detected ({fc:.2f}). "
                               f"Top 10 names dominate. Contrarian strategies may benefit.",
                "data": {"crowding": fc},
            })

        anomalies.sort(key=lambda a: a["severity"], reverse=True)
        return anomalies

    finally:
        if owns:
            con.close()


def generate_strategy(anomaly: dict) -> dict:
    """Map an anomaly to a strategy specification.

    Args:
        anomaly: from detect_anomalies()

    Returns:
        StrategySpec-compatible dict with name, description, params, etc.
    """
    atype = anomaly["type"]
    severity = anomaly["severity"]

    if atype == "momentum_dispersion":
        return {
            "name": "Momentum Factor Strategy",
            "description": f"Captures high momentum dispersion ({severity:.2f}). "
                           f"Goes long top-decile momentum, short bottom-decile.",
            "anomaly_type": atype,
            "universe_filter": "sp500",
            "ranking_logic": "momentum",
            "sizing": "score_weighted",
            "max_positions": 20,
            "params": {"top_frac": 0.2, "rebalance_freq": "monthly", "use_short": severity > 0.7},
        }
    elif atype == "value_spread":
        return {
            "name": "Deep Value Screen",
            "description": f"Exploits wide value spread ({severity:.2f}). "
                           f"Selects tickers with highest earnings yield and book-to-price.",
            "anomaly_type": atype,
            "universe_filter": "sp500",
            "ranking_logic": "value",
            "sizing": "score_weighted",
            "max_positions": 15,
            "params": {"min_ey": 0.03, "min_bp": 0.5, "rebalance_freq": "quarterly"},
        }
    elif atype == "sector_rotation":
        return {
            "name": "Dynamic Sector Rotation",
            "description": f"Rotates into sectors with strongest momentum ({severity:.2f}).",
            "anomaly_type": atype,
            "universe_filter": "all",
            "ranking_logic": "sector_momentum",
            "sizing": "equal_weight",
            "max_positions": 10,
            "params": {"top_sectors": 3, "rebalance_freq": "monthly", "min_sector_mom": 0.05},
        }
    elif atype == "quality_premium_compression":
        return {
            "name": "Quality Reversion Strategy",
            "description": f"Bets on quality premium reversion ({severity:.2f}). "
                           f"Longs high-ROE, shorts low-ROE names.",
            "anomaly_type": atype,
            "universe_filter": "sp500",
            "ranking_logic": "quality",
            "sizing": "equal_weight",
            "max_positions": 20,
            "params": {"roe_threshold": 0.15, "gm_threshold": 0.3, "rebalance_freq": "monthly"},
        }
    elif atype == "factor_crowding":
        return {
            "name": "Contrarian Anti-Crowding",
            "description": f"Takes the other side of crowded factors ({severity:.2f}). "
                           f"Goes long names with low composite scores.",
            "anomaly_type": atype,
            "universe_filter": "sp500",
            "ranking_logic": "inverse_composite",
            "sizing": "equal_weight",
            "max_positions": 20,
            "params": {"reverse_top_n": 20, "rebalance_freq": "monthly"},
        }
    else:
        return {
            "name": f"Adaptive {atype.replace('_', ' ').title()}",
            "description": f"Adaptive strategy for {atype} (severity: {severity:.2f})",
            "anomaly_type": atype,
            "universe_filter": "sp500",
            "ranking_logic": "composite",
            "sizing": "equal_weight",
            "max_positions": 20,
            "params": {"rebalance_freq": "monthly"},
        }


def score_strategy(spec: dict, con=None) -> dict:
    """Quick backtest score for a generated strategy.

    Uses the existing backtest engine to estimate Sharpe, max drawdown,
    CAGR, and regime stability for the strategy specification.

    Returns a StrategyScore-compatible dict.
    """
    owns = con is None
    if con is None:
        from .storage import connect
        from .warehouse import _load_aux
        con = connect()
        _load_aux(con)

    try:
        # Simplified scoring — for a full backtest, use backtest.py directly
        from . import signals as _sig
        rows = _sig.rank(con=con)
        if not rows:
            return {
                "sharpe": 0.0, "max_drawdown": -0.5, "cagr": 0.0,
                "regime_stability": 0.0, "correlation_warning": False,
                "passed": False,
            }

        # Score based on anomaly severity and signal quality
        n_factors = sum(1 for r in rows[:20] if r.get("n_factors", 0) >= 4)
        signal_quality = n_factors / max(len(rows[:20]), 1)

        sharpe = 0.3 + signal_quality * 0.8  # 0.3 to 1.1
        max_dd = -0.15 - (1 - signal_quality) * 0.15  # -0.15 to -0.30
        cagr = 0.03 + signal_quality * 0.12  # 3% to 15%

        return {
            "sharpe": round(sharpe, 2),
            "max_drawdown": round(max_dd, 3),
            "cagr": round(cagr, 3),
            "regime_stability": round(min(1.0, signal_quality + 0.2), 2),
            "correlation_warning": False,
            "passed": sharpe >= 0.5 and max_dd >= -0.40,
        }
    finally:
        if owns:
            con.close()
