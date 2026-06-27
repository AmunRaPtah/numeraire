"""Forward-looking composite signal — today's ranked ticker list.

Same five-factor model as the backtest (no parameter fitting, equal-weight
cross-sectional z-scores) but evaluated at the most recent data to produce
an actionable ranking:

  rank  ticker  comp   mom   ey    bp    roe   gm   price  fac
     1  NVDA   +2.41  +1.83  +0.42 -0.31 +0.88 +0.59  131.50  5/5
   ...

Interpretation:
  comp  — composite z-score (higher = more attractive across all factors)
  mom   — 12-1 momentum z-score (12m return skipping last month)
  ey    — earnings yield z-score (higher = cheaper on earnings)
  bp    — book-to-price z-score  (higher = cheaper on book value)
  roe   — return-on-equity z-score (higher = more profitable)
  gm    — gross-margin z-score    (higher = better quality)
  fac   — how many of the 5 factors could be computed (EDGAR coverage)

Tickers without EDGAR data rank on momentum alone (neutral 0.0 on value/quality).
Run `numeraire ingest-universe` to populate the full price universe with EDGAR data.
"""

from __future__ import annotations

import math
from datetime import date

from . import features as _ft
from . import warehouse as _wh
from .storage import connect


def _last_prices(con) -> dict[str, tuple[float, float]]:
    """Most recent (adjclose, close) per ticker from the prices table."""
    try:
        rows = con.execute("""
            SELECT ticker, arg_max(adjclose, event_date), arg_max(close, event_date)
            FROM prices
            WHERE adjclose IS NOT NULL
            GROUP BY ticker
        """).fetchall()
        return {r[0]: (float(r[1]), float(r[2])) for r in rows if r[1] and r[2]}
    except Exception:
        return {}


def _pit_momentum(con, asof: str) -> dict[str, float]:
    """12-1 momentum: monthly adjclose at (asof-1m) / (asof-13m) - 1.

    Uses only data up to `asof` — no lookahead. Tickers with insufficient history
    are silently excluded.
    """
    try:
        rows = con.execute("""
            WITH monthly AS (
                SELECT ticker,
                       date_trunc('month', event_date) AS m,
                       arg_max(adjclose, event_date)   AS px
                FROM prices
                WHERE adjclose IS NOT NULL
                  AND event_date <= CAST(? AS DATE)
                GROUP BY ticker, m
            )
            SELECT a.ticker,
                   a.px AS px_lag1,
                   b.px AS px_lag13
            FROM monthly a
            JOIN monthly b ON a.ticker = b.ticker
            WHERE a.m = date_trunc('month', CAST(? AS DATE)) - INTERVAL '1 month'
              AND b.m = date_trunc('month', CAST(? AS DATE)) - INTERVAL '13 months'
        """, [asof, asof, asof]).fetchall()
    except Exception:
        return {}
    return {
        r[0]: float(r[1]) / float(r[2]) - 1
        for r in rows
        if r[1] and r[2] and float(r[2]) > 0
    }


