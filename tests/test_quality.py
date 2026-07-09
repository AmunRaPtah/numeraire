"""Ingest-time quality gate: backtest-poisoning rows are quarantined, not stored."""

from __future__ import annotations

import seed

from numeraire import quality, warehouse


def _build(con):
    warehouse.build(con)  # runs quality.gate internally


def test_prices_garbage_is_quarantined(con, env):
    seed.seed_prices("AAPL")
    # inject garbage price rows straight into the landing zone
    seed._write_jsonl("prices", "BAD.jsonl", [
        {"ticker": "BAD", "date": "2024-01-02", "open": 10, "high": 9, "low": 11,
         "close": 10, "adjclose": 10, "volume": 100, "fetched_at": "2024-01-03"},  # high<low
        {"ticker": "BAD", "date": "2024-01-03", "open": 0, "high": 0, "low": 0,
         "close": 0, "adjclose": 0, "volume": 100, "fetched_at": "2024-01-04"},    # close<=0
        {"ticker": "BAD", "date": "2024-01-04", "open": 5, "high": 6, "low": 4,
         "close": 5, "adjclose": 5, "volume": -10, "fetched_at": "2024-01-05"},    # neg volume
    ])
    _build(con)
    live = con.execute("SELECT count(*) FROM prices WHERE ticker='BAD'").fetchone()[0]
    rej = dict(con.execute(
        "SELECT reject_reason, count(*) FROM prices_rejected GROUP BY 1").fetchall())
    assert live == 0
    assert rej.get("corrupt_ohlc") == 1
    assert rej.get("nonpositive_close") == 1
    assert rej.get("negative_volume") == 1
    # clean AAPL prices are untouched
    assert con.execute("SELECT count(*) FROM prices WHERE ticker='AAPL'").fetchone()[0] > 0


def test_clean_prices_quarantine_nothing(con, env):
    seed.seed_prices("AAPL")
    _build(con)
    assert con.execute("SELECT count(*) FROM prices_rejected").fetchone()[0] == 0


def test_gate_report_shape(con, env):
    seed.build_full(con)
    report = quality.gate(con)  # idempotent second run
    assert set(report) >= {"fundamentals", "prices"}
    assert "quarantined" in report["fundamentals"]


def test_fundamentals_lookahead_and_nulls_quarantined(con, env):
    seed.seed_edgar("AAPL", 320193)
    _build(con)
    by = dict(con.execute(
        "SELECT reject_reason, count(*) FROM fundamentals_rejected GROUP BY 1").fetchall())
    assert by.get("null_knowledge_date") == 1
    assert by.get("lookahead") == 1
    # none of the quarantined rows remain live
    assert con.execute(
        "SELECT count(*) FROM fundamentals WHERE knowledge_date IS NULL "
        "OR knowledge_date < event_date").fetchone()[0] == 0
