"""Tests for the PIT validation gate."""

from __future__ import annotations

import seed

from numeraire import validate


def test_validate_empty_no_error(con, env):
    """Empty warehouse should pass validation (no data = no issues)."""
    result = validate.validate(con)
    assert result["ok"] is True


def test_gate_quarantines_garbage_leaving_clean_warehouse(con, env):
    """The ingest gate (run inside build) removes the seeded garbage from the live
    tables and quarantines it, so validate sees a clean, backtest-safe warehouse."""
    seed.build_full(con)  # build_full -> warehouse.build -> quality.gate
    result = validate.validate(con)
    assert result["checks"]["observations"] > 0
    # The intentionally-seeded poison is gone from fundamentals...
    assert result["checks"]["null_knowledge_date"] == 0
    assert result["checks"]["lookahead_filed_before_event"] == 0
    assert result["ok"] is True
    # ...and preserved in quarantine: 1 null-kd + 1 lookahead row per ticker (5 each).
    by = dict(con.execute(
        "SELECT reject_reason, count(*) FROM fundamentals_rejected GROUP BY 1"
    ).fetchall())
    assert by.get("null_knowledge_date") == 5
    assert by.get("lookahead") == 5
    assert result["quarantined"] >= 10


def test_validate_report_structure(con, env):
    """validate() returns expected keys."""
    seed.build_full(con)
    result = validate.validate(con)
    assert "ok" in result
    assert "checks" in result
    for check in (
        "observations",
        "companies",
        "null_knowledge_date",
        "null_event_date",
        "lookahead_filed_before_event",
        "restated_period_facts",
    ):
        assert check in result["checks"]


def test_validate_restatement_detection(con, env):
    """A genuine restatement — one period filed twice with different values at
    different (valid, non-lookahead) knowledge dates — is detected, and both filings
    survive the ingest gate."""
    period = {"cik": 999, "entity": "R CO", "taxonomy": "us-gaap",
              "tag": "NetIncomeLoss", "unit": "USD",
              "start": "2024-01-01", "end": "2024-03-31", "fy": "2024", "fp": "Q1",
              "form": "10-Q", "frame": "CY1"}
    seed._write_jsonl("edgar", "RSTT_CIK999.jsonl", [
        {**period, "val": 5_000_000, "filed": "2024-05-01", "accn": "orig"},
        {**period, "val": 5_200_000, "filed": "2024-11-01", "accn": "restated"},
    ])
    from numeraire import warehouse as wh

    wh.build(con)
    result = validate.validate(con)
    assert result["checks"]["restated_period_facts"] > 0
    # both filings are valid PIT rows (knowledge_date > event_date) -> not quarantined
    assert con.execute("SELECT count(*) FROM fundamentals WHERE cik=999").fetchone()[0] == 2
