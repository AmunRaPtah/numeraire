"""Federal Reserve Economic Data (FRED) connector — macro regime layer.

Five core series for regime classification, plus additional series needed by
Hermes (unemployment, CPI). Supports both API-key and keyless CSV endpoints
(public CSV at fred.stlouisfed.org requires no registration).

Core series (regime classification):
  DFF          — Federal Funds Rate (%)
  T10Y2Y       — 10Y-2Y yield-curve spread (%) — negative = inverted
  BAMLH0A0HYM2 — US HY credit spread OAS (%) — elevated = credit stress
  VIXCLS       — CBOE VIX — elevated = fear regime
  USREC        — NBER recession indicator (0/1); knowledge_date +180d (PIT lag)

Additional series (Hermes briefing):
  UNRATE       — Civilian Unemployment Rate (%)
  CPIAUCSL     — Consumer Price Index (CPI, level)

Setup:
  export FRED_API_KEY=<key>   # optional; free at fred.stlouisfed.org
  python -m numeraire fred    # land all series (keyless CSV if no key)
  python -m numeraire fred T10Y2Y VIXCLS   # land specific series

regime(con, asof) returns the macro label for any date:
  'expansion' | 'late_cycle' | 'risk_off' | 'recession' | 'recovery' | 'unknown'

regime_series(con, months) returns {month: label} for all months in a list —
used by the backtest for regime-conditional performance breakdown.
"""

from __future__ import annotations

import csv
import os
from bisect import bisect_right
from datetime import date as _date
from datetime import datetime, timezone
from datetime import timedelta
from io import StringIO

from .. import config, net
from ..landing import merge_jsonl

_KEYED_BASE = "https://api.stlouisfed.org/fred/series/observations"
_KEYLESS_BASE = "https://fred.stlouisfed.org/graph/fredgraph.csv"

# (description, knowledge_lag_days)
# USREC: NBER declares recessions ~6 months after they start — 180d lag
# for PIT so backtests don't use information they wouldn't have had.
SERIES: dict[str, tuple[str, int]] = {
    # Core regime series
    "DFF":           ("Federal Funds Rate (%)",      0),
    "T10Y2Y":        ("10Y-2Y Yield Spread (%)",     0),
    "BAMLH0A0HYM2":  ("US HY Credit Spread OAS (%)", 1),
    "VIXCLS":        ("CBOE VIX",                    0),
    "USREC":         ("NBER Recession (0/1)",         180),
    # Hermes briefing series
    "UNRATE":        ("Civilian Unemployment Rate (%)", 1),
    "CPIAUCSL":      ("Consumer Price Index (CPI)",      2),
}

_KEY = ("series_id", "event_date")


def _api_key() -> str | None:
    return os.environ.get("FRED_API_KEY")


def _fetch_keyed(series_id: str, api_key: str) -> list[dict]:
    """Fetch via the FRED API (requires a free API key)."""
    fetched = datetime.now(timezone.utc).isoformat()
    lag = SERIES.get(series_id, ("", 0))[1]
    url = (f"{_KEYED_BASE}?series_id={series_id}&api_key={api_key}"
           "&file_type=json&sort_order=asc&observation_start=1950-01-01")
    try:
        data = net.get_json(url, timeout=30)
    except net.NetworkError as e:
        print(f"[fred] {series_id}: fetch failed: {e}")
        return []
    rows = []
    for obs in data.get("observations", []):
        v = obs.get("value", "")
        if v in (".", "", None):
            continue
        try:
            val = float(v)
        except ValueError:
            continue
        ed = obs["date"]
        kd = (_date.fromisoformat(ed) + timedelta(days=lag)).isoformat() if lag else ed
        rows.append({"series_id": series_id, "event_date": ed,
                     "knowledge_date": kd, "val": val, "fetched_at": fetched})
    return rows


