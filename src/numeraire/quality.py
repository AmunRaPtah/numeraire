"""Ingest-time quality gate for the warehouse — admission control for PIT data.

`validate.py` *reports* integrity problems; this gate *removes* rows that are unusable
for point-in-time analysis right after the warehouse is built, quarantining them (with a
reason) in `<table>_rejected`. Nothing that would poison a backtest survives in the core
numeric streams, and nothing is silently lost — every rejection stays auditable and can
be recovered if a rule proves too strict.

Quarantined rows:
  fundamentals / fred (macro):
      null_knowledge_date  can't be placed in time (invisible to PIT anyway, pollutes aggregates)
      null_event_date      no period it describes
      lookahead            knowledge_date < event_date — impossible for a realized figure;
                           would inject future knowledge into a backtest
      null_value / non_finite_value
  prices:
      null_event_date, null/non-finite/non-positive close, corrupt OHLC (high < low),
      negative volume
"""

from __future__ import annotations

from .storage import connect

# table -> (garbage WHERE clause, reason CASE) for the PIT-critical numeric streams.
_SPECS: dict[str, tuple[str, str]] = {
    "fundamentals": (
        "knowledge_date IS NULL OR event_date IS NULL "
        "OR knowledge_date < event_date "
        "OR val IS NULL OR isnan(val) OR isinf(val)",
        "CASE WHEN knowledge_date IS NULL THEN 'null_knowledge_date' "
        "WHEN event_date IS NULL THEN 'null_event_date' "
        "WHEN knowledge_date < event_date THEN 'lookahead' "
        "WHEN val IS NULL THEN 'null_value' ELSE 'non_finite_value' END",
    ),
    "fred": (
        "knowledge_date IS NULL OR event_date IS NULL "
        "OR val IS NULL OR isnan(val) OR isinf(val)",
        "CASE WHEN knowledge_date IS NULL THEN 'null_knowledge_date' "
        "WHEN event_date IS NULL THEN 'null_event_date' "
        "WHEN val IS NULL THEN 'null_value' ELSE 'non_finite_value' END",
    ),
    "prices": (
        'event_date IS NULL OR "close" IS NULL OR isnan("close") OR isinf("close") '
        'OR "close" <= 0 OR "volume" < 0 '
        'OR ("high" IS NOT NULL AND "low" IS NOT NULL AND "high" < "low")',
        'CASE WHEN event_date IS NULL THEN \'null_event_date\' '
        'WHEN "close" IS NULL THEN \'null_close\' '
        'WHEN isnan("close") OR isinf("close") THEN \'non_finite_close\' '
        'WHEN "close" <= 0 THEN \'nonpositive_close\' '
        'WHEN "volume" < 0 THEN \'negative_volume\' ELSE \'corrupt_ohlc\' END',
    ),
}


def gate(con=None, *, verbose: bool = True) -> dict:
    """Quarantine garbage rows out of the PIT-critical tables. Returns a per-table report.

    For each table it (re)creates `<table>_rejected` with the offending rows + a
    `reject_reason`, then deletes them from the live table. Idempotent: safe to run on
    every build (the warehouse is rebuilt from the landing zone each time anyway).
    """
    owns = con is None
    con = con or connect()
    try:
        tables = {r[0] for r in con.execute("SHOW TABLES").fetchall()}
        report: dict[str, dict] = {}
        for table, (where, reason) in _SPECS.items():
            if table not in tables:
                continue
            con.execute(
                f"CREATE OR REPLACE TABLE {table}_rejected AS "
                f"SELECT *, {reason} AS reject_reason, now() AS rejected_at "
                f"FROM {table} WHERE {where}"
            )
            n = con.execute(f"SELECT count(*) FROM {table}_rejected").fetchone()[0]
            by: dict[str, int] = {}
            if n:
                con.execute(f"DELETE FROM {table} WHERE {where}")
                by = dict(con.execute(
                    f"SELECT reject_reason, count(*) FROM {table}_rejected GROUP BY 1"
                ).fetchall())
                if verbose:
                    reasons = ", ".join(f"{k}={v}" for k, v
                                        in sorted(by.items(), key=lambda kv: -kv[1]))
                    print(f"[gate]    {table}: quarantined {n:,} row(s) "
                          f"-> {table}_rejected ({reasons})")
            report[table] = {"quarantined": n, "reasons": by}
        return report
    finally:
        if owns:
            con.close()
