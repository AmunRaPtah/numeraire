"""numeraire CLI

python -m numeraire ingest AAPL MRNA           land EDGAR fundamentals + rebuild
python -m numeraire ingest-universe             ingest EDGAR for all priced tickers
python -m numeraire prices AAPL MRNA            land EOD prices
python -m numeraire prices-universe             refresh EOD prices for current S&P 500 members
python -m numeraire sp500                       load survivorship-free S&P 500 membership
python -m numeraire secmaster                   land SEC CIK/ticker/name map (identity spine)
python -m numeraire fda GILEAD PFIZER           land FDA drug-approval catalysts
python -m numeraire fda-universe                FDA catalysts for the curated pharma/biotech list
python -m numeraire pipeline ABBV               link clinical trials via aqueduct bridge
python -m numeraire pipeline-universe           pipeline bridge for the curated pharma/biotech list
python -m numeraire estimates AAPL MRNA         land analyst consensus EPS estimates + revision trend
python -m numeraire estimates-universe          estimates for the current S&P 500 members
python -m numeraire crypto                      land EOD prices for the curated crypto list
python -m numeraire pit AAPL NetIncomeLoss 2020-01-01
python -m numeraire fred [SERIES ...]           land FRED macro series (requires FRED_API_KEY)
python -m numeraire signals [N] [--asof DATE]  today's ranked composite signal (top N, default 40)
python -m numeraire backtest                    momentum-only + multi-factor + regime breakdown
python -m numeraire build                       rebuild warehouse from landed JSONL files
python -m numeraire validate                    PIT integrity checks
"""

from __future__ import annotations

import sys

from . import validate as _validate
from . import warehouse
from .sources import aqueduct_bridge, edgar, estimates, openfda, prices, sp500
from .storage import connect


