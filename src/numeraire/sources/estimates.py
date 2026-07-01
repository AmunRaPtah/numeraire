"""Analyst consensus EPS estimates + revision trend — Yahoo Finance (keyless).

True consensus estimate data (I/B/E/S, Zacks, FactSet) is proprietary/paid. Yahoo's
`quoteSummary` earningsTrend module is a free, keyless substitute — same endpoint
family as sources/prices.py. Each period (0q/+1q/0y/+1y) already carries a built-in
revision trend (current estimate vs 7/30/60/90 days ago), so even a single fetch
gives revision momentum; weekly re-fetches (event_date=knowledge_date=fetch date)
accumulate a genuine bitemporal history of what was known when — a snapshot fact,
not a restatable one, so there's no lookahead risk the way there is for fundamentals.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone

from .. import config, net
from ..landing import merge_jsonl

QUOTE_SUMMARY = ("https://query1.finance.yahoo.com/v10/finance/quoteSummary/{t}"
                  "?modules=earningsTrend")
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
KEY = ("ticker", "period", "fetched_date")


def _raw(d: dict | None):
    return (d or {}).get("raw")


def ingest(ticker: str) -> tuple[str, int, int]:
    t = ticker.upper()
    try:
        payload = json.loads(net.request(QUOTE_SUMMARY.format(t=t), timeout=30, headers=UA))
    except net.NetworkError as e:
        print(f"[estimates] {t}: {e}"); return ("", 0, 0)
    results = ((payload.get("quoteSummary") or {}).get("result")) or []
    if not results:
        print(f"[estimates] {t}: no data"); return ("", 0, 0)
    trend = ((results[0].get("earningsTrend") or {}).get("trend")) or []
    fetched = datetime.now(timezone.utc).isoformat()
    fetched_date = date.today().isoformat()
    rows = []
    for p in trend:
        period = p.get("period")
        if not period:
            continue
        ee, et, er = p.get("earningsEstimate") or {}, p.get("epsTrend") or {}, p.get("epsRevisions") or {}
        rows.append({
            "ticker": t, "period": period, "fetched_date": fetched_date,
            "avg_estimate": _raw(ee.get("avg")),
            "num_analysts": _raw(ee.get("numberOfAnalysts")),
            "growth": _raw(p.get("growth")),
            "eps_trend_current": _raw(et.get("current")),
            "eps_trend_7d_ago": _raw(et.get("7daysAgo")),
            "eps_trend_30d_ago": _raw(et.get("30daysAgo")),
            "eps_trend_60d_ago": _raw(et.get("60daysAgo")),
            "eps_trend_90d_ago": _raw(et.get("90daysAgo")),
            "revisions_up_7d": _raw(er.get("upLast7days")),
            "revisions_down_7d": _raw(er.get("downLast7days") or er.get("downLast7Days")),
            "revisions_up_30d": _raw(er.get("upLast30days")),
            "revisions_down_30d": _raw(er.get("downLast30days") or er.get("downLast30Days")),
            "fetched_at": fetched,
        })
    if not rows:
        print(f"[estimates] {t}: no trend periods"); return ("", 0, 0)
    src = config.raw_source_dir("estimates")
    path = src / f"{t}.jsonl"
    total, added = merge_jsonl(path, rows, KEY)
    print(f"[estimates] {t}: {len(rows)} periods, +{added} new ({total} total) -> {path.name}")
    return (config.rel_data_path(path), total, added)
