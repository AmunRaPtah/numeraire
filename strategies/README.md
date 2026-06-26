# strategies/

Codified, versioned financial strategies the wealth-creation engine selects from and
composes. Each strategy is a self-describing, reproducible artifact — not a black box.

Each strategy should carry:

- **Thesis** — the economic/behavioral reason an edge should exist (and why it persists).
- **Universe** — instruments + the point-in-time membership rule.
- **Signal logic** — entry/exit/sizing, built only from `pit/` views (no lookahead).
- **Costs & constraints** — slippage, fees, borrow, liquidity/capacity limits.
- **Risk limits** — max position, drawdown, exposure, correlation caps.
- **Expected behavior** — when it should work, when it should *not* (regime).
- **Falsification tests** — what out-of-sample / walk-forward result would kill it.

A strategy earns "live" only after surviving out-of-sample + walk-forward validation
with realistic costs. Treat backtested edges as hypotheses to falsify, not signals to
fund. (Empty for now — scaffold.)
