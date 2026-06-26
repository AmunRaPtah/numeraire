# numeraire

The data + strategy foundation for an automated **wealth-creation engine**.

*A numéraire is the base unit against which all value is measured — fitting for the
layer everything else in the engine prices itself against.*

This repository is the **financial knowledge base**: point-in-time market & fundamental
data, a security master, a library of codified strategies, and the backtesting/
verification layer the engine needs to find opportunities and create wealth
**consistently and reliably**. The autonomous execution engine itself is a separate
project that consumes this one.

It is the financial sibling of [`aqueduct`](https://github.com/AmunRaPtah/aqueduct)
(the scientific knowledge base) — **same proven framework, deliberately separate data
and pipeline.** See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for why.

## Status

🚧 Scaffold only. Design is captured in `docs/ARCHITECTURE.md`; build starts later.

## The non-negotiable principle: point-in-time correctness

Every use case here — backtesting, verification, opportunity-finding — is silently
destroyed by lookahead and survivorship bias. The data layer is built so that
self-deception is *hard*:

- **Bitemporal storage** — every fact carries both *event time* (when it happened) and
  *knowledge time* (when we could have known it). Restated fundamentals keep their
  original as-of values; a backtest sees only what was knowable then.
- **Survivorship-bias-free** — delisted, merged, and dead instruments are retained.
- **Corporate actions** — unadjusted prices + an adjustment table; adjusted values are
  derived on read, never overwritten.
- **Anti-overfitting by construction** — walk-forward / out-of-sample splits and
  deflated metrics are first-class, so "opportunities" are hypotheses to falsify, not
  noise to fund.

## Layers

```
landing (as-of, immutable)
  -> normalized (bitemporal)
    -> point-in-time views
      -> features
        -> signals
          -> backtest (realistic costs: slippage, fees, liquidity)
            -> paper -> live
```

Research and live trading read the **same** data layer, to eliminate train/serve skew.

## Inherited from aqueduct

- DuckDB warehouse; keyless-first connectors
- Harvest off-box on GitHub Actions; state as a single archive on OneDrive (rclone)
- Cross-run cursor/`harvest_state` paging; a validation gate that fails bad data loudly
- Retrieval/query API for the engine to consume

## Keyless / public data anchors (verify terms before wiring)

- **SEC EDGAR** — filings + Financial Statement Datasets + company-facts (keyless; the
  point-in-time backbone, this project's "SureChEMBL")
- **FRED** (macro), **stooq / Yahoo** (EOD prices), **CoinGecko / Binance** (crypto),
  **Frankfurter / ECB** (FX), **OpenFIGI** (security-master ID resolution)
- Financial data licensing is stricter than scientific (redistribution/real-time often
  restricted, free tiers rate-limited) — confirm each source's current terms first.

## Honest framing

Good data infrastructure is necessary but not sufficient for automated wealth creation.
The data layer is the tractable part; not fooling yourself (overfitting, costs, regime
change, execution) is the hard part. This repo's job is to make the hard part *visible
and testable*.
