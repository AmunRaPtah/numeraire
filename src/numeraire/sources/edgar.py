"""SEC EDGAR connector — keyless, natively bitemporal.

The XBRL companyfacts API gives every reported fact with:
  end   -> the fiscal period it applies to        == EVENT time
  filed -> the date the filing made it public      == KNOWLEDGE time
  accn  -> the accession (which filing)             (restatements differ by accn/filed)

So a single fetch yields the full as-of history: the same `end` reported across an
original 10-Q and a later restated 10-K appears as two rows with different `filed`.
We land each observation; the point-in-time view reconstructs "what was known on date D".
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from .. import config, net
from ..landing import merge_jsonl

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"

# unique identity of one observation; restatements differ by accn -> kept as separate rows
KEY = ("cik", "taxonomy", "tag", "unit", "start", "end", "accn")

_tickers_cache: dict | None = None


def _tickers() -> dict:
    global _tickers_cache
    if _tickers_cache is None:
        _tickers_cache = net.get_json(TICKERS_URL, timeout=30)
    return _tickers_cache


def cik_for(ticker: str) -> int | None:
    t = ticker.upper()
    for row in _tickers().values():
        if row.get("ticker", "").upper() == t:
            return int(row["cik_str"])
    return None


def _flatten(facts: dict, cik: int, entity: str):
    fetched = datetime.now(timezone.utc).isoformat()
    for taxonomy, tags in (facts.get("facts") or {}).items():
        for tag, body in tags.items():
            for unit, points in (body.get("units") or {}).items():
                for p in points:
                    if p.get("val") is None or not p.get("end"):
                        continue
                    yield {
                        "cik": cik,
                        "entity": entity,
                        "taxonomy": taxonomy,
                        "tag": tag,
                        "unit": unit,
                        "start": p.get("start"),
                        "end": p["end"],
                        "val": p["val"],
                        "accn": p.get("accn"),
                        "fy": p.get("fy"),
                        "fp": p.get("fp"),
                        "form": p.get("form"),
                        "filed": p.get("filed"),
                        "frame": p.get("frame"),
                        "fetched_at": fetched,
                    }


def ingest(ticker: str, limit: int | None = None) -> tuple[str, int, int]:
    """Land all XBRL facts for `ticker` as bitemporal observations. Returns (file, total, added)."""
    cik = cik_for(ticker)
    if cik is None:
        print(f"[edgar]   {ticker}: CIK not found")
        return ("", 0, 0)
    try:
        facts = json.loads(net.request(FACTS_URL.format(cik=cik), timeout=45))
    except net.NetworkError as e:
        print(f"[edgar]   {ticker} (CIK {cik}): fetch failed: {e}")
        return ("", 0, 0)
    entity = facts.get("entityName", ticker)
    rows = list(_flatten(facts, cik, entity))
    src = config.raw_source_dir("edgar")
    path = src / f"{ticker.upper()}_CIK{cik:010d}.jsonl"
    total, added = merge_jsonl(path, rows, KEY)
    print(
        f"[edgar]   {ticker} (CIK {cik}, {entity}): {len(rows)} observations, "
        f"+{added} new ({total} total) -> {path.name}"
    )
    return (config.rel_data_path(path), total, added)
