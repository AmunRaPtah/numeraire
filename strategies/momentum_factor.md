# Momentum Factor (Fama-French 5-Factor)

**Runner:** `fama_french.py` — Hermes

## Thesis

Cross-sectional momentum is one of the most empirically robust anomalies in equity markets (Jegadeesh & Titman 1993, Asness 2014). Stocks that performed well over the past 12 months (excluding the last month) tend to continue outperforming over the next month. Combined with value (earnings yield, book-to-price) and quality (ROE, gross margin), the signal is strengthened. The Fama-French 5-factor integration adds size, value, profitability, and investment factors to momentum for a composite ranking.

The edge persists due to:
- Behavioral underreaction to gradual news diffusion
- Institutional herding and slow capital reallocation
- Limits to arbitrage keeping the anomaly alive

## Universe

S&P 500 membership (survivorship-free point-in-time — ADR-2 compliant). Minimum 13 months of price history for momentum computation.

## Signal Logic

**Entry:** Equal-weight composite of five z-scored factors:
1. Momentum (12-1 month return, skipping 1 month lag)
2. Earnings yield (NetIncomeLoss / market cap)
3. Book-to-price (StockholdersEquity / market cap)
4. ROE (NetIncomeLoss / StockholdersEquity)
5. Gross margin (GrossProfit / Revenues)

**Exit:** Rebalanced monthly. Positions dropped from the top decile are sold. Holdings with negative trailing 12-month returns are flagged for review.

**Sizing:** Equal-weight among top 20% of ranked names.

## Costs & Constraints

- **Slippage:** 5 bps per trade
- **Turnover cost:** 10 bps on traded fraction
- **Capacity:** S&P 500 large-cap only — minimal market impact
- **Borrow cost:** Not modeled (long-only)

## Risk Limits

- Max single position: 10% of portfolio
- Max drawdown halt: 25%
- Min cash: 2%
- Max 5 trades per cycle

## Expected Regime Behavior

| Regime | Expected | Historical Basis |
|--------|----------|-----------------|
| Expansion | Outperforms | Momentum thrives in trending markets |
| Late-cycle | Mixed | Value factors add protection as momentum fades |
| Risk-off | Underperforms | Momentum crashes in sharp reversals |
| Recession | Underperforms | Systematic factor drawdown |
| Recovery | Outperforms | Trend re-establishment |

## Falsification Tests

1. Walk-forward out-of-sample CAGR < benchmark CAGR over 10+ years
2. Sharpe ratio < 0.3 after costs (10 bps)
3. 5-year rolling period showing negative alpha vs equal-weight benchmark
4. Maximum drawdown > 40% with no recovery within 18 months
5. Any regime showing consistent negative Sharpe with >36 months of data
