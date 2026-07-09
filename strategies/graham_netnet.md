# Graham Net-Net (NCAV)

**Runner:** `graham_net_net.py` — Hermes

## Thesis

Benjamin Graham's classic Net Current Asset Value (NCAV) strategy: buy stocks trading below their net current asset value (current assets minus total liabilities). The strategy exploits extreme undervaluation where the market prices assets below liquidation value. While rare in large-cap indices, it occasionally surfaces during bear markets and sector panics.

## Universe

S&P 500 constituents (point-in-time) with EDGAR current asset and liability data.

## Signal Logic

**NCAV** = Current Assets − Total Liabilities

**NCAV/Price** = NCAV / Market Capitalization

**Entry:** NCAV/Price > 1.0 (stock trading below liquidation value).

**Exit:** NCAV/Price < 0.8, or 12-month hold, or monthly rebalance.

**Sizing:** Equal-weight among qualifying names (typically very few; may go unfilled for months).

## Costs & Constraints

- **Slippage:** 10 bps (thin opportunity set may include smaller names)
- **Turnover cost:** 10 bps
- **Opportunity set:** May be very small or zero for extended periods
- **Data lag:** Uses latest 10-K/10-Q filed

## Risk Limits

- Max position: 15% (concentrated when few opportunities)
- Max drawdown: 30%
- Min cash when no opportunities: 100%
- Forced to cash if fewer than 3 qualifying names

## Expected Regime Behavior

| Regime | Expected |
|--------|----------|
| Expansion | Rarely triggers — markets fairly priced |
| Risk-off | Begins to surface |
| Recession | Most opportunities — deep value emerges |
| Recovery | Strongest — mean reversion from extreme undervaluation |
| Late-cycle | Vanishes as prices recover |

## Falsification Tests

1. No qualifying names for 5+ consecutive years
2. When triggered, negative CAGR over 3-year horizon
3. NCAV/Price > 1.5 threshold shows no better returns than 1.0
4. Strategy loses during recession (should be the best time)
