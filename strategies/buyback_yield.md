# Buyback Yield

**Runner:** `buyback_yield.py` — Hermes

## Thesis

Corporate share buybacks reduce the share count, mechanically increasing EPS and signaling management's belief that the stock is undervalued. Firms with high buyback yield (large net share repurchase relative to market cap) tend to outperform, particularly when funded by operating cash flow rather than debt.

## Universe

S&P 500 constituents with 12+ months of EDGAR share-count data (CommonStockSharesOutstanding).

## Signal Logic

**Buyback yield** = (SharesOutstanding_t−12 − SharesOutstanding_t) / SharesOutstanding_t−12

**Quality filter:** Operating cash flow > CapEx (buybacks funded from operations).

**Entry:** Top quintile by quality-filtered buyback yield.

**Exit:** Monthly rebalance; positions exiting top quintile sold.

**Sizing:** Equal-weight among top quintile.

## Costs & Constraints

- **Slippage:** 5 bps
- **Turnover cost:** 10 bps
- **Data lag:** Quarterly filings (10-Q) — share counts update each quarter
- **False signals:** Buybacks via debt issuance filtered out

## Risk Limits

- Max position: 10%
- Max drawdown halt: 25%
- Min holdings: 5

## Expected Regime Behavior

| Regime | Expected |
|--------|----------|
| Expansion | Strong — companies have cash to repurchase |
| Late-cycle | Mixed — some buybacks are debt-funded |
| Risk-off | Underperforms — buybacks tend to pause |
| Recession | Underperforms — buybacks collapse |
| Recovery | Strong — resumption of buyback programs |

## Falsification Tests

1. Top-quintile buyback yield does not outperform bottom quintile over 10 years
2. High-buyback + low-quality (debt-funded) shows same returns as high-quality
3. Buyback yield loses significance after controlling for value factors
