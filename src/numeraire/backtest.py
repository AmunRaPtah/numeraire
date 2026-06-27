"""Point-in-time backtest of a cross-sectional momentum signal.

Demonstrates the research loop on the bitemporal price layer with the discipline the
whole project is built around:
  - SIGNAL uses only past data (12-1 momentum: 12m return skipping the last month).
  - Returns are realized t -> t+1 (no lookahead).
  - Transaction costs charged on turnover.
  - Reported vs an equal-weight benchmark, with annualized Sharpe + max drawdown.

This is a *loop validator*, NOT a validated strategy. A real edge needs out-of-sample /
walk-forward + multiple-testing correction (deflated Sharpe) — see ADR-6. One backtest
number means nothing on its own.
"""

from __future__ import annotations

import math

from .storage import connect


def _month_end_panel(con):
    rows = con.execute("""
        SELECT ticker, date_trunc('month', event_date) AS m,
               arg_max(adjclose, event_date) AS px
        FROM prices WHERE adjclose IS NOT NULL
        GROUP BY ticker, m ORDER BY m
    """).fetchall()
    panel: dict = {}   # month -> {ticker: px}
    for tkr, m, px in rows:
        panel.setdefault(m, {})[tkr] = px
    return panel


def _membership_fn(con):
    """Return a fn(month_date) -> set of PIT index members, or None if no membership data.

    Cached per-month so we don't re-query the warehouse every rebalance.
    """
    from . import warehouse
    has = con.execute(
        "SELECT count(*) FROM information_schema.tables WHERE table_name='index_membership'"
    ).fetchone()[0]
    if not has:
        return None
    cache: dict = {}

    def members(month):
        key = month.isoformat() if hasattr(month, "isoformat") else str(month)
        if key not in cache:
            cache[key] = set(warehouse.members_as_of(key, con=con))
        return cache[key]

    return members


def run(top_frac=0.2, cost_bps=10, con=None):
    owns = con is None
    con = con or connect()
    try:
        panel = _month_end_panel(con)
        months = sorted(panel)
        if len(months) < 26:
            print("[backtest] not enough history"); return
        members = _membership_fn(con)
        print("[backtest] universe: survivorship-free PIT index membership"
              if members else "[backtest] universe: priced names only "
              "(no membership table -> survivorship-biased; run `sp500` to fix)")
        strat_rets, bench_rets = [], []
        prev_holdings: set = set()
        for i in range(13, len(months) - 1):
            t, t_next = months[i], months[i + 1]
            p_t, p_n = panel[t], panel[t_next]
            p_lag1, p_lag13 = panel[months[i - 1]], panel[months[i - 13]]
            # 12-1 momentum (uses only data up to t-1 -> no lookahead)
            mom = {tk: p_lag1[tk] / p_lag13[tk] - 1
                   for tk in p_lag1 if tk in p_lag13 and p_lag13[tk]}
            # restrict to names that were IN the index as of t (survivorship-free)
            if members is not None:
                inx = members(t)
                mom = {tk: v for tk, v in mom.items() if tk in inx}
            # tradable next month (have price at t and t_next)
            elig = [tk for tk in mom if tk in p_t and tk in p_n and p_t[tk]]
            if len(elig) < 5:
                continue
            elig.sort(key=lambda tk: mom[tk], reverse=True)
            k = max(1, int(len(elig) * top_frac))
            holdings = set(elig[:k])
            # equal-weight realized return of the held names, t -> t_next
            r = sum(p_n[tk] / p_t[tk] - 1 for tk in holdings) / len(holdings)
            turnover = len(holdings ^ prev_holdings) / max(len(holdings), 1)
            r -= turnover * cost_bps / 10000
            prev_holdings = holdings
            strat_rets.append(r)
            bench = [p_n[tk] / p_t[tk] - 1 for tk in elig if p_t[tk]]
            bench_rets.append(sum(bench) / len(bench))
        _report("Momentum 12-1 (top %.0f%%)" % (top_frac * 100), strat_rets)
        _report("Equal-weight benchmark", bench_rets)
    finally:
        if owns: con.close()


def _composite(mom: dict, fundl: dict) -> dict:
    """Equal-weight z-score composite: momentum + EY + B/P + ROE + gross margin.

    Each factor z-scored cross-sectionally before summing. Tickers with no fundamental
    data contribute 0.0 on the missing factors (neutral, not penalised).
    No parameter fitting — no in-sample / out-of-sample bias on the weights.
    """
    from . import features
    z_mom = features.zscore(mom)
    z_ey  = features.zscore({tk: fundl[tk]["ey"]  for tk in fundl})
    z_bp  = features.zscore({tk: fundl[tk]["bp"]  for tk in fundl})
    z_roe = features.zscore({tk: fundl[tk]["roe"] for tk in fundl})
    z_gm  = features.zscore({tk: fundl[tk]["gm"]  for tk in fundl})
    return {
        tk: (z_mom.get(tk, 0.0) + z_ey.get(tk, 0.0) + z_bp.get(tk, 0.0)
             + z_roe.get(tk, 0.0) + z_gm.get(tk, 0.0))
        for tk in mom
    }


