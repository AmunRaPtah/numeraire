# Piotroski F-Score

**Runner:** `piotroski.py` — Hermes

## Thesis

Piotroski (2000) proposed a 9-point fundamental score to identify value stocks with improving financial health. The F-Score evaluates three dimensions: profitability (4 points), leverage/liquidity (3 points), and operating efficiency (2 points). High-F-Score value stocks significantly outperform low-F-Score value stocks. The strategy exploits market underreaction to fundamental signals embedded in annual financial statements.

## Universe

S&P 500 constituents (point-in-time) with 10-K annual filings available in the EDGAR warehouse.

## Signal Logic

**F-Score components (1 point each):**
1. Positive net income (ROA > 0)
2. Positive operating cash flow
3. ROA improvement year-over-year
4. Operating cash flow > net income (accrual quality)
5. Decrease in long-term debt ratio
6. Increase in current ratio
7. No new shares issued (dilution check)
8. Increase in gross margin
9. Increase in asset turnover

**Entry:** Score ≥ 7 (strong), rank by score × value attractiveness
**Exit:** Score drops below 5, or rebalance monthly
**Sizing:** Equal-weight among top-ranked

## Costs & Constraints

- **Slippage:** 5 bps
- **Turnover cost:** 10 bps
- **Data lag:** Fundamentals have up to 45-day filing lag from period end
- **Staleness:** Points expire 12 months after filing

## Risk Limits

- Max position: 10%
- Max drawdown halt: 25%
- Min 5 holdings (diversification floor)

## Expected Regime Behavior

| Regime | Expected |
|--------|----------|
| Expansion | Outperforms — improving fundamentals widespread |
| Late-cycle | Mixed — high-quality holds up, low-quality fades |
| Risk-off | Defensive — strong balance sheets resist |
| Recession | Outperforms — quality premium expands |
| Recovery | Strong — early-cycle fundamental improvement captured |

## Falsification Tests

1. No significant spread between F-Score ≥ 7 and ≤ 3 quintiles over 10 years
2. CAGR below risk-free rate on 5-year rolling basis
3. F-Score components show no individual predictive power
4. Strategy loses money in recession regimes (should be defensive)
