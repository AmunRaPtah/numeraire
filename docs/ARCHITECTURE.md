# numeraire — architecture & decisions

Design record for the financial data + strategy foundation of the automated
wealth-creation engine. Captured up front so the build (later) has direction.

## ADR-1: Separate from aqueduct (data + pipeline), share the framework

**Decision.** numeraire is its own repo and its own DuckDB warehouse, on its own harvest
schedule — *not* merged into aqueduct. The reusable scaffolding (DuckDB warehouse,
keyless connector pattern, GitHub-Actions harvest, single-archive OneDrive state,
cursor paging, validation gate, retrieval API) is shared as a common pattern/library,
not duplicated wholesale.

**Why separate:**
- **Data shape differs.** aqueduct = documents + entities (text). numeraire = time
  series + events (prices, fundamentals, filings, corporate actions). Different schema,
  indexes, query patterns.
- **Cadence & blast radius.** Scientific harvest is slow and low-stakes; financial data
  is time-critical and *moves money*. Isolation keeps a science-side bug or OOM from
  ever touching data we trade on.
- **Correctness bar.** Finance needs bitemporal point-in-time discipline and audit
  trails that would be overkill for papers.

**Why not fully independent:** the framework is proven; re-deriving it wastes the work
already hardened in aqueduct. Extract the genuinely shared bits *after* the finance
shape is clear — avoid premature abstraction.

## ADR-2: Bitemporal, point-in-time-first storage

The cardinal rule. Two timestamps on every fact:
- `event_time` — when the thing occurred / the value applies.
- `knowledge_time` (as-of) — when this value first became known to us.

Consequences:
- **Restatements** are appended, never overwritten; a query "as of date D" returns the
  value whose `knowledge_time <= D` with the latest such — i.e. what was *actually known*
  then. Fundamentals get revised; backtests must not see the revision early.
- **Survivorship-bias-free universe**: delisted/merged/dead instruments stay in the
  master and the data; the tradable universe "as of D" is reconstructed, not assumed
  from today's survivors.
- **Corporate actions**: store unadjusted prices + a separate adjustment/event table
  (splits, dividends, spinoffs); derive split/dividend-adjusted series on read.

## ADR-3: Layered pipeline

```
landing/      raw vendor payloads, immutable, stamped with knowledge_time
normalized/   bitemporal canonical tables (prices, fundamentals, actions, filings)
pit/          point-in-time views (no-lookahead query surface)
features/     engineered factors/features built only from pit views
signals/      strategy outputs
backtest/     event-driven simulation w/ realistic costs
live/         paper -> real execution (separate engine repo consumes pit + signals)
```
Research and live read the **same pit layer** → no train/serve skew.

## ADR-4: Security master

One identity layer resolving tickers / CUSIP / ISIN / FIGI across sources and across
time (tickers get reused and reassigned — map by stable id + validity interval). The
finance analog of aqueduct's entity resolution. OpenFIGI for keyless ID mapping.

## ADR-5: Validation gate (extends aqueduct's)

Fail loudly on: lookahead leaks (any feature referencing knowledge_time > as-of),
price gaps/spikes beyond bounds, stale feeds, duplicate as-of rows, missing corporate
actions around known split dates, survivorship holes (universe shrinking only forward).

## ADR-6: Backtesting

Don't reinvent the engine — evaluate `vectorbt`, `backtrader`, `zipline-reloaded`,
QuantConnect-LEAN. Spend effort on data correctness + realistic cost modeling
(slippage, commissions, borrow, liquidity/fill constraints) and on **anti-overfitting**:
walk-forward, out-of-sample holdout, multiple-testing correction / deflated Sharpe,
regime awareness. Treat every discovered "edge" as a hypothesis to falsify.

## ADR-7: Strategies as codified, versioned artifacts

`strategies/` holds each strategy as a self-describing spec (thesis, universe, signal
logic, costs, risk limits, expected behavior, falsification tests) + code. The engine
selects/composes from this library; backtests are reproducible from the spec.

## Sources (keyless-first; verify licensing before wiring)

| Source | Coverage | Key? |
|---|---|---|
| SEC EDGAR | filings, fundamentals (point-in-time backbone) | no |
| FRED | macro / rates | free key |
| stooq / Yahoo (unofficial) | EOD equity prices | no |
| CoinGecko / Binance | crypto | no |
| Frankfurter / ECB | FX | no |
| OpenFIGI | security-master IDs | free key |

Financial data licensing is stricter than scientific: redistribution and real-time are
often restricted; free tiers are rate-limited. Confirm each source's current terms
(same discipline applied to the patent-API selection in aqueduct).

## Open questions (resolve at build time)

- Asset classes for v1 (equities? + crypto? + FX/macro?).
- Cadence: EOD fits GitHub-Actions cron; intraday likely needs a small always-on
  collector (Actions cron is 5-min-granular, quota-bound, and market-hours-naive).
- Warehouse scale: DuckDB handles a lot; partitioned Parquet if tick-level later.
- Where the execution engine boundary sits (this repo ends at pit + signals + backtest).
