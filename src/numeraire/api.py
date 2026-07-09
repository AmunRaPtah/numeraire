"""
Numeraire live API — FastAPI server exposing point-in-time financial analytics.

Provides REST endpoints for ranked signals, factor profiles, macro regime,
and investable universe. Read-only — the warehouse is never mutated through this API.

Run with:  python -m numeraire serve [--port 8100]
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import date
from functools import wraps

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from . import signals, universe
from . import warehouse as _wh
from .sources import fred as _fred
from .storage import connect

log = logging.getLogger("numeraire.api")

app = FastAPI(
    title="Numeraire Signal API",
    version="0.1.0",
    description="Point-in-time financial signals, factor profiles, and macro regime data",
)

# ── CORS (allow any origin — Hermes may be on a different port/host) ────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

# ── Simple in-memory response cache ─────────────────────────────────────────

_cache: dict[str, tuple[float, object]] = {}  # key -> (expires_at, value)


def _cached(ttl_s: int = 30):
    """Decorator that caches JSON responses for `ttl_s` seconds."""

    def deco(f):
        @wraps(f)
        async def wrapper(*args, **kw):
            key = f"{f.__name__}:{args}:{sorted(kw.items())}"
            now = time.monotonic()
            if key in _cache:
                exp, val = _cache[key]
                if now < exp:
                    return val
            if asyncio.iscoroutinefunction(f):
                val = await f(*args, **kw)
            else:
                val = f(*args, **kw)
            _cache[key] = (now + ttl_s, val)
            return val

        return wrapper

    return deco


def _open_con():
    """Open a read-only DuckDB connection. Dies with 503 if warehouse unreachable."""
    try:
        con = connect()
        _wh._load_aux(con)
        return con
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Warehouse unavailable: {exc}") from exc


# ── Endpoints ───────────────────────────────────────────────────────────────


@app.get("/health")
@_cached(ttl_s=60)
async def health():
    """Warehouse connectivity and data freshness."""
    con = connect()
    try:
        _wh._load_aux(con)
        p_count = con.execute("SELECT count(*) FROM prices").fetchone()[0]
        f_count = con.execute("SELECT count(*) FROM fundamentals").fetchone()[0]
        has_fred = (
            con.execute("SELECT count(*) FROM information_schema.tables WHERE table_name='fred'").fetchone()[
                0
            ]
            > 0
        )
        return {
            "status": "ok",
            "prices_count": p_count,
            "fundamentals_count": f_count,
            "fred_loaded": bool(has_fred),
            "timestamp": time.time(),
        }
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    finally:
        con.close()


@app.get("/signals")
@_cached(ttl_s=30)
async def ranked_signals(
    top: int = Query(default=40, ge=1, le=200),
    asof: str | None = None,
    universe: str | None = Query(
        default=None, description="Filter to universe: general, pharma_biotech, crypto"
    ),
):
    """Ranked tickers by multi-factor composite score.

    Default is today's signals. Pass ``asof=YYYY-MM-DD`` for a historical snapshot.
    Pass ``universe=general`` to filter to a curated universe.
    """
    asof = asof or date.today().isoformat()
    con = _open_con()
    try:
        rows = signals.rank(asof=asof, top=None, con=con)
        if not rows:
            raise HTTPException(status_code=404, detail="No signal data available")

        # Optional universe filter
        if universe:
            mapping = {
                "general": universe.GENERAL,
                "pharma_biotech": universe.PHARMA_BIOTECH,
                "crypto": universe.CRYPTO,
            }
            tickers = set(mapping.get(universe, []))
            rows = [r for r in rows if r["ticker"] in tickers]

        return {
            "asof": asof,
            "count": min(len(rows), top),
            "signals": rows[:top],
        }
    finally:
        con.close()


@app.get("/factors/{ticker}")
@_cached(ttl_s=300)
async def factor_profile(
    ticker: str,
    asof: str | None = None,
):
    """Per-ticker factor breakdown: earnings yield, book-to-price, ROE, gross margin, momentum."""
    from . import features as _ft

    asof = asof or date.today().isoformat()
    sym = ticker.upper()
    con = _open_con()
    try:
        # Get latest price
        px = con.execute(
            "SELECT close FROM prices "
            "WHERE ticker = ? AND event_date <= CAST(? AS DATE) "
            "ORDER BY event_date DESC LIMIT 1",
            [sym, asof],
        ).fetchone()
        if not px:
            raise HTTPException(status_code=404, detail=f"No price data for {sym}")

        # Factor computation
        tk_cik = _ft.ticker_cik_map()
        cik = tk_cik.get(sym)
        if not cik:
            return {
                "ticker": sym,
                "asof": asof,
                "price": float(px[0]),
                "fundamentals": None,
                "note": "No CIK mapping — ticker may not file EDGAR",
            }

        fundl = _ft.compute(con, tk_cik, asof, {sym: float(px[0])})
        factors = fundl.get(sym, {})

        # Momentum (12-1)
        from .signals import _pit_momentum

        mom = _pit_momentum(con, asof)
        mom_val = mom.get(sym)

        return {
            "ticker": sym,
            "asof": asof,
            "price": float(px[0]),
            "factors": {
                "earnings_yield": factors.get("ey"),
                "book_to_price": factors.get("bp"),
                "return_on_equity": factors.get("roe"),
                "gross_margin": factors.get("gm"),
                "momentum_12_1": mom_val,
            },
        }
    finally:
        con.close()


@app.get("/regime")
@_cached(ttl_s=300)
async def macro_regime(
    asof: str | None = None,
):
    """Current macro regime from FRED data."""
    asof = asof or date.today().isoformat()
    con = _open_con()
    try:
        reg = _fred.regime(con, asof)
        return {
            "asof": asof,
            "label": reg.get("label", "unknown"),
            "display": reg.get("display", "Unknown"),
            "indicators": {
                "fed_rate": reg.get("fed_rate"),
                "curve": reg.get("curve"),
                "hy_spread": reg.get("hy_spread"),
                "vix": reg.get("vix"),
            },
            "confidence": reg.get("confidence", 0.0),
        }
    finally:
        con.close()


@app.get("/universe")
@_cached(ttl_s=300)
async def ticker_universe():
    """Available tickers across all curated universes."""
    return {
        "general": universe.GENERAL,
        "pharma_biotech": universe.PHARMA_BIOTECH,
        "crypto": universe.CRYPTO,
        "default": universe.DEFAULT,
        "total_tickers": len(universe.DEFAULT),
    }


@app.get("/prices/{ticker}")
@_cached(ttl_s=60)
async def price_history(
    ticker: str,
    days: int = Query(default=252, ge=1, le=2520),
    asof: str | None = None,
):
    """Historical price series for a ticker."""
    asof = asof or date.today().isoformat()
    sym = ticker.upper()
    con = _open_con()
    try:
        rows = con.execute(
            "SELECT event_date, open, high, low, close, adjclose, volume "
            "FROM prices "
            "WHERE ticker = ? AND event_date <= CAST(? AS DATE) "
            "ORDER BY event_date DESC LIMIT ?",
            [sym, asof, days],
        ).fetchall()
        if not rows:
            raise HTTPException(status_code=404, detail=f"No price data for {sym}")
        return {
            "ticker": sym,
            "asof": asof,
            "count": len(rows),
            "prices": [
                {
                    "date": r[0].isoformat() if hasattr(r[0], "isoformat") else str(r[0]),
                    "open": r[1],
                    "high": r[2],
                    "low": r[3],
                    "close": r[4],
                    "adjclose": r[5],
                    "volume": r[6],
                }
                for r in rows
            ],
        }
    finally:
        con.close()


@app.get("/universe/{list_name}")
@_cached(ttl_s=300)
async def universe_list(list_name: str):
    """Tickers in a named universe (general, pharma_biotech, crypto, default)."""
    key = list_name.upper().replace("-", "_")
    mapping = {
        "GENERAL": universe.GENERAL,
        "PHARMA_BIOTECH": universe.PHARMA_BIOTECH,
        "CRYPTO": universe.CRYPTO,
        "DEFAULT": universe.DEFAULT,
    }
    tickers = mapping.get(key)
    if tickers is None:
        raise HTTPException(status_code=404, detail=f"Unknown universe: {list_name}")
    return {"universe": list_name, "count": len(tickers), "tickers": tickers}
