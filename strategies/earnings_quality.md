# Earnings Quality (Low Accruals)

**Runner:** `earnings_quality.py` — Hermes

## Thesis

Sloan (1996) demonstrated that the accrual component of earnings is less persistent than the cash flow component. Firms with high accruals (earnings far above operating cash flow) tend to experience negative future returns as the market over-extrapolates earnings. Conversely, low-accrual firms (high cash flow relative to earnings) tend to outperform. This is the classic "accrual anomaly."

## Universe

S&P 500 constituents with trailing 12 months of EDGAR data.

## Signal Logic

**Accrual ratio** = (Net Income − Operating Cash Flow) / (Total Assets)

**Entry:** Bottom tercile by accrual ratio (lowest accruals = highest quality).

**Exit:** Monthly rebalance. Positions exiting bottom tercile are sold.

**Sizing:** Equal-weight among qualifying names.

## Costs & Constraints

- **Slippage:** 5 bps
- **Turnover cost:** 10 bps
- **Data lag:** Annual filings (10-K) preferred; quarterly (10-Q) accepted with reduced confidence

## Risk Limits

- Max position: 10%
- Max drawdown: 25%
- Sector concentration: max 30% in any sector

## Expected Regime Behavior

Persistent across regimes — the anomaly has shown consistent premiums with modest drawdowns. Slightly stronger in expansion (more earnings manipulation opportunity).

## Falsification Tests

1. Accrual hedge portfolio (long low, short high) Sharpe < 0.5 over 10 years
2. Strategy fails to produce positive alpha after size and value adjustments
3. No monotonic relationship across accrual deciles
