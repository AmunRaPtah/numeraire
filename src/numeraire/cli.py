"""numeraire CLI: ingest EDGAR fundamentals, build the bitemporal warehouse, query
point-in-time, validate.

  python -m numeraire ingest AAPL MRNA      # land + build
  python -m numeraire pit AAPL Revenues 2020-01-01
  python -m numeraire validate
"""

from __future__ import annotations

import sys

from . import warehouse, validate as _validate
from .sources import edgar, prices, openfda, aqueduct_bridge
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
    elif cmd == "build":
        warehouse.build()
    elif cmd == "backtest":
        from . import backtest
        con = connect()
        try:
            warehouse._load_aux(con); backtest.run(con=con)
        finally:
            con.close()
    elif cmd == "validate":
        _validate.validate()
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
