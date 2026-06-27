"""Security master — the canonical identity map (ADR-4).

One table that answers "what is this company": CIK <-> ticker <-> registered name, for
every SEC filer (~10k). It's the join key the rest of the system leans on:
  - fundamentals (EDGAR) are keyed by CIK
  - prices are keyed by ticker
  - clinical-trial pipeline is keyed by *sponsor name*
so a sponsor-name -> CIK/ticker resolver is what lets the aqueduct pharma edge actually
attach trials to tradable securities (it's why the bridge previously matched ~1 row).

Source: SEC's company_tickers.json (keyless, the same file edgar.cik_for already uses).
We persist it as a table and add a name resolver: normalized-exact first, then a
contained-name fallback ("Moderna" <- "ModernaTX, Inc."). Conservative on purpose — a
wrong identity link is worse than a missing one.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from .. import config
from ..landing import merge_jsonl
from . import edgar

KEY = ("cik", "ticker")

# corporate-form noise to strip before matching names. NOT industry words
# (therapeutics/pharma) — those disambiguate ("Arena Pharmaceuticals" != "Arena").
_SUFFIX = {"inc", "incorporated", "corp", "corporation", "co", "company", "ltd",
           "limited", "plc", "llc", "lp", "lllp", "sa", "ag", "nv", "se", "ab",
           "holdings", "holding", "group", "the", "and", "of", "&"}


def normalize(name: str) -> str:
    """Lowercase, drop punctuation + corporate-form words, collapse whitespace."""
    if not name:
        return ""
    toks = re.sub(r"[^a-z0-9 ]", " ", name.lower()).split()
    toks = [t for t in toks if t not in _SUFFIX]
    return " ".join(toks)


def ingest() -> tuple[int, int]:
    """Land the SEC CIK/ticker/name map as the security_master stream."""
    fetched = datetime.now(timezone.utc).isoformat()
    rows = []
    for r in edgar._tickers().values():
        tk = (r.get("ticker") or "").upper()
        cik = r.get("cik_str")
        name = r.get("title") or ""
        if not tk or cik is None:
            continue
        rows.append({"cik": int(cik), "ticker": tk, "name": name,
                     "name_norm": normalize(name), "fetched_at": fetched})
    d = config.raw_source_dir("security_master")
    tot, add = merge_jsonl(d / "sec.jsonl", rows, KEY)
    print(f"[secmaster] {len(rows)} securities; landed {tot} (+{add})")
    return (tot, add)


# ---- name resolver ----------------------------------------------------------

def _index() -> dict:
    """{name_norm: (cik, ticker)} from the SEC ticker map. Built once, in memory."""
    idx: dict[str, tuple[int, str]] = {}
    for r in edgar._tickers().values():
        tk = (r.get("ticker") or "").upper()
        cik = r.get("cik_str")
        nn = normalize(r.get("title") or "")
        if tk and cik is not None and nn and nn not in idx:
            idx[nn] = (int(cik), tk)
    return idx


def resolve(sponsor: str, idx: dict | None = None):
    """Best-effort sponsor-name -> (cik, ticker). None if no confident match.

    1. exact normalized match
    2. the sponsor's normalized name *starts with* a company name, or vice versa
       (handles "ModernaTX" / "Moderna", "Pfizer Research" / "Pfizer") — but only when
       the shorter side is >=4 chars, to avoid matching on a stray short token.
    """
    idx = idx if idx is not None else _index()
    s = normalize(sponsor)
    if not s:
        return None
    if s in idx:
        return idx[s]
    best = None
    for nn, hit in idx.items():
        short, long = (s, nn) if len(s) <= len(nn) else (nn, s)
        if len(short) >= 4 and long.startswith(short + " ") or long == short:
            # prefer the longest matched company name (most specific)
            if best is None or len(nn) > best[0]:
                best = (len(nn), hit)
    return best[1] if best else None
