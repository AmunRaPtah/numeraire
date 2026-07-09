"""PIT factor computation — value and quality signals from EDGAR fundamentals.

Factors (all point-in-time, no lookahead — knowledge_date <= rebalance date):
  ey  — earnings yield  = annual NI / market cap   (inverted P/E; higher = cheaper)
  bp  — book-to-price   = book equity / market cap  (inverted P/B)
  roe — return on equity = NI / book equity          (profitability)
  gm  — gross margin    = gross profit / revenues    (quality proxy)

Tickers without ingested EDGAR data get None for all fundamental factors.
Run `numeraire ingest-universe` to bulk-populate the price universe.
"""

from __future__ import annotations

import math
from datetime import date as _date
from datetime import timedelta


def ticker_cik_map() -> dict[str, int]:
    """ticker (uppercase) -> CIK, from SEC's company_tickers.json."""
    from .sources import edgar
    return {
        r["ticker"].upper(): int(r["cik_str"])
        for r in edgar._tickers().values()
        if r.get("ticker") and r.get("cik_str") is not None
    }


def _to_date_str(d) -> str:
    if isinstance(d, _date):
        return d.isoformat()[:10]   # [:10] strips time from datetime subclass
    return str(d)[:10]


def _3yr_cutoff(asof_str: str) -> str:
    d = _date.fromisoformat(asof_str)
    try:
        return d.replace(year=d.year - 3).isoformat()
    except ValueError:
        return (d - timedelta(days=1096)).isoformat()


def _pit_tag(con, tag: str, unit: str, asof: str, fp: str | None) -> dict[int, float]:
    """Latest PIT value of `tag` for all CIKs, as known on `asof`. Returns {cik: val}.

    Only includes values whose event_date is within 3 years of asof — stale filings
    from companies that stopped reporting are excluded.
    """
    cutoff = _3yr_cutoff(asof)
    try:
        if fp:
            rows = con.execute("""
                SELECT cik, val FROM (
                    SELECT cik, val,
                        row_number() OVER (
                            PARTITION BY cik ORDER BY knowledge_date DESC, event_date DESC
                        ) rn
                    FROM fundamentals
                    WHERE tag = ? AND unit = ? AND fp = ?
                      AND knowledge_date IS NOT NULL
                      AND knowledge_date <= CAST(? AS DATE)
                      AND event_date    >= CAST(? AS DATE)
                ) WHERE rn = 1
            """, [tag, unit, fp, asof, cutoff]).fetchall()
        else:
            rows = con.execute("""
                SELECT cik, val FROM (
                    SELECT cik, val,
                        row_number() OVER (
                            PARTITION BY cik ORDER BY knowledge_date DESC, event_date DESC
                        ) rn
                    FROM fundamentals
                    WHERE tag = ? AND unit = ?
                      AND knowledge_date IS NOT NULL
                      AND knowledge_date <= CAST(? AS DATE)
                      AND event_date    >= CAST(? AS DATE)
                ) WHERE rn = 1
            """, [tag, unit, asof, cutoff]).fetchall()
    except Exception:
        return {}
    return {int(cik): float(val) for cik, val in rows if val is not None}


def zscore(vals: dict) -> dict:
    """Cross-sectional z-score normalization.

    None / non-finite values get 0.0 (neutral — they neither help nor hurt ranking).
    Requires >=2 finite values; returns all-zeros otherwise.
    """
    finite = {k: v for k, v in vals.items() if v is not None and math.isfinite(v)}
    if len(finite) < 2:
        return {k: 0.0 for k in vals}
    mean = sum(finite.values()) / len(finite)
    var = sum((v - mean) ** 2 for v in finite.values()) / max(len(finite) - 1, 1)
    sd = math.sqrt(var) if var > 0 else 1.0
    return {k: ((vals[k] - mean) / sd if k in finite else 0.0) for k in vals}


def compute(
    con,
    ticker_cik: dict[str, int],
    asof,
    prices: dict[str, float],
) -> dict[str, dict]:
    """PIT value + quality factors for each ticker in `prices` as of `asof`.

    Returns {ticker: {ey, bp, roe, gm}} — values are float or None.
    Market cap = price × shares_outstanding (both PIT).
    """
    asof_s = _to_date_str(asof)
    ni = _pit_tag(con, "NetIncomeLoss",               "USD",    asof_s, "FY")
    be = _pit_tag(con, "StockholdersEquity",           "USD",    asof_s, "FY")
    gp = _pit_tag(con, "GrossProfit",                  "USD",    asof_s, "FY")
    rv = _pit_tag(con, "Revenues",                     "USD",    asof_s, "FY")
    sh = _pit_tag(con, "CommonStockSharesOutstanding", "shares", asof_s, None)

    out: dict[str, dict] = {}
    for tkr, px in prices.items():
        cik = ticker_cik.get(tkr)
        if not cik or not px or px <= 0:
            out[tkr] = {"ey": None, "bp": None, "roe": None, "gm": None}
            continue
        n = ni.get(cik)
        b = be.get(cik)
        g = gp.get(cik)
        r = rv.get(cik)
        s = sh.get(cik)
        mktcap = px * s if (s and s > 0) else None
        out[tkr] = {
            "ey":  n / mktcap if (n is not None and mktcap and mktcap > 0) else None,
            "bp":  b / mktcap if (b is not None and mktcap and mktcap > 0) else None,
            "roe": n / b      if (n is not None and b and abs(b) > 1e6)    else None,
            "gm":  g / r      if (g is not None and r and r > 0)           else None,
        }
    return out