def _period_report(name: str, months: list, rets: list, period_years: int = 5) -> None:
    """5-year period breakdown — the parameter-free analog of walk-forward OOS."""
    chunk = period_years * 12
    rows = []
    for i in range(0, len(months), chunk):
        ms, rs = months[i:i + chunk], rets[i:i + chunk]
        if len(rs) < 12:
            continue
        eq = 1.0
        for r in rs:
            eq *= (1 + r)
        n = len(rs)
        cagr = eq ** (12 / n) - 1
        mean = sum(rs) / n
        var = sum((r - mean) ** 2 for r in rs) / max(n - 1, 1)
        sd = math.sqrt(var) if var > 0 else 0.0
        sharpe = mean / sd * math.sqrt(12) if sd else 0.0
        rows.append((f"{ms[0].year}–{ms[-1].year}", n, cagr, sharpe))
    if rows:
        print(f"\n  {name} — {period_years}-year periods:")
        for lbl, n, cagr, sharpe in rows:
            print(f"    {lbl} ({n}m): CAGR {cagr*100:+.1f}%  Sharpe {sharpe:.2f}")


def run_multifactor(top_frac: float = 0.2, cost_bps: int = 10, con=None) -> None:
    """Multi-factor backtest: momentum + value (EY, B/P) + quality (ROE, gross margin).

    Signal = equal-weight cross-sectional z-score sum across all five factors. No
    parameters fitted → no IS/OOS bias on the combination. Period breakdown shows
    regime stability (the right analog of walk-forward for a parameter-free model).

    Coverage: fundamental factors apply only to tickers with EDGAR data ingested.
    Run `numeraire ingest-universe` to populate the full price universe. Tickers
    without EDGAR data contribute neutral z-scores — momentum still applies to them.
    """
    from . import features as _ft
    owns = con is None
    con = con or connect()
    try:
        panel = _month_end_panel(con)
        months = sorted(panel)
        if len(months) < 26:
            print("[multifactor] not enough price history"); return

        tk_cik = _ft.ticker_cik_map()
        members = _membership_fn(con)

        all_tickers = {tk for m in panel.values() for tk in m}
        try:
            n_edgar = sum(
                1 for tk in all_tickers
                if tk_cik.get(tk) and con.execute(
                    "SELECT 1 FROM fundamentals WHERE cik = ? LIMIT 1", [tk_cik[tk]]
                ).fetchone()
            )
        except Exception:
            n_edgar = 0

        print(f"[multifactor] factors: mom + EY + B/P + ROE + GM  "
              f"({n_edgar}/{len(all_tickers)} tickers have EDGAR data)")
        if members:
            print("[multifactor] universe: survivorship-free PIT index membership")
        else:
            print("[multifactor] universe: priced names only (run `sp500` for survivorship-free)")

        strat_rets, bench_rets, trade_months = [], [], []
        prev_holdings: set = set()
        for i in range(13, len(months) - 1):
            t, t_next = months[i], months[i + 1]
            p_t, p_n = panel[t], panel[t_next]
            p_lag1, p_lag13 = panel[months[i - 1]], panel[months[i - 13]]

            mom = {tk: p_lag1[tk] / p_lag13[tk] - 1
                   for tk in p_lag1 if tk in p_lag13 and p_lag13[tk]}
            if members is not None:
                inx = members(t)
                mom = {tk: v for tk, v in mom.items() if tk in inx}
            elig = [tk for tk in mom if tk in p_t and tk in p_n and p_t[tk]]
            if len(elig) < 5:
                continue

            fundl = _ft.compute(con, tk_cik, t, {tk: p_t[tk] for tk in elig})
            scores = _composite({tk: mom[tk] for tk in elig}, fundl)

            elig.sort(key=lambda tk: scores[tk], reverse=True)
            k = max(1, int(len(elig) * top_frac))
            holdings = set(elig[:k])
            r = sum(p_n[tk] / p_t[tk] - 1 for tk in holdings) / len(holdings)
            turnover = len(holdings ^ prev_holdings) / max(len(holdings), 1)
            r -= turnover * cost_bps / 10000
            prev_holdings = holdings
            strat_rets.append(r)
            bench = [p_n[tk] / p_t[tk] - 1 for tk in elig if p_t[tk]]
            bench_rets.append(sum(bench) / len(bench))
            trade_months.append(t)

        _report(f"Multi-factor composite (top {top_frac*100:.0f}%)", strat_rets)
        _report("Equal-weight benchmark", bench_rets)
        _period_report(f"Multi-factor composite (top {top_frac*100:.0f}%)", trade_months, strat_rets)
    finally:
        if owns: con.close()


def _report(name, rets):
    if not rets:
        print(f"  {name}: no trades"); return
    n = len(rets)
    eq = 1.0; curve = []
    for r in rets:
        eq *= (1 + r); curve.append(eq)
    yrs = n / 12
    cagr = eq ** (1 / yrs) - 1 if yrs > 0 else 0
    mean = sum(rets) / n
    var = sum((r - mean) ** 2 for r in rets) / max(n - 1, 1)
    sd = math.sqrt(var)
    sharpe = (mean / sd * math.sqrt(12)) if sd else 0
    peak = -1e9; mdd = 0
    for v in curve:
        peak = max(peak, v); mdd = min(mdd, v / peak - 1)
    print(f"  {name}: {n} months ({yrs:.1f}y) | total x{eq:.2f} | CAGR {cagr*100:.1f}% "
          f"| Sharpe {sharpe:.2f} | maxDD {mdd*100:.1f}%")
