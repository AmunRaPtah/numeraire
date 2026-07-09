# Dogs of the Dow

**Runner:** `dogs_of_dow.py` — Hermes

## Thesis

The "Dogs of the Dow" strategy selects the 10 highest-dividend-yielding stocks in the Dow Jones Industrial Average. The thesis is twofold: (1) mean reversion in yields — high current yield often results from price declines that reverse; (2) dividend yield as a value signal — high yields indicate undervaluation. While oversimplified and well-known, the strategy has historically produced competitive risk-adjusted returns with lower volatility.

## Universe

S&P 500 (or Dow 30) constituents with 12+ months of dividend data.

## Signal Logic

**Trailing dividend yield** = (Sum of dividends paid past 12 months) / Current price

**Entry:** Top 10 by trailing dividend yield.

**Exit:** Annual rebalance (December). Holdings falling out of top 10 are sold and replaced.

**Sizing:** Equal-weight among top 10.

## Costs & Constraints

- **Slippage:** 5 bps
- **Turnover cost:** 20 bps (annual rebalance, higher per-trade)
- **Concentration:** Only 10 names, single-index exposure
- **Tax drag:** Dividends taxed as ordinary income (for taxable accounts)
- **Signal frequency:** Annual — low maintenance

## Risk Limits

- Max position: 20% (only 10 names)
- Max drawdown: 25%
- Max sector concentration: 40%

## Expected Regime Behavior

| Regime | Expected |
|--------|----------|
| Expansion | Competitive but not exceptional |
| Late-cycle | Defensive — high-yield stable |
| Risk-off | Defensive — dividend payers hold up |
| Recession | Underperforms — dividend cuts |
| Recovery | Lags — growth outperforms value |

## Falsification Tests

1. Dogs of the 10 underperform the Dow 30 equal-weight over 15 years
2. Sharpe ratio < 0.3 after tax drag adjustment
3. Any 5-year rolling period with negative total return
4. Bottom-decile yield names outperform top-decile over 20 years