def main(argv=None):
    argv = argv or sys.argv[1:]
    if not argv:
        print(__doc__)
        return
    cmd, rest = argv[0], argv[1:]
    if cmd == "ingest":
        for t in rest:
            edgar.ingest(t)
        con = connect()
        try:
            warehouse.build(con)
            _validate.validate(con)
        finally:
            con.close()
    elif cmd == "pit":
        ticker, tag, asof = rest[0], rest[1], rest[2]
        cik = edgar.cik_for(ticker)
        rows = warehouse.as_of(cik, tag, asof, unit=rest[3] if len(rest) > 3 else "USD")
        print(f"{ticker} {tag} as known on {asof}: {len(rows)} periods")
        for event_date, val, kd, form, _accn in rows[-8:]:
            print(f"  {event_date}  {val:>18,.0f}  (filed {kd} via {form})")
    elif cmd in ("prices", "pipeline", "fda"):
        fn = {"prices": prices.ingest, "pipeline": aqueduct_bridge.ingest, "fda": openfda.ingest}[cmd]
        for x in rest:
            fn(x)
        warehouse.build()
    elif cmd == "sp500":
        sp500.ingest()
        warehouse.build()
    elif cmd == "secmaster":
        from .sources import security_master

        security_master.ingest()
        warehouse.build()
    elif cmd == "build":
        warehouse.build()
    elif cmd == "signals":
        from . import signals as _sig

        top = 40
        asof = None
        i = 0
        while i < len(rest):
            if rest[i] == "--asof" and i + 1 < len(rest):
                asof = rest[i + 1]
                i += 2
            elif rest[i].lstrip("-").isdigit():
                top = int(rest[i])
                i += 1
            else:
                i += 1
        _sig.print_signals(asof=asof, top=top)
    elif cmd == "backtest":
        from . import backtest

        con = connect()
        try:
            warehouse._load_aux(con)
            print("=== Momentum-only ===")
            backtest.run(con=con)
            print("\n=== Multi-factor ===")
            backtest.run_multifactor(con=con)
        finally:
            con.close()
    elif cmd == "fred":
        from .sources import fred as _fred

        _fred.ingest([s.upper() for s in rest] if rest else None)
        warehouse.build()
    elif cmd == "ingest-universe":
        # Ingest EDGAR fundamentals for every ticker in the price universe.
        # Falls back to the curated DEFAULT universe if prices haven't been loaded yet.
        from .universe import DEFAULT

        try:
            con = connect()
            try:
                tickers = [
                    r[0] for r in con.execute("SELECT DISTINCT ticker FROM prices ORDER BY ticker").fetchall()
                ]
            finally:
                con.close()
        except Exception:
            tickers = []
        if not tickers:
            tickers = DEFAULT
        eta = len(tickers) // 5
        print(f"[ingest-universe] {len(tickers)} tickers — SEC rate-limit: ~10 req/s, expect ~{eta}s")
        for tk in tickers:
            edgar.ingest(tk)
        warehouse.build()
        _validate.validate()
    elif cmd == "prices-universe":
        # Refresh EOD prices + corporate actions for the *currently active* S&P 500
        # membership (not the full survivorship-free history) — delisted tickers
        # won't have new bars, so re-fetching them every run is wasted API calls.
        from datetime import date

        con = connect()
        try:
            tickers = warehouse.members_as_of(date.today().isoformat(), con=con)
        finally:
            con.close()
        if not tickers:
            from .universe import DEFAULT

            tickers = DEFAULT
        print(f"[prices-universe] refreshing {len(tickers)} tickers")
        for tk in tickers:
            prices.ingest(tk)
        warehouse.build()
        _validate.validate()
    elif cmd == "fda-universe":
        from .universe import PHARMA_BIOTECH

        for tk in PHARMA_BIOTECH:
            title = aqueduct_bridge._company_title(tk)
            tok = aqueduct_bridge._match_token(title) if title else None
            openfda.ingest(tok or tk)
        warehouse.build()
    elif cmd == "pipeline-universe":
        from .universe import PHARMA_BIOTECH

        for tk in PHARMA_BIOTECH:
            aqueduct_bridge.ingest(tk)
        warehouse.build()
    elif cmd == "estimates":
        for t in rest:
            estimates.ingest(t)
        warehouse.build()
    elif cmd == "estimates-universe":
        from datetime import date

        con = connect()
        try:
            tickers = warehouse.members_as_of(date.today().isoformat(), con=con)
        finally:
            con.close()
        if not tickers:
            from .universe import DEFAULT

            tickers = DEFAULT
        print(f"[estimates-universe] refreshing {len(tickers)} tickers")
        for tk in tickers:
            estimates.ingest(tk)
        warehouse.build()
    elif cmd == "crypto":
        from .universe import CRYPTO

        for tk in CRYPTO:
            prices.ingest(tk)
        warehouse.build()
    elif cmd == "validate":
        _validate.validate()
    elif cmd == "serve":
        from . import serve as _serve

        _serve.main(rest)
    elif cmd in ("watch", "unwatch"):
        from .sources.realtime import unwatch, watch, watched_symbols

        if cmd == "watch":
            if not rest:
                print("Usage: numeraire watch SYMBOL [SYMBOL ...]")
                return
            watch(rest)
            print(f"Watching: {len(rest)} symbol(s). Currently watched: {len(watched_symbols())}")
        elif cmd == "unwatch":
            unwatch(rest)
            print(f"Unwatched: {len(rest)} symbol(s). Currently watched: {len(watched_symbols())}")
    elif cmd == "watched":
        from .sources.realtime import watched_symbols

        symbols = watched_symbols()
        if symbols:
            print("Watched symbols:", ", ".join(symbols))
        else:
            print("No symbols being watched")
    elif cmd == "realtime-latest":
        from .sources.realtime import latest_tick

        if not rest:
            print("Usage: numeraire realtime-latest SYMBOL")
            return
        con = connect()
        try:
            tick = latest_tick(con, rest[0].upper())
            if tick:
                print(
                    f"{tick['ticker']}: ${tick['price']:.2f} ({tick['change']:+.2f}%) "
                    f"vol={tick['volume']} @ {tick['timestamp']}"
                )
            else:
                print(f"No realtime data for {rest[0].upper()}")
        finally:
            con.close()
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
