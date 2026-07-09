"""Synthetic data factories for tests — write JSONL to the landing zone.

Each seed function creates controlled synthetic data (no lookahead, known point-in-time
relationships) so tests can verify pipeline stages deterministically.

Usage:
    from tests import seed
    seed.seed_sp500(con)
    seed.seed_edgar(con, "AAPL")
    ...
"""

from __future__ import annotations

import json
from datetime import date, timedelta

from numeraire import config, warehouse

# ── helpers ─────────────────────────────────────────────────────────────────

def _write_jsonl(source: str, filename: str, records: list[dict]) -> None:
    """Write records as JSONL to the landing zone for `source`."""
    d = config.raw_source_dir(source)
    (d / filename).write_text("\n".join(json.dumps(r) for r in records) + "\n")


# ── S&P 500 membership ─────────────────────────────────────────────────────

def seed_sp500() -> None:
    """Write survivorship-free S&P 500 membership with known added/removed dates.

    Current members: AAPL (added 1982), MSFT (added 1994), GOOGL (added 2006)
    Removed: TWTR (added 2018, removed 2023), ENRNQ (added 1995, removed 2001)
    """
    _write_jsonl("sp500_membership", "SP500.jsonl", [
        {"index_name": "SP500", "ticker": "AAPL",  "added_date": "1982-01-01", "removed_date": None},
        {"index_name": "SP500", "ticker": "MSFT",  "added_date": "1994-06-01", "removed_date": None},
        {"index_name": "SP500", "ticker": "GOOGL", "added_date": "2006-04-03", "removed_date": None},
        {"index_name": "SP500", "ticker": "ABBV",  "added_date": "2013-01-02", "removed_date": None},
        {"index_name": "SP500", "ticker": "JNJ",   "added_date": "1973-01-01", "removed_date": None},
        {"index_name": "SP500", "ticker": "TWTR",  "added_date": "2018-06-07", "removed_date": "2023-11-28"},
        {"index_name": "SP500", "ticker": "ENRNQ", "added_date": "1995-12-01", "removed_date": "2001-12-03"},
    ])


# ── Security master ────────────────────────────────────────────────────────

def seed_security_master() -> None:
    """Write CIK/ticker/name mapping."""
    _write_jsonl("security_master", "securities.jsonl", [
        {"cik": 320193, "ticker": "AAPL",  "name": "Apple Inc.",         "name_norm": "APPLE INC",    "fetched_at": "2025-01-01T00:00:00"},
        {"cik": 789019, "ticker": "MSFT",  "name": "Microsoft Corp.",    "name_norm": "MICROSOFT CORP", "fetched_at": "2025-01-01T00:00:00"},
        {"cik": 1652044, "ticker": "GOOGL", "name": "Alphabet Inc.",     "name_norm": "ALPHABET INC",   "fetched_at": "2025-01-01T00:00:00"},
        {"cik": 1800,    "ticker": "ABBV",  "name": "AbbVie Inc.",       "name_norm": "ABBVIE INC",     "fetched_at": "2025-01-01T00:00:00"},
        {"cik": 14272,   "ticker": "JNJ",   "name": "Johnson & Johnson", "name_norm": "JOHNSON JOHNSON", "fetched_at": "2025-01-01T00:00:00"},
    ])


# ── EDGAR fundamentals (bitemporal) ────────────────────────────────────────

