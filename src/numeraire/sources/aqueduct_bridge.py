"""aqueduct bridge — link a ticker to its clinical-trial pipeline (the pharma edge).

Reads aqueduct's clinical_trials (read-only) and attaches each company's trials
(phase/status/indication) to its ticker/CIK via a sponsor-name match. This is what
turns "a biotech stock" into "a biotech stock with a Phase-3 readout due in Q3 and 14
months of cash" -- pipeline catalysts fused with EDGAR financials.

Coverage = whatever aqueduct has harvested; add pharma sponsors to aqueduct's topics
watchlist to deepen it. NOTE: a fuzzy name match (first significant token); the proper
fix is a security-master sponsor-alias -> CIK table (ADR-4/8).
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone

import duckdb

from .. import config
from ..landing import merge_jsonl
from . import edgar

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
    for row in edgar._tickers().values():
        if row.get("ticker", "").upper() == ticker.upper():
            return row.get("title")
    return None


def _match_token(title: str) -> str | None:
    toks = [t for t in re.sub(r"[^a-z0-9 ]", " ", title.lower()).split() if len(t) > 2 and t not in _STOP]
    return toks[0] if toks else None


def ingest(ticker: str) -> tuple[str, int, int]:
    title = _company_title(ticker)
    cik = edgar.cik_for(ticker)
    tok = _match_token(title) if title else None
    if not tok:
        print(f"[aqbridge] {ticker}: no company name")
        return ("", 0, 0)
    if not os.path.exists(AQ_WAREHOUSE):
        print(f"[aqbridge] aqueduct warehouse not found at {AQ_WAREHOUSE}")
        return ("", 0, 0)
    con = duckdb.connect(AQ_WAREHOUSE, read_only=True)
    try:
        rows = con.execute(
            """
            SELECT nct_id, title, status, phases, conditions, interventions,
                   start_date, completion_date, lead_sponsor
            FROM clinical_trials WHERE lower(lead_sponsor) LIKE ?
        """,
            [f"%{tok}%"],
        ).fetchall()
    finally:
        con.close()
    fetched = datetime.now(timezone.utc).isoformat()
    out = [
        {
            "ticker": ticker.upper(),
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
    path = pdir / f"{ticker.upper()}.jsonl"
    total, added = merge_jsonl(path, out, KEY) if out else (0, 0)
    print(f"[aqbridge] {ticker} (~'{tok}'): {len(out)} trials, +{added} ({total})")
    return (config.rel_data_path(path), total, added)
