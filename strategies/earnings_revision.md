# Earnings Revision Momentum

**Runner:** `earnings_revision.py` — Hermes

## Thesis

Analyst estimate revisions are one of the strongest cross-sectional return predictors. When analysts revise earnings estimates upward, they tend to do so in clusters (herding), and prices only gradually incorporate the new information. Revenue acceleration (quarter-over-quarter growth for 3+ quarters) serves as a fundamentals-based proxy for revision momentum, capturing improving business trajectories before analyst revisions fully reflect them.

## Universe

S&P 500 constituents with 4+ quarters of EDGAR revenue data.

## Signal Logic

**Revenue acceleration** = (Revenue_q − Revenue_q−4) / Revenue_q−4 — with acceleration measured as the change in this growth rate over 3+ quarters.

**Entry:** Sustained revenue acceleration (growth rate increasing for 3+ consecutive quarters).

**Exit:** Revenue growth decelerates for 2 consecutive quarters.

**Sizing:** Equal-weight among accelerating names.

## Costs & Constraints

- **Slippage:** 5 bps
- **Turnover cost:** 10 bps
- **Data lag:** Quarterly filings (10-Q) with ~40-day filing delay
- **Signal staleness:** Revenue data may be 1-4 months old

## Risk Limits

- Max position: 10%
- Max drawdown halt: 25%
- Min holdings: 5
- Sector max: 35%

## Expected Regime Behavior

| Regime | Expected |
|--------|----------|
| Expansion | Strong — broad-based revenue acceleration |
| Late-cycle | Positive but narrowing — fewer accelerating names |
| Risk-off | Negative — sharp deceleration |
| Recession | Negative — widespread revenue decline |
| Recovery | Strongest — inflection in growth rates |

## Falsification Tests

1. No significant spread between accelerating and decelerating portfolios over 10 years
2. Average holding period < 3 months (too transient to capture)
3. Revenue acceleration reverses in 50%+ of cases within 2 quarters
4. False positive rate (acceleration → subsequent deceleration) > 40%