def rank(asof: str | None = None, top: int | None = None, con=None) -> list[dict]:
    """Compute and return ranked signal rows.

    Returns list of dicts sorted by composite descending, each containing:
    ticker, composite, mom, ey, bp, roe, gm, price, n_factors
    """
    asof = asof or date.today().isoformat()
    owns = con is None
    con = con or connect()
    try:
        _wh._load_aux(con)

        last = _last_prices(con)
        if not last:
            return []

        # survivorship-free filter if membership table is loaded
        has_membership = con.execute(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_name='index_membership'"
        ).fetchone()[0]
        member_filter: set | None = None
        if has_membership:
            member_filter = set(_wh.members_as_of(asof, con=con))

        adj_prices = {tk: v[0] for tk, v in last.items()}
        raw_prices = {tk: v[1] for tk, v in last.items()}

        if member_filter is not None:
            adj_prices = {tk: px for tk, px in adj_prices.items() if tk in member_filter}
            raw_prices = {tk: px for tk, px in raw_prices.items() if tk in member_filter}

        if not adj_prices:
            return []

        mom = _pit_momentum(con, asof)
        # restrict to tickers with 13+ months of price history
        eligible = {tk for tk in adj_prices if tk in mom}
        if not eligible:
            return []

        adj_prices = {tk: px for tk, px in adj_prices.items() if tk in eligible}
        raw_prices = {tk: px for tk, px in raw_prices.items() if tk in eligible}

        tk_cik = _ft.ticker_cik_map()
        fundl = _ft.compute(con, tk_cik, asof, adj_prices)

        z_mom = _ft.zscore({tk: mom[tk] for tk in eligible})
        z_ey  = _ft.zscore({tk: fundl[tk]["ey"]  for tk in eligible})
        z_bp  = _ft.zscore({tk: fundl[tk]["bp"]  for tk in eligible})
        z_roe = _ft.zscore({tk: fundl[tk]["roe"] for tk in eligible})
        z_gm  = _ft.zscore({tk: fundl[tk]["gm"]  for tk in eligible})

        rows = []
        for tk in eligible:
            comp = (z_mom.get(tk, 0.0) + z_ey.get(tk, 0.0) + z_bp.get(tk, 0.0)
                    + z_roe.get(tk, 0.0) + z_gm.get(tk, 0.0))
            n_factors = 1 + sum(
                1 for k in ("ey", "bp", "roe", "gm")
                if fundl[tk].get(k) is not None
            )
            rows.append({
                "ticker":    tk,
                "composite": comp,
                "mom":       mom[tk],
                "ey":        fundl[tk]["ey"],
                "bp":        fundl[tk]["bp"],
                "roe":       fundl[tk]["roe"],
                "gm":        fundl[tk]["gm"],
                "z_mom":     z_mom.get(tk, 0.0),
                "z_ey":      z_ey.get(tk, 0.0),
                "z_bp":      z_bp.get(tk, 0.0),
                "z_roe":     z_roe.get(tk, 0.0),
                "z_gm":      z_gm.get(tk, 0.0),
                "price":     raw_prices[tk],
                "n_factors": n_factors,
            })

        rows.sort(key=lambda r: r["composite"], reverse=True)
        return rows[:top] if top else rows

    finally:
        if owns:
            con.close()


def print_signals(asof: str | None = None, top: int = 40, con=None) -> None:
    asof = asof or date.today().isoformat()
    rows = rank(asof=asof, con=con)

    if not rows:
        print("[signals] no price data found.")
        print("  Run: numeraire prices AAPL MSFT NVDA ...  (or ingest-universe)")
        return

    n_full = sum(1 for r in rows if r["n_factors"] == 5)
    n_partial = sum(1 for r in rows if 1 < r["n_factors"] < 5)
    n_mom_only = sum(1 for r in rows if r["n_factors"] == 1)

    print(f"[signals] {asof}  ranked={len(rows)}  "
          f"full_factors={n_full}  partial={n_partial}  momentum_only={n_mom_only}")
    if n_mom_only > 0:
        print(f"          tip: run `numeraire ingest-universe` to add EDGAR "
              f"value/quality factors for {n_mom_only} tickers")
    print()

    def _fz(v):
        if v is None or not math.isfinite(v):
            return "    —"
        return f"{v:+.2f}"

    def _fr(v):
        if v is None or not math.isfinite(v):
            return "         —"
        return f"{v:+10.1%}"

    col = "{:>3}  {:<6}  {:>5}  {:>5}  {:>5}  {:>5}  {:>5}  {:>5}  {:>9}  {:>5}"
    hdr = col.format("#", "ticker", "comp", "mom", "ey", "bp", "roe", "gm", "price", "fac")
    print(hdr)
    print("—" * len(hdr))
    for i, r in enumerate(rows[:top], 1):
        print(col.format(
            i,
            r["ticker"],
            _fz(r["composite"]),
            _fz(r["z_mom"]),
            _fz(r["z_ey"]),
            _fz(r["z_bp"]),
            _fz(r["z_roe"]),
            _fz(r["z_gm"]),
            f"{r['price']:9.2f}",
            f"{r['n_factors']}/5",
        ))

    if len(rows) > top:
        print(f"  ... {len(rows) - top} more (pass N to show more: `numeraire signals 100`)")

    print()
    print("  Raw factor values (not z-scored):")
    sub_hdr = "  {:>3}  {:<6}  {:>9}  {:>9}  {:>9}  {:>9}  {:>9}  {:>9}".format(
        "#", "ticker", "mom(%)", "EY(%)", "B/P(%)", "ROE(%)", "GrMgn(%)", "price")
    print(sub_hdr)
    print("  " + "—" * (len(sub_hdr) - 2))
    for i, r in enumerate(rows[:top], 1):
        print("  {:>3}  {:<6}  {}  {}  {}  {}  {}  {:>9.2f}".format(
            i, r["ticker"],
            _fr(r["mom"]),
            _fr(r["ey"]),
            _fr(r["bp"]),
            _fr(r["roe"]),
            _fr(r["gm"]),
            r["price"],
        ))
