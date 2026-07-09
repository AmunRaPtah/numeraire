"""Survivorship-free S&P 500 membership — reconstructed point-in-time (ADR-2).

The whole project's discipline collapses if the universe is just "today's index": a
backtest that only ever considers current members has already conditioned on survival
(the failures were dropped). To be honest we need to know, for any past date, *which
tickers were in the index then* — including the ones since removed/delisted.

Keyless source: Wikipedia's "List of S&P 500 companies" carries two tables:
  1. current constituents (ticker, name, CIK, date first added)
  2. a dated log of changes (added / removed tickers, with the date)

From these we reconstruct membership intervals [added_date, removed_date):
  - current members: added_date from table 1, removed_date = NULL (still in)
  - removed names:   removed_date from the changes log; added_date if it also appears
                     as an addition there, else NULL (member before our log coverage)

This is survivorship-FREE for index *membership* (delisted names are retained). It is
NOT a full survivorship-free price history — Yahoo drops most delisted tickers, so
delisted-name prices remain a gap that only paid data (CRSP) fully closes. Documented,
not hidden: membership PIT removes the inclusion/look-ahead bias even where prices end.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

from .. import config, net
from ..landing import merge_jsonl

WIKI = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
KEY = ("index_name", "ticker", "added_date", "removed_date")


class _TableParser(HTMLParser):
    """Extract <table> rows as lists of cell text. Keeps each table separately."""

    def __init__(self):
        super().__init__()
        self.tables: list[list[list[str]]] = []
        self._depth = 0  # table nesting depth
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._rows: list[list[str]] | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._depth += 1
            if self._depth == 1:
                self._rows = []
        elif self._depth == 1 and tag == "tr":
            self._row = []
        elif self._depth == 1 and tag in ("td", "th"):
            self._cell = []

    def handle_endtag(self, tag):
        if tag == "table":
            if self._depth == 1 and self._rows is not None:
                self.tables.append(self._rows)
                self._rows = None
            self._depth = max(0, self._depth - 1)
        elif self._depth == 1 and tag == "tr" and self._row is not None:
            self._rows.append(self._row)
            self._row = None
        elif self._depth == 1 and tag in ("td", "th") and self._cell is not None:
            self._row.append(re.sub(r"\s+", " ", "".join(self._cell)).strip())
            self._cell = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def _parse_date(s: str) -> str | None:
    s = (s or "").strip()
    for fmt in ("%Y-%m-%d", "%B %d, %Y", "%b %d, %Y", "%d %B %Y"):
        try:
            from datetime import datetime

            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", s)
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None


def _norm_ticker(s: str) -> str:
    # Wikipedia uses BRK.B; Yahoo uses BRK-B. Normalise to Yahoo form.
    return (
        re.sub(r"[^A-Z0-9.\-]", "", (s or "").upper().split()[0] if s else "").replace(".", "-") if s else ""
    )


def _find_tables(html: str):
    p = _TableParser()
    p.feed(html)
    return p.tables


def _build_membership(tables) -> list[dict]:
    """Reconstruct [added, removed) intervals from the constituents + changes tables."""
    members: dict[str, dict] = {}  # ticker -> {added, removed}

    def hdr(t):
        return [c.lower() for c in t[0]] if t else []

    # --- current constituents: header has "symbol" + "date added" ---
    cur = next(
        (
            t
            for t in tables
            if t and any("symbol" in c for c in hdr(t)) and any("date" in c and "added" in c for c in hdr(t))
        ),
        None,
    )
    if cur:
        h = hdr(cur)
        i_sym = next(i for i, c in enumerate(h) if "symbol" in c)
        i_add = next((i for i, c in enumerate(h) if "date" in c and "added" in c), None)
        for row in cur[1:]:
            if len(row) <= i_sym:
                continue
            tk = _norm_ticker(row[i_sym])
            if not tk:
                continue
            added = _parse_date(row[i_add]) if i_add is not None and len(row) > i_add else None
            members[tk] = {"added": added, "removed": None}

    # --- changes log: header has "date" + "added"/"removed" sections ---
    chg = next(
        (t for t in tables if t and any("date" in c for c in hdr(t)) and any("removed" in c for c in hdr(t))),
        None,
    )
    if chg:
        # Wikipedia's layout uses colspan/rowspan headers, so the sub-header row
        # (Ticker|Security|Ticker|Security) does NOT index-align with the 6-cell data
        # rows. The data layout is fixed and stable:
        #   0=date  1=added ticker  2=added security  3=removed ticker  4=removed security  5=reason
        # We map by position and *validate shape* (a ticker is short & uppercase) so a
        # layout drift degrades to "skipped row", never "security name as ticker".
        i_date, i_added, i_removed = 0, 1, 3
        ticker_re = re.compile(r"^[A-Z][A-Z0-9]*([.\-][A-Z0-9]+)?$")

        def _tk(row, i):
            if len(row) <= i:
                return ""
            tk = _norm_ticker(row[i])
            return tk if (1 <= len(tk) <= 6 and ticker_re.match(tk)) else ""

        # changes are listed newest-first; iterate oldest-first so the EARLIEST event wins.
        for row in reversed(chg):
            d = _parse_date(row[i_date]) if len(row) > i_date else None
            if not d:
                continue
            rem = _tk(row, i_removed)
            if rem and rem not in members:
                # A removed name that is NOT a current constituent: it left the index on d
                # and never came back (else it'd be in the current table). Iterating
                # oldest-first, the first removal we record is the one that matters.
                members[rem] = {"added": None, "removed": d}
            add = _tk(row, i_added)
            if add and add in members and members[add]["added"] is None:
                # an addition date for a current member we hadn't dated yet
                members[add]["added"] = d

    out = []
    for tk, m in sorted(members.items()):
        out.append(
            {"index_name": "SP500", "ticker": tk, "added_date": m["added"], "removed_date": m["removed"]}
        )
    return out


def ingest() -> tuple[int, int]:
    """Fetch + reconstruct S&P 500 membership, land it idempotently."""
    try:
        html = net.request(WIKI, timeout=40, headers=UA).decode("utf-8", "replace")
    except net.NetworkError as e:
        print(f"[sp500]   fetch failed: {e}")
        return (0, 0)
    rows = _build_membership(_find_tables(html))
    if not rows:
        print("[sp500]   no membership rows parsed (page layout changed?)")
        return (0, 0)
    cur = sum(1 for r in rows if r["removed_date"] is None)
    d = config.raw_source_dir("sp500_membership")
    tot, add = merge_jsonl(d / "SP500.jsonl", rows, KEY)
    print(f"[sp500]   {len(rows)} names ({cur} current, {len(rows) - cur} removed); landed {tot} (+{add})")
    return (tot, add)