def seed_edgar(ticker: str = "AAPL", cik: int = 320193) -> None:
    """Write bitemporal EDGAR fundamentals for one ticker.

    Creates two years of quarterly data with:
    - A restatement of 2024-Q2 NI (higher value filed later — backtest must see original)
    - One row with NULL knowledge_date (should trigger validation)
    """
    rows = []
    base = date(2023, 1, 1)
    for i in range(8):
        q = i + 1
        ev = date(2023 + i // 4, ((i % 4) * 3 + 3) % 12 + 1, 1)
        fy = str(2023 + i // 4)
        fp = f"Q{i % 4 + 1}"
        kd = ev + timedelta(days=40 + i * 2)

        # NetIncomeLoss (USD)
        ni = 10_000_000 + q * 500_000 + (200_000 if q >= 5 else 0)
        rows.append({
            "cik": cik, "entity": "APPLE INC", "taxonomy": "us-gaap",
            "tag": "NetIncomeLoss", "unit": "USD",
            "start": (ev - timedelta(days=85)).isoformat(),
            "end": ev.isoformat(),
            "val": ni, "filed": kd.isoformat(),
            "accn": f"0000320193-{fy}{fp}",
            "fy": fy, "fp": fp, "form": "10-Q" if q % 4 else "10-K",
            "frame": f"CY{q}",
        })
        # StockholdersEquity (USD)
        be = 50_000_000 + q * 1_000_000
        rows.append({
            "cik": cik, "entity": "APPLE INC", "taxonomy": "us-gaap",
            "tag": "StockholdersEquity", "unit": "USD",
            "start": (ev - timedelta(days=85)).isoformat(),
            "end": ev.isoformat(),
            "val": be, "filed": kd.isoformat(),
            "accn": f"0000320193-{fy}{fp}",
            "fy": fy, "fp": fp, "form": "10-Q" if q % 4 else "10-K",
            "frame": f"CY{q}",
        })
        # CommonStockSharesOutstanding (shares)
        shares = 5_000_000_000 + q * 10_000_000
        rows.append({
            "cik": cik, "entity": "APPLE INC", "taxonomy": "us-gaap",
            "tag": "CommonStockSharesOutstanding", "unit": "shares",
            "start": (ev - timedelta(days=85)).isoformat(),
            "end": ev.isoformat(),
            "val": shares, "filed": kd.isoformat(),
            "accn": f"0000320193-{fy}{fp}",
            "fy": fy, "fp": fp, "form": "10-Q",
            "frame": f"CY{q}",
        })

        # FY (annual) rows for each fiscal year in our range
        for yr in (2023, 2024, 2025):
            for tag, val, unit in [
                ("NetIncomeLoss",            45_000_000 + (yr - 2023) * 3_000_000, "USD"),
                ("StockholdersEquity",       210_000_000 + (yr - 2023) * 8_000_000, "USD"),
                ("GrossProfit",              90_000_000 + (yr - 2023) * 5_000_000, "USD"),
                ("Revenues",                 350_000_000 + (yr - 2023) * 20_000_000, "USD"),
            ]:
                fy_ev = date(yr, 9, 30)
                rows.append({
                    "cik": cik, "entity": "APPLE INC", "taxonomy": "us-gaap",
                    "tag": tag, "unit": unit,
                    "start": date(yr - 1, 10, 1).isoformat(),
                    "end": fy_ev.isoformat(),
                    "val": val, "filed": date(yr, 11, 15).isoformat(),
                    "accn": f"0000320193-{yr}-10K",
                    "fy": str(yr), "fp": "FY", "form": "10-K",
                    "frame": f"FY{yr}",
                })

    # Restatement: Q2 2024 NI was originally filed as 11,500,000, later restated to 11,800,000
    rows.append({
        "cik": cik, "entity": "APPLE INC", "taxonomy": "us-gaap",
        "tag": "NetIncomeLoss", "unit": "USD",
        "start": "2024-04-01", "end": "2024-06-30",
        "val": 11_800_000, "filed": "2025-02-15",
        "accn": "0000320193-2024Q2-RESTATED",
        "fy": "2024", "fp": "Q2", "form": "10-Q/A",
        "frame": "CY2",
    })
    # The ORIGINAL filing remains in the data (val=11_500_000, filed=2024-08-10)
    # A query as-of 2024-09-01 sees the original (11.5M), not the restatement (11.8M)

    # Lookahead row: filed before period ends (triggers validation)
    rows.append({
        "cik": cik, "entity": "APPLE INC", "taxonomy": "us-gaap",
        "tag": "NetIncomeLoss", "unit": "USD",
        "start": "2025-07-01", "end": "2025-09-30",
        "val": 9_000_000, "filed": "2025-09-15",  # filed mid-Q3, before Q ended
        "accn": "0000320193-2025Q3-LOOKAHEAD",
        "fy": "2025", "fp": "Q3", "form": "10-Q",
        "frame": "CY3",
    })

    # Row with null knowledge_date (also triggers validation)
    rows.append({
        "cik": cik, "entity": "APPLE INC", "taxonomy": "us-gaap",
        "tag": "Revenues", "unit": "USD",
        "start": "2023-01-01", "end": "2023-03-31",
        "val": 90_000_000, "filed": None,
        "accn": "BAD-NO-DATE",
        "fy": "2023", "fp": "Q1", "form": "10-Q",
        "frame": "CY1",
    })

    _write_jsonl("edgar", f"{ticker}_CIK{cik}.jsonl", rows)


def seed_edgar_multi() -> None:
    """Seed EDGAR for multiple tickers used in signal/backtest tests."""
    for tkr, cik in [("AAPL", 320193), ("MSFT", 789019), ("GOOGL", 1652044),
                      ("ABBV", 1800), ("JNJ", 14272)]:
        seed_edgar(tkr, cik)


# ── Prices (OHLCV + corporate actions) ─────────────────────────────────────

def seed_prices(ticker: str = "AAPL") -> None:
    """Write 5 years of monthly-end prices for one ticker.

    Creates a steady upward trend (~15% annualized) so momentum signals are predictable.
    Also writes a split event (4:1 in 2024).
    """
    rows = []
    actions = []
    px = 100.0
    for y in range(2020, 2026):
        for m in range(1, 13):
            d = date(y, m, 1)
            if d > date(2025, 6, 1):
                break
            px *= 1.01  # ~1% monthly = ~12.7% annualized
            rows.append({
                "ticker": ticker, "date": d.isoformat(),
                "open": round(px * 0.995, 2),
                "high": round(px * 1.015, 2),
                "low": round(px * 0.985, 2),
                "close": round(px, 2),
                "adjclose": round(px, 2),
                "volume": 100_000_000,
                "fetched_at": (d + timedelta(days=1)).isoformat(),
            })

    # Split 4:1 on 2024-08-28
    actions.append({
        "ticker": ticker, "date": "2024-08-28",
        "type": "split", "value": "4/1",
        "fetched_at": "2024-08-28T10:00:00",
    })

    _write_jsonl("prices", f"{ticker}.jsonl", rows)
    _write_jsonl("corporate_actions", f"{ticker}.jsonl", actions)


def seed_prices_multi() -> None:
    """Seed prices for multiple tickers."""
    for tkr in ("AAPL", "MSFT", "GOOGL", "ABBV", "JNJ"):
        seed_prices(tkr)


# ── Macro / FRED ───────────────────────────────────────────────────────────

def seed_macro() -> None:
    """Write synthetic FRED macro data covering 2020-2025.

    Includes expansion (before 2020-03), recession (2020-Q2), recovery, risk_off, late_cycle.
    """
    rows = []
    for y in range(2020, 2026):
        for m in range(1, 13):
            d = date(y, m, 1)
            if d > date(2025, 6, 1):
                break
            # Fed Funds Rate: 0-0.25% 2020-2021, then rising
            ff = 0.25 if y < 2022 else (1.0 if y == 2022 else (5.0 if y == 2023 else 4.5))
            # Yield curve (10Y-2Y): inverted in 2023
            curve = -0.5 if y == 2023 else (1.5 if y < 2022 else 0.5)
            # VIX: high in 2020 and 2022
            vix = 35 if (y == 2020 and m <= 6) else (28 if y == 2022 else 16)
            # HY spread
            hy = 6.0 if (y == 2020 and m <= 6) else (4.0 if y == 2022 else 3.0)
            # NBER recession: Q2 2020 only
            rec = 1 if (y == 2020 and 3 <= m <= 6) else 0

            for sid, val in [("DFF", ff), ("T10Y2Y", curve), ("VIXCLS", vix),
                             ("BAMLH0A0HYM2", hy), ("USREC", rec)]:
                kd = d + timedelta(days=15) if sid != "USREC" else d + timedelta(days=185)
                rows.append({
                    "series_id": sid, "event_date": d.isoformat(),
                    "knowledge_date": kd.isoformat(),
                    "val": val, "fetched_at": kd.isoformat(),
                })
    _write_jsonl("fred", "fred.jsonl", rows)


# ── Analyst estimates ──────────────────────────────────────────────────────

def seed_estimates(ticker: str = "AAPL") -> None:
    """Write analyst consensus EPS estimates for one ticker."""
    rows = []
    for p in ("0q", "+1q", "0y", "+1y"):
        rows.append({
            "ticker": ticker, "period": p, "fetched_date": "2025-06-01",
            "avg_estimate": 1.50 if "q" in p else 6.20,
            "num_analysts": 35,
            "growth": 0.08,
            "eps_trend_current": 1.50, "eps_trend_7d_ago": 1.48,
            "eps_trend_30d_ago": 1.45, "eps_trend_60d_ago": 1.42,
            "eps_trend_90d_ago": 1.40,
            "revisions_up_7d": 3, "revisions_down_7d": 1,
            "revisions_up_30d": 8, "revisions_down_30d": 3,
            "fetched_at": "2025-06-01T10:00:00",
        })
    _write_jsonl("estimates", f"{ticker}.jsonl", rows)


# ── OpenFDA drug events ────────────────────────────────────────────────────

def seed_openfda() -> None:
    """Write synthetic FDA drug approval/submission events."""
    _write_jsonl("openfda", "abbvie.jsonl", [
        {"application_number": "NDA208604",
         "sponsor_name": "ABBVIE INC.",
         "brand_name": "VENCLEXTA",
         "submission_type": "SUPPLEMENT",
         "submission_number": "S-012",
         "submission_status": "APPR",
         "submission_class_code": "1",
         "submission_class_description": "EFFICACY",
         "approval_date": "2024-06-15",
         "fetched_at": "2024-06-16T00:00:00"},
        {"application_number": "NDA206024",
         "sponsor_name": "ABBVIE INC.",
         "brand_name": "RINVOQ",
         "submission_type": "ORIGINAL",
         "submission_number": "1",
         "submission_status": "APPR",
         "submission_class_code": None,
         "submission_class_description": None,
         "approval_date": "2019-08-16",
         "fetched_at": "2024-01-01T00:00:00"},
    ])


# ── Aqueduct bridge (clinical trials pipeline) ─────────────────────────────

def seed_pipeline() -> None:
    """Write synthetic clinical trial data matching security_master sponsors."""
    _write_jsonl("pipeline", "ABBV.jsonl", [
        {"ticker": "ABBV", "cik": 1800, "nct_id": "NCT05460767",
         "trial_title": "A Study of Venclexta in Relapsed/Refractory CLL",
         "status": "ACTIVE, NOT RECRUITING",
         "phases": "PHASE3",
         "conditions": "Leukemia, Lymphocytic, Chronic, B-Cell",
         "interventions": "VENCLEXTA",
         "start_date": "2022-06-01", "completion_date": "2025-12-01",
         "lead_sponsor": "AbbVie"},
        {"ticker": "ABBV", "cik": 1800, "nct_id": "NCT04891783",
         "trial_title": "Rinvoq for Atopic Dermatitis",
         "status": "COMPLETED",
         "phases": "PHASE3",
         "conditions": "Dermatitis, Atopic",
         "interventions": "RINVOQ",
         "start_date": "2021-04-01", "completion_date": "2024-03-01",
         "lead_sponsor": "AbbVie"},
    ])


# ── Full test warehouse builder ────────────────────────────────────────────

def build_full(con) -> None:
    """Seed all sources and build the warehouse — one-stop for integration tests."""
    seed_sp500()
    seed_security_master()
    seed_edgar_multi()
    seed_prices_multi()
    seed_macro()
    seed_estimates()
    seed_openfda()
    seed_pipeline()
    warehouse.build(con)
