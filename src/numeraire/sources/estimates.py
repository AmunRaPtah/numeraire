"""Analyst consensus EPS estimates + revision trend — Yahoo Finance (keyless).

True consensus estimate data (I/B/E/S, Zacks, FactSet) is proprietary/paid. Yahoo's
`quoteSummary` earningsTrend module is a free, keyless substitute — same endpoint
family as sources/prices.py. Each period (0q/+1q/0y/+1y) already carries a built-in
revision trend (current estimate vs 7/30/60/90 days ago), so even a single fetch
gives revision momentum; weekly re-fetches (event_date=knowledge_date=fetch date)
accumulate a genuine bitemporal history of what was known when — a snapshot fact,
not a restatable one, so there's no lookahead risk the way there is for fundamentals.

Unlike the `chart` endpoint prices.py uses, `quoteSummary` requires a session cookie
+ CSRF "crumb" (Yahoo's anti-scraping gate). We bootstrap that once per process and
reuse it for the whole batch (~500 tickers) — bootstrapping per-ticker would both be
wasteful and trip Yahoo's rate limiter, which is tighter on this endpoint than on
`chart`. If the bootstrap or a given ticker fails, we degrade gracefully (skip, don't
raise) — this is a best-effort free substitute for paid data, not a guaranteed feed.
"""

from __future__ import annotations

import contextlib
import http.cookiejar
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone

from .. import config
from ..landing import merge_jsonl

QUOTE_SUMMARY = (
    "https://query1.finance.yahoo.com/v10/finance/quoteSummary/{t}?modules=earningsTrend&crumb={crumb}"
)
GET_CRUMB = "https://query1.finance.yahoo.com/v1/test/getcrumb"
WARMUP = "https://fc.yahoo.com"
UA = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}
KEY = ("ticker", "period", "fetched_date")

_opener_cache: tuple | None = None  # (opener, crumb) — bootstrapped once, reused


def _bootstrap():
    """Warm up a cookie session + fetch a CSRF crumb. Cached for the process lifetime."""
    global _opener_cache
    if _opener_cache is not None:
        return _opener_cache
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    # fc.yahoo.com 404s but still seeds cookies via redirects
    with contextlib.suppress(Exception):
        opener.open(urllib.request.Request(WARMUP, headers=UA), timeout=15)
    try:
        crumb = opener.open(urllib.request.Request(GET_CRUMB, headers=UA), timeout=15).read().decode()
    except Exception as e:
        print(f"[estimates] crumb bootstrap failed (will skip estimates this run): {e}")
        _opener_cache = (None, None)
        return _opener_cache
    _opener_cache = (opener, crumb)
    return _opener_cache


def _raw(d: dict | None):
    return (d or {}).get("raw")


def ingest(ticker: str) -> tuple[str, int, int]:
    t = ticker.upper()
    opener, crumb = _bootstrap()
    if opener is None:
        return ("", 0, 0)
    url = QUOTE_SUMMARY.format(t=t, crumb=urllib.parse.quote(crumb))
    try:
        payload = json.loads(opener.open(urllib.request.Request(url, headers=UA), timeout=30).read())
    except (urllib.error.URLError, urllib.error.HTTPError) as e:
        print(f"[estimates] {t}: {e}")
        return ("", 0, 0)
    results = ((payload.get("quoteSummary") or {}).get("result")) or []
    if not results:
        print(f"[estimates] {t}: no data")
        return ("", 0, 0)
    trend = ((results[0].get("earningsTrend") or {}).get("trend")) or []
    fetched = datetime.now(timezone.utc).isoformat()
    fetched_date = date.today().isoformat()
    rows = []
    for p in trend:
        period = p.get("period")
        if not period:
            continue
        ee, et, er = p.get("earningsEstimate") or {}, p.get("epsTrend") or {}, p.get("epsRevisions") or {}
        rows.append(
            {
                "ticker": t,
                "period": period,
                "fetched_date": fetched_date,
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
            }
        )
    if not rows:
        print(f"[estimates] {t}: no trend periods")
        return ("", 0, 0)
    src = config.raw_source_dir("estimates")
    path = src / f"{t}.jsonl"
    total, added = merge_jsonl(path, rows, KEY)
    print(f"[estimates] {t}: {len(rows)} periods, +{added} new ({total} total) -> {path.name}")
    return (config.rel_data_path(path), total, added)
