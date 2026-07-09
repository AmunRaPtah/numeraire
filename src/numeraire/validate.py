"""Point-in-time validation gate (adapted from aqueduct's validate concept).

Fails loudly on the things that silently ruin a backtest: missing knowledge_time
(can't place a fact in time), lookahead (filed before the period it reports — rare but
poisonous), and surfaces restatement coverage so the bitemporal model is doing its job.
"""

from __future__ import annotations

from .storage import connect


def validate(con=None, *, verbose=True) -> dict:
    owns = con is None
    con = con or connect()
    try:
        tables = {r[0] for r in con.execute("SHOW TABLES").fetchall()}
        if "fundamentals" not in tables:
            if verbose:
                print("[validate] no warehouse yet")
            return {"ok": True, "checks": {}}

        def q(s):
            return con.execute(s).fetchone()[0]

        checks = {
            "observations": q("SELECT count(*) FROM fundamentals"),
            "companies": q("SELECT count(DISTINCT cik) FROM fundamentals"),
            "null_knowledge_date": q("SELECT count(*) FROM fundamentals WHERE knowledge_date IS NULL"),
            "null_event_date": q("SELECT count(*) FROM fundamentals WHERE event_date IS NULL"),
            # lookahead: a fact 'known' before the period it describes even ended
            "lookahead_filed_before_event": q(
                "SELECT count(*) FROM fundamentals WHERE knowledge_date < event_date"
            ),
            # restated periods: same (cik,tag,unit,event_date) seen at >1 knowledge_date
            "restated_period_facts": q("""
                SELECT count(*) FROM (
                  SELECT cik,tag,unit,event_date FROM fundamentals
                  GROUP BY 1,2,3,4 HAVING count(DISTINCT knowledge_date) > 1)"""),
        }
        bad = (
            checks["null_knowledge_date"] + checks["null_event_date"] + checks["lookahead_filed_before_event"]
        )
        ok = bad == 0
        # Quarantine is healthy: garbage the ingest gate kept out of the live tables.
        # Report it (not counted as an issue) so growth-vs-rejection stays visible.
        quarantined = 0
        quarantine_reasons: dict[str, int] = {}
        for t in ("fundamentals_rejected", "fred_rejected", "prices_rejected"):
            if t not in tables:
                continue
            for reason, n in con.execute(
                f"SELECT reject_reason, count(*) FROM {t} GROUP BY 1"
            ).fetchall():
                quarantined += n
                quarantine_reasons[reason] = quarantine_reasons.get(reason, 0) + n
        if verbose:
            for k, v in checks.items():
                print(f"  {k}: {v:,}")
            print(f"  -> {'OK' if ok else 'ISSUES'} ({bad} problematic rows)")
            if quarantined:
                top = ", ".join(f"{k}={v}" for k, v in
                                sorted(quarantine_reasons.items(), key=lambda kv: -kv[1]))
                print(f"  quarantined by ingest gate: {quarantined:,} ({top})")
        return {"ok": ok, "checks": checks,
                "quarantined": quarantined, "quarantine_reasons": quarantine_reasons}
    finally:
        if owns:
            con.close()
