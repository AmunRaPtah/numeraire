# Pharma Catalyst (FDA PDUFA)

**Runner:** `fda_pdufa.py` — Hermes

## Thesis

Binary catalyst events in biotech/pharma (FDA approval decisions, trial readouts) create asymmetric return profiles. A Phase 3 success or FDA approval can drive 100-500% moves; a failure can wipe out 80%+. By combining catalyst awareness with fundamental health (cash runway, R&D spend), the strategy can avoid binary risk while still capturing the upside of pipeline progress. This is the unique edge that only Numeraire's aqueduct bridge provides — fusing clinical pipelines with financial runway.

## Universe

Pharma/biotech tickers in the PHARMA_BIOTECH curated list with both EDGAR fundamentals and aqueduct clinical-trial or openFDA catalyst data.

## Signal Logic

**Long signals:**
1. Upcoming PDUFA date (FDA decision) within 3 months with positive advisory committee vote
2. Phase 3 trial completion with positive efficacy data
3. Cash runway > 18 months (Q burn from R&D + SG&A)

**Avoid/Halt signals:**
1. Cash runway < 12 months AND no catalyst
2. FDA Complete Response Letter (rejection) for lead program
3. Trial placed on clinical hold

**Exit:** Catalyst resolved (approval → take profit; rejection → exit immediately) or cash declines below 12-month runway.

**Sizing:** Equal-weight, max 5-8 positions (limited opportunity set).

## Costs & Constraints

- **Slippage:** 15-30 bps (biotech can be illiquid)
- **Turnover cost:** 20 bps
- **Binary risk:** Catalyst-driven moves are extreme
- **Data dependency:** Requires aqueduct pipeline bridge to be populated
- **Borrow cost:** May be high for short-selling biotech

## Risk Limits

- Max position: 8% (higher binary risk)
- Max drawdown halt: 30%
- Max single-catalyst exposure: 15%
- No leverage on pre-catalyst positions
- Forced exit at catalyst resolution regardless of P&L

## Expected Regime Behavior

Low correlation to equity markets — driven by idiosyncratic catalysts. Historically performs across all regimes. The key risk is not market beta but binary trial outcomes.

## Falsification Tests

1. Cash runway metric shows zero predictive power for survival
2. Positive advisory committee vote predicts approval no better than 50/50
3. Strategy has negative Sharpe over any 5-year period
4. Returns explained entirely by biotech ETF (IBB/XBI) beta