def _fetch_keyless(series_id: str) -> list[dict]:
    """Fetch via the public CSV endpoint (no API key needed).

    Uses the same endpoint as Hermes' fred runner at
    api/services/hermes/runners/fred.py.
    """
    fetched = datetime.now(timezone.utc).isoformat()
    lag = SERIES.get(series_id, ("", 0))[1]
    url = f"{_KEYLESS_BASE}?id={series_id}"
    try:
        resp = net.get_bytes(url, timeout=30).decode()
    except net.NetworkError as e:
        print(f"[fred] {series_id}: CSV fetch failed: {e}")
        return []
    rows = []
    reader = csv.reader(StringIO(resp))
    for i, row in enumerate(reader):
        if i == 0:
            continue  # header
        if len(row) >= 2 and row[1] not in ("", "."):
            try:
                val = float(row[1])
            except ValueError:
                continue
            ed = row[0]
            kd = (_date.fromisoformat(ed) + timedelta(days=lag)).isoformat() if lag else ed
            rows.append({"series_id": series_id, "event_date": ed,
                         "knowledge_date": kd, "val": val, "fetched_at": fetched})
    return rows


def _fetch(series_id: str) -> list[dict]:
    """Fetch FRED data, preferring API key but falling back to keyless CSV."""
    key = _api_key()
    if key:
        return _fetch_keyed(series_id, key)
    return _fetch_keyless(series_id)


def ingest(series_ids: list[str] | None = None) -> dict[str, tuple[int, int]]:
    """Fetch and land FRED series. Returns {series_id: (total, added)}."""
    d = config.raw_source_dir("fred")
    targets = [s.upper() for s in series_ids] if series_ids else list(SERIES)
    out: dict[str, tuple[int, int]] = {}
    for sid in targets:
        rows = _fetch(sid)
        if not rows:
            out[sid] = (0, 0)
            continue
        tot, add = merge_jsonl(d / f"{sid}.jsonl", rows, _KEY)
        desc = SERIES.get(sid, (sid, 0))[0]
        print(f"[fred] {sid} ({desc}): {len(rows)} obs, +{add} new ({tot} total)")
        out[sid] = (tot, add)
    return out


# ── PIT lookups ───────────────────────────────────────────────────────────────

def _pit_val(con, series_id: str, asof: str) -> float | None:
    """Latest known value of series_id as of asof (PIT: knowledge_date <= asof)."""
    try:
        row = con.execute("""
            SELECT val FROM macro
            WHERE series_id = ?
              AND knowledge_date IS NOT NULL
              AND knowledge_date <= CAST(? AS DATE)
            ORDER BY knowledge_date DESC, event_date DESC
            LIMIT 1
        """, [series_id, asof]).fetchone()
        return float(row[0]) if row else None
    except Exception:
        return None


def _pit_series_bulk(con, series_id: str, months: list) -> dict:
    """Vectorised PIT: returns {month: val} for all months using bisect (5 SQL queries
    total for 5 series, regardless of how many backtest months there are).
    """
    try:
        rows = con.execute("""
            SELECT knowledge_date, val
            FROM macro
            WHERE series_id = ? AND knowledge_date IS NOT NULL
            ORDER BY knowledge_date, event_date DESC
        """, [series_id]).fetchall()
    except Exception:
        return {m: None for m in months}
    if not rows:
        return {m: None for m in months}
    kds = [r[0] for r in rows]   # datetime.date objects from DuckDB
    vals = [float(r[1]) for r in rows]
    out = {}
    for m in months:
        m_date = _date.fromisoformat(m) if isinstance(m, str) else m
        idx = bisect_right(kds, m_date) - 1
        out[m] = vals[idx] if idx >= 0 else None
    return out


def latest_value(con, series_id: str) -> float | None:
    """Return the most recent value for a series (no PIT filter — live query)."""
    try:
        row = con.execute("""
            SELECT val FROM macro
            WHERE series_id = ?
            ORDER BY event_date DESC
            LIMIT 1
        """, [series_id]).fetchone()
        return float(row[0]) if row else None
    except Exception:
        return None


