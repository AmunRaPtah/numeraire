"""numeraire CLI

  python -m numeraire ingest AAPL MRNA           land EDGAR fundamentals + rebuild
  python -m numeraire ingest-universe             ingest EDGAR for all priced tickers
  python -m numeraire prices AAPL MRNA            land EOD prices
  python -m numeraire sp500                       load survivorship-free S&P 500 membership
  python -m numeraire secmaster                   land SEC CIK/ticker/name map (identity spine)
  python -m numeraire fda GILEAD PFIZER           land FDA drug-approval catalysts
  python -m numeraire pipeline ABBV               link clinical trials via aqueduct bridge
  python -m numeraire pit AAPL NetIncomeLoss 2020-01-01
  python -m numeraire signals [N] [--asof DATE]  today's ranked composite signal (top N, default 40)
  python -m numeraire backtest                    momentum-only + multi-factor (if EDGAR present)
  python -m numeraire build                       rebuild warehouse from landed JSONL files
  python -m numeraire validate                    PIT integrity checks
"""

from __future__ import annotations

import sys

from . import warehouse, validate as _validate
from .sources import edgar, prices, openfda, aqueduct_bridge, sp500
from .storage import connect


def main(argv=None):
    argv = argv or sys.argv[1:]
    if not argv:
        print(__doc__); return
    cmd, rest = argv[0], argv[1:]
    if cmd == "ingest":
        for t in rest:
            edgar.ingest(t)
        con = connect()
        try:
            warehouse.build(con); _validate.validate(con)
        finally:
            con.close()
    elif cmd == "pit":
        ticker, tag, asof = rest[0], rest[1], rest[2]
        cik = edgar.cik_for(ticker)
        rows = warehouse.as_of(cik, tag, asof, unit=rest[3] if len(rest) > 3 else "USD")
        print(f"{ticker} {tag} as known on {asof}: {len(rows)} periods")
        for event_date, val, kd, form, accn in rows[-8:]:
            print(f"  {event_date}  {val:>18,.0f}  (filed {kd} via {form})")
    elif cmd in ("prices", "pipeline", "fda"):
        fn = {"prices": prices.ingest, "pipeline": aqueduct_bridge.ingest,
              "fda": openfda.ingest}[cmd]
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
                asof = rest[i + 1]; i += 2
            elif rest[i].lstrip("-").isdigit():
                top = int(rest[i]); i += 1
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
    elif cmd == "ingest-universe":
        # Ingest EDGAR fundamentals for every ticker in the price universe.
        # Falls back to the curated DEFAULT universe if prices haven't been loaded yet.
        from .universe import DEFAULT
        try:
            con = connect()
            try:
                tickers = [r[0] for r in con.execute(
                    "SELECT DISTINCT ticker FROM prices ORDER BY ticker"
                ).fetchall()]
            finally:
                con.close()
        except Exception:
            tickers = []
        if not tickers:
            tickers = DEFAULT
        print(f"[ingest-universe] {len(tickers)} tickers — SEC rate-limit: ~10 req/s, expect ~{len(tickers)//5}s")
        for tk in tickers:
            edgar.ingest(tk)
        warehouse.build()
        _validate.validate()
    elif cmd == "validate":
        _validate.validate()
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
