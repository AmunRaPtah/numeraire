"""Tests for the PIT validation gate."""

from __future__ import annotations

import seed

from numeraire import validate


def test_validate_empty_no_error(con, env):
    """Empty warehouse should pass validation (no data = no issues)."""
    result = validate.validate(con)
    assert result["ok"] is True


def test_validate_clean_data(con, env):
    """Clean bitemporal data with no lookahead/nulls should pass."""
    seed.build_full(con)
    result = validate.validate(con)
    # Should have data
    assert result["checks"]["observations"] > 0
    # Each ticker's seed creates 1 null-knowledge-date Revenues row (5 tickers)
    assert result["checks"]["null_knowledge_date"] == 5
    # Each ticker's seed creates 1 lookahead row (5 tickers)
    assert result["checks"]["lookahead_filed_before_event"] == 5
    # We intentionally have issues
    assert result["ok"] is False


def test_validate_report_structure(con, env):
    """validate() returns expected keys."""
    seed.build_full(con)
    result = validate.validate(con)
    assert "ok" in result
    assert "checks" in result
    for check in ("observations", "companies", "null_knowledge_date",
                   "null_event_date", "lookahead_filed_before_event",
                   "restated_period_facts"):
        assert check in result["checks"]


def test_validate_restatement_detection(con, env):
    """Restated periods count > 0 when seeded."""
    seed.seed_edgar("AAPL", 320193)
    from numeraire import warehouse as wh
    wh.build(con)
    result = validate.validate(con)
    assert result["checks"]["restated_period_facts"] > 0
