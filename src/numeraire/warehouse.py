"""Bitemporal warehouse build + point-in-time query.

Loads landed EDGAR observations into `fundamentals` (one row per
cik/tag/unit/period/filing). The point-in-time query reconstructs what was *known*
on a given date — the cornerstone that makes backtests honest (no lookahead, sees
the originally-reported value, not a later restatement).
"""

from __future__ import annotations

from . import config
from .storage import connect


def build(con=None) -> int:
    owns = con is None
    con = con or connect()
    try:
        pattern = str(config.RAW_DIR / "edgar" / "*.jsonl")
        con.execute("DROP TABLE IF EXISTS fundamentals")
        con.execute(f"""
            CREATE TABLE fundamentals AS
            SELECT cik, entity, taxonomy, tag, unit,
                   TRY_CAST(start AS DATE) AS start_date,
                   TRY_CAST("end" AS DATE)  AS event_date,    -- when it applies
                   TRY_CAST(filed AS DATE)  AS knowledge_date, -- when it was knowable
                   CAST(val AS DOUBLE) AS val,
                   accn, fy, fp, form, frame
            FROM read_json_auto('{pattern}', format='newline_delimited', union_by_name=true)
        """)
        n = con.execute("SELECT count(*) FROM fundamentals").fetchone()[0]
        print(f"[build]   fundamentals: {n:,} observations")
        return n
    finally:
        if owns: con.close()


def as_of(cik: int, tag: str, asof: str, unit: str = "USD", con=None):
    """Point-in-time series: for each period, the value as KNOWN on `asof` date.

    For every event_date, picks the latest filing with knowledge_date <= asof — i.e. the
    value you'd actually have had on that date, restatements after `asof` invisible.
    """
    owns = con is None
    con = con or connect()
    try:
        return con.execute("""
            SELECT event_date, val, knowledge_date, form, accn FROM (
              SELECT *, row_number() OVER (
                  PARTITION BY event_date ORDER BY knowledge_date DESC, accn DESC) rn
              FROM fundamentals
              WHERE cik = ? AND tag = ? AND unit = ?
                AND knowledge_date IS NOT NULL AND knowledge_date <= TRY_CAST(? AS DATE)
            ) WHERE rn = 1 ORDER BY event_date
        """, [cik, tag, unit, asof]).fetchall()
    finally:
        if owns: con.close()
