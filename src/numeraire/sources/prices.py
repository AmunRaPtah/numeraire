"""EOD prices + corporate actions — Yahoo chart API (keyless).

Yahoo's chart endpoint returns daily OHLCV, adjusted close, AND dividend/split events
in one call (stooq is now behind a JS proof-of-work wall). We store:
  - raw `close` (split-adjusted by Yahoo) -> the price you'd have seen, for PIT signals
  - `adjclose` (split+dividend adjusted)   -> for total-return computations
  - dividends/splits as a separate corporate_actions stream

Point-in-time note: Yahoo's `close` is split-back-adjusted, so the corporate_actions
table is what lets us reconstruct truly unadjusted prices if a strategy needs them.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from .. import config, net
from ..landing import merge_jsonl

CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{t}?period1=0&period2=9999999999&interval=1d&events=div%2Csplits"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
PRICE_KEY = ("ticker", "date")
ACTION_KEY = ("ticker", "date", "type")


def _iso(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()


def ingest(ticker: str) -> tuple[int, int]:
    t = ticker.upper()
    try:
        d = json.loads(net.request(CHART.format(t=t), timeout=30, headers=UA))
    except net.NetworkError as e:
        print(f"[prices]  {t}: {e}")
        return (0, 0)
    res = (d.get("chart") or {}).get("result")
    if not res:
        print(f"[prices]  {t}: no data")
        return (0, 0)
    r = res[0]
    ts = r.get("timestamp") or []
    q = r["indicators"]["quote"][0] if r.get("indicators", {}).get("quote") else {}
    adj = r["indicators"].get("adjclose", [{}])[0].get("adjclose") if r.get("indicators") else None
    fetched = datetime.now(timezone.utc).isoformat()
    prices = []
    for i, t_i in enumerate(ts):
        if q.get("close", [None])[i] is None:
            continue
        prices.append(
            {
                "ticker": t,
                "date": _iso(t_i),
                "open": q["open"][i],
                "high": q["high"][i],
                "low": q["low"][i],
                "close": q["close"][i],
                "adjclose": (adj[i] if adj else None),
                "volume": q["volume"][i],
                "fetched_at": fetched,
            }
        )
    pdir = config.raw_source_dir("prices")
    ptot, padd = merge_jsonl(pdir / f"{t}.jsonl", prices, PRICE_KEY)

    # corporate actions (dividends + splits)
    ev = r.get("events") or {}
    actions = []
    for d_ in (ev.get("dividends") or {}).values():
        actions.append(
            {
                "ticker": t,
                "date": _iso(d_["date"]),
                "type": "dividend",
                "value": d_.get("amount"),
                "fetched_at": fetched,
            }
        )
    for s_ in (ev.get("splits") or {}).values():
        actions.append(
            {
                "ticker": t,
                "date": _iso(s_["date"]),
                "type": "split",
                "value": f"{s_.get('numerator')}/{s_.get('denominator')}",
                "fetched_at": fetched,
            }
        )
    atot = aadd = 0
    if actions:
        adir = config.raw_source_dir("corporate_actions")
        atot, aadd = merge_jsonl(adir / f"{t}.jsonl", actions, ACTION_KEY)
    print(f"[prices]  {t}: {len(prices)} bars (+{padd}), {len(actions)} actions (+{aadd})")
    return (ptot, atot)