def latest_with_date(con, series_id: str) -> tuple[str, float]:
    """Return (event_date, value) for the most recent observation."""
    try:
        row = con.execute("""
            SELECT event_date, val FROM macro
            WHERE series_id = ?
            ORDER BY event_date DESC
            LIMIT 1
        """, [series_id]).fetchone()
        if row:
            return (str(row[0]), float(row[1]))
    except Exception:
        pass
    raise ValueError(f"No data for FRED series {series_id} in macro table")


def macro_snapshot(con, series_ids: list[str] | None = None) -> dict:
    """Return {series_id: {'value': val, 'date': event_date}} for latest values.

    Used by Hermes agent_loop to inject macro context into LLM prompts.
    """
    targets = series_ids or [
        "DFF", "T10Y2Y", "BAMLH0A0HYM2", "VIXCLS", "UNRATE", "CPIAUCSL", "USREC",
    ]
    out = {}
    for sid in targets:
        try:
            d, v = latest_with_date(con, sid)
            out[sid] = {"value": v, "date": d}
        except (ValueError, Exception):
            out[sid] = {"value": None, "date": None}
    return out


# ── Regime classification ─────────────────────────────────────────────────────

_LABELS = {
    "recession":  "📉 RECESSION",
    "risk_off":   "⚠️  RISK-OFF",
    "late_cycle": "🕐 LATE-CYCLE",
    "expansion":  "🟢 EXPANSION",
    "recovery":   "🔄 RECOVERY",
    "unknown":    "❓ UNKNOWN (no macro data — run `numeraire fred`)",
}


def _classify(fed, curve, hys, vix, rec) -> str:
    if rec is not None and rec >= 0.5:
        return "recession"
    if (vix is not None and vix > 25) or (hys is not None and hys > 6.0):
        return "risk_off"
    if curve is not None and curve < 0.0:
        return "late_cycle"
    if (curve is not None and curve > 0.0
            and hys is not None and hys < 4.0
            and vix is not None and vix < 20.0):
        return "expansion"
    if any(v is None for v in (fed, curve, hys, vix, rec)):
        return "unknown"
    return "recovery"


def regime(con, asof: str | None = None) -> dict:
    """Macro regime as of asof (defaults to today).

    Regime thresholds:
      recession  — USREC = 1 (NBER-declared, 180d knowledge lag in PIT)
      risk_off   — VIX > 25 OR HY spread > 6 %
      late_cycle — T10Y2Y < 0 (curve inverted) AND not in recession
      expansion  — curve > 0 AND HY < 4 % AND VIX < 20
      recovery   — everything else (post-recession healing or ambiguous)
      unknown    — macro table empty or no data for asof
    """
    asof = asof or _date.today().isoformat()
    fed   = _pit_val(con, "DFF",           asof)
    curve = _pit_val(con, "T10Y2Y",        asof)
    hys   = _pit_val(con, "BAMLH0A0HYM2", asof)
    vix   = _pit_val(con, "VIXCLS",        asof)
    rec   = _pit_val(con, "USREC",         asof)
    label = _classify(fed, curve, hys, vix, rec)
    return {"asof": asof, "fed_rate": fed, "curve": curve, "hy_spread": hys,
            "vix": vix, "recession": rec, "label": label, "display": _LABELS[label]}


def regime_series(con, months: list) -> dict:
    """Vectorised regime labels for a list of months (used by backtest).

    Returns {month: label_str} — 5 SQL queries total regardless of len(months).
    """
    fed_s   = _pit_series_bulk(con, "DFF",           months)
    curve_s = _pit_series_bulk(con, "T10Y2Y",        months)
    hys_s   = _pit_series_bulk(con, "BAMLH0A0HYM2", months)
    vix_s   = _pit_series_bulk(con, "VIXCLS",        months)
    rec_s   = _pit_series_bulk(con, "USREC",         months)
    return {
        m: _classify(fed_s.get(m), curve_s.get(m), hys_s.get(m),
                     vix_s.get(m), rec_s.get(m))
        for m in months
    }
