# Quality + Fundamental Momentum

**Runner:** `quality_momentum.py` — Hermes

## Thesis

Quality companies (high ROE, low debt, stable earnings) combined with improving fundamentals (revenue acceleration) form a robust signal. Quality provides downside protection; accelerating fundamentals provide upside momentum. The combination captures both the quality premium (Novy-Marx 2013) and fundamental momentum (revenue surprise persistence).

## Universe

S&P 500 constituents with 4+ quarters of EDGAR data.

## Signal Logic

**Entry criteria (all must pass):**
1. ROE > 15%
2. Debt-to-equity < 0.5
3. Revenue accelerating: current quarter revenue > same quarter last year AND sequential improvement for 3+ quarters

**Exit:** Any criterion fails, or monthly rebalance rotation.

**Sizing:** Equal-weight among qualifying names (typically 10-30 tickers).

## Costs & Constraints

- **Slippage:** 5 bps
- **Turnover cost:** 15 bps (higher due to quarterly fundamental refresh)
- **Capacity:** Large-cap only; limited to names with sufficient financial history
- **Concentration risk:** May produce very small portfolios in tight markets

## Risk Limits

- Min holdings: 5
- Max position: 10%
- Max drawdown: 25%
- Sector max: 35%

## Expected Regime Behavior

| Regime | Expected |
|--------|----------|
| Expansion | Strong — quality compounding |
| Late-cycle | Stable — low debt buffers |
| Risk-off | Defensive — quality holds up |
| Recession | Outperforms — quality premium |
| Recovery | Strongest — revenue acceleration peaks |

## Falsification Tests

1. Any 5-year period with negative CAGR
2. More than 10% of months with no qualifying names
3. Average Sharpe < 0.5 over full history
4. Revenue acceleration component shows no persistence beyond 1 quarter
