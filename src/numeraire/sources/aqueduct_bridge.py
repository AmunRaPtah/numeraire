"""aqueduct bridge — link a ticker to its clinical-trial pipeline (the pharma edge).

Reads aqueduct's clinical_trials (read-only) and attaches each company's trials
(phase/status/indication) to its ticker/CIK via the security_master sponsor-name
resolver (ADR-4/8): every distinct `lead_sponsor` landed by aqueduct is resolved to
a CIK/ticker, and only the trials that resolve to *this* ticker are kept. This
replaces a forward guess (ticker -> first name token -> substring `LIKE` on
lead_sponsor) that produced false positives (e.g. `%eli%` matches any sponsor
containing "eli" anywhere, not just Eli Lilly) and matched only ~1 row per ticker
before aqueduct's topics.json seeded sponsor-based harvesting. This is what turns
"a biotech stock" into "a biotech stock with a Phase-3 readout due in Q3 and 14
months of cash" -- pipeline catalysts fused with EDGAR financials.

Coverage = whatever aqueduct has harvested; aqueduct's topics.json seeds the top
pharma/biotech names via the `clinicaltrials_sponsor` source (query.lead, not just
disease-term `query.cond`) — extend that list to deepen coverage further.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone

import duckdb

from .. import config
from ..landing import merge_jsonl
from . import edgar, security_master

AQ_WAREHOUSE = os.environ.get("NUMERAIRE_AQUEDUCT_DB", "/root/projects/aqueduct/data/warehouse.duckdb")
KEY = ("ticker", "nct_id")
_STOP = {
    "inc",
    "corp",
    "corporation",
    "ltd",
    "plc",
    "co",
    "the",
    "company",
    "therapeutics",
    "pharmaceuticals",
    "pharma",
    "sciences",
    "holdings",
    "group",
}


def _company_title(ticker: str) -> str | None:
    """EDGAR company title for a ticker — used by fda-universe to build an openFDA sponsor-name token."""
    for row in edgar._tickers().values():
        if row.get("ticker", "").upper() == ticker.upper():
            return row.get("title")
    return None


def _match_token(title: str) -> str | None:
    toks = [t for t in re.sub(r"[^a-z0-9 ]", " ", title.lower()).split() if len(t) > 2 and t not in _STOP]
    return toks[0] if toks else None


def _matching_sponsors(con, cik: int, ticker: str) -> list[str]:
    """Every distinct `lead_sponsor` in aqueduct's clinical_trials that resolves to (cik, ticker)."""
    sponsors = [
        r[0]
        for r in con.execute(
            "SELECT DISTINCT lead_sponsor FROM clinical_trials WHERE lead_sponsor IS NOT NULL"
        ).fetchall()
    ]
    idx = security_master._index()
    return [s for s in sponsors if security_master.resolve(s, idx) == (cik, ticker)]


def ingest(ticker: str) -> tuple[str, int, int]:
    ticker = ticker.upper()
    cik = edgar.cik_for(ticker)
    if cik is None:
        print(f"[aqbridge] {ticker}: no CIK")
        return ("", 0, 0)
    if not os.path.exists(AQ_WAREHOUSE):
        print(f"[aqbridge] aqueduct warehouse not found at {AQ_WAREHOUSE}")
        return ("", 0, 0)
    con = duckdb.connect(AQ_WAREHOUSE, read_only=True)
    try:
        sponsors = _matching_sponsors(con, cik, ticker)
        if not sponsors:
            print(f"[aqbridge] {ticker}: no resolved sponsor match")
            return ("", 0, 0)
        placeholders = ",".join("?" for _ in sponsors)
        rows = con.execute(
            f"""
            SELECT nct_id, title, status, phases, conditions, interventions,
                   start_date, completion_date, lead_sponsor
            FROM clinical_trials WHERE lead_sponsor IN ({placeholders})
            """,
            sponsors,
        ).fetchall()
    finally:
        con.close()
    fetched = datetime.now(timezone.utc).isoformat()
    out = [
        {
            "ticker": ticker,
            "cik": cik,
            "nct_id": r[0],
            "trial_title": r[1],
            "status": r[2],
            "phases": r[3],
            "conditions": r[4],
            "interventions": r[5],
            "start_date": r[6],
            "completion_date": r[7],
            "lead_sponsor": r[8],
            "fetched_at": fetched,
        }
        for r in rows
    ]
    pdir = config.raw_source_dir("pipeline")
    path = pdir / f"{ticker}.jsonl"
    total, added = merge_jsonl(path, out, KEY) if out else (0, 0)
    print(f"[aqbridge] {ticker} ({len(sponsors)} sponsor alias(es)): {len(out)} trials, +{added} ({total})")
    return (config.rel_data_path(path), total, added)
