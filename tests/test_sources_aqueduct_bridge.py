"""Tests for the aqueduct bridge (clinical trials pipeline)."""

from __future__ import annotations

from numeraire.sources import aqueduct_bridge


class _FakeConnection:
    """Minimal duckdb.connect() stand-in: canned rows per query shape."""

    def __init__(self, sponsors, trials):
        self._sponsors = sponsors
        self._trials = trials
        self.closed = False

    def execute(self, sql, params=None):
        if "DISTINCT lead_sponsor" in sql:
            return _FakeResult([(s,) for s in self._sponsors])
        return _FakeResult(self._trials)

    def close(self):
        self.closed = True


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


def test_ingest_no_cik(monkeypatch):
    """Unknown ticker (no CIK) returns empty result before touching the warehouse."""
    monkeypatch.setattr(aqueduct_bridge.edgar, "_tickers", lambda: {})
    result = aqueduct_bridge.ingest("FAKE")
    assert result == ("", 0, 0)


def test_ingest_warehouse_missing(monkeypatch, tmp_path):
    """Missing warehouse file returns empty result instead of raising."""
    monkeypatch.setattr(
        aqueduct_bridge.edgar,
        "_tickers",
        lambda: {"0": {"ticker": "ABBV", "cik_str": 1800, "title": "AbbVie Inc."}},
    )
    monkeypatch.setattr(aqueduct_bridge, "AQ_WAREHOUSE", str(tmp_path / "missing.duckdb"))
    result = aqueduct_bridge.ingest("ABBV")
    assert result == ("", 0, 0)


def test_ingest_no_resolved_sponsor(monkeypatch, tmp_path):
    """A CIK with no sponsor in clinical_trials resolving to it returns empty, not an error."""
    monkeypatch.setattr(
        aqueduct_bridge.edgar,
        "_tickers",
        lambda: {"0": {"ticker": "ABBV", "cik_str": 1800, "title": "AbbVie Inc."}},
    )
    warehouse = tmp_path / "warehouse.duckdb"
    warehouse.touch()
    monkeypatch.setattr(aqueduct_bridge, "AQ_WAREHOUSE", str(warehouse))
    monkeypatch.setattr(
        aqueduct_bridge.duckdb, "connect", lambda *a, **k: _FakeConnection(["Yale University"], [])
    )
    result = aqueduct_bridge.ingest("ABBV")
    assert result == ("", 0, 0)


def test_ingest_matches_resolved_sponsor(monkeypatch, tmp_path):
    """A sponsor name that resolves to the ticker's CIK is included in the query and output."""
    monkeypatch.setattr(
        aqueduct_bridge.edgar,
        "_tickers",
        lambda: {"0": {"ticker": "ABBV", "cik_str": 1800, "title": "AbbVie Inc."}},
    )
    warehouse = tmp_path / "warehouse.duckdb"
    warehouse.touch()
    monkeypatch.setattr(aqueduct_bridge, "AQ_WAREHOUSE", str(warehouse))
    trial_row = ("NCT001", "A trial", "RECRUITING", "PHASE3", "cond", "interv", "2026-01-01", None, "AbbVie Inc.")
    monkeypatch.setattr(
        aqueduct_bridge.duckdb,
        "connect",
        lambda *a, **k: _FakeConnection(["AbbVie Inc.", "Yale University"], [trial_row]),
    )
    monkeypatch.setattr(aqueduct_bridge, "merge_jsonl", lambda path, recs, key: (len(recs), len(recs)))
    result = aqueduct_bridge.ingest("ABBV")
    path, total, added = result
    assert total == added == 1
    assert path.endswith("ABBV.jsonl")


def test_matching_sponsors_excludes_unresolved(monkeypatch):
    """_matching_sponsors only returns sponsor names that resolve to the given (cik, ticker)."""
    monkeypatch.setattr(
        aqueduct_bridge.edgar,
        "_tickers",
        lambda: {"0": {"ticker": "ABBV", "cik_str": 1800, "title": "AbbVie Inc."}},
    )
    con = _FakeConnection(["AbbVie Inc.", "Yale University", "Vertex Pharmaceuticals"], [])
    matched = aqueduct_bridge._matching_sponsors(con, 1800, "ABBV")
    assert matched == ["AbbVie Inc."]
