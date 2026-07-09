"""Tests for landing-zone JSONL merge/dedup."""

from __future__ import annotations

from numeraire.landing import merge_jsonl


def test_merge_into_empty(tmp_path):
    p = tmp_path / "test.jsonl"
    recs = [{"id": 1, "v": "a"}, {"id": 2, "v": "b"}]
    total, added = merge_jsonl(p, recs, key="id")
    assert total == 2 and added == 2
    lines = p.read_text().strip().splitlines()
    assert len(lines) == 2


def test_merge_dedup(tmp_path):
    p = tmp_path / "test.jsonl"
    p.write_text('{"id": 1, "v": "a"}\n')
    recs = [{"id": 1, "v": "updated"}, {"id": 2, "v": "new"}]
    total, added = merge_jsonl(p, recs, key="id")
    assert total == 2 and added == 1
    lines = p.read_text().strip().splitlines()
    assert len(lines) == 2
    # id=1 should be updated to latest
    import json
    assert json.loads(lines[0])["v"] == "updated"


def test_merge_noop(tmp_path):
    p = tmp_path / "test.jsonl"
    recs = [{"id": 1, "v": "a"}]
    total1, _ = merge_jsonl(p, recs, key="id")
    total2, added2 = merge_jsonl(p, recs, key="id")
    assert total2 == total1 and added2 == 0


def test_merge_file_missing(tmp_path):
    """First call on a non-existent file creates it."""
    p = tmp_path / "new.jsonl"
    assert not p.exists()
    total, added = merge_jsonl(p, [{"k": "x"}], key="k")
    assert total == 1 and added == 1
    assert p.exists()


def test_merge_callable_key(tmp_path):
    p = tmp_path / "callable.jsonl"
    recs = [{"a": 1, "b": 2}]
    total, added = merge_jsonl(p, recs, key=lambda r: r["a"])
    assert total == 1 and added == 1


def test_merge_tuple_key(tmp_path):
    p = tmp_path / "tuple.jsonl"
    recs = [{"a": 1, "b": 2}]
    total, added = merge_jsonl(p, recs, key=("a", "b"))
    assert total == 1 and added == 1


def test_merge_empty_records(tmp_path):
    p = tmp_path / "empty.jsonl"
    total, added = merge_jsonl(p, [], key="id")
    assert total == 0 and added == 0
    assert not p.exists() or p.read_text().strip() == ""
