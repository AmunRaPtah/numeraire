"""Landing-zone helpers: incremental, idempotent JSONL accumulation (from aqueduct).

For bitemporal data the merge KEY includes the knowledge-time fields (filed/accession),
so re-fetching produces identical rows (de-duped) while genuinely new filings — including
restatements of an already-seen period — add NEW rows. Nothing is ever overwritten, so
the full as-of history accumulates.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path


def _key(rec: dict, key):
    if callable(key):
        return key(rec)
    if isinstance(key, (tuple, list)):
        return tuple(rec.get(k) for k in key)
    return rec.get(key)


def merge_jsonl(path: Path, records: Iterable[dict],
                key: str | Sequence[str] | Callable[[dict], object]) -> tuple[int, int]:
    """Merge records into JSONL at `path`, de-duplicating by `key`. Returns (total, added)."""
    merged: dict[object, dict] = {}
    if path.exists():
        for line in path.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                merged[_key(r, key)] = r
    before = len(merged)
    for r in records:
        merged[_key(r, key)] = r
    with path.open("w") as f:
        for r in merged.values():
            f.write(json.dumps(r) + "\n")
    return len(merged), len(merged) - before
