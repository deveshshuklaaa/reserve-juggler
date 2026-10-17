# Member 2: four-tier contract boundary

Import `FourTierRecommendationRequest`, `PortfolioRecommendation`, and
`recommend_portfolio_allocation` from `treasury_intelligence`. They depend on
Pydantic, not ML, FastAPI, ORM, or a dataset loader. The recommendation function is
a contract-only stub in RJ-M1-06. No API/database files or old signatures changed.

- Validate CSV row strings with `OrganizerHourlyObservation.model_validate(row)`.
  It matches all 16 headers. Load with strings/Decimal, never float. Preserve the
  source CSV and hourly rows; retain source net_flow_usd independently.
- New timestamps have unspecified timezone. Do not use the old UTC contracts as
  an implicit adapter. Establish source availability semantics before a backtest;
  only rows available by the decision cutoff may be supplied.
- Snapshot Tier 0 cash, unsettled repo principal, index-marked bonds/equities,
  and overdraft debt separately. Market units are normalized dollar-per-index-point
  exposure. Marked cents are half-up; the schema verifies units times index.
- Repo entry is 17:00, maturity next-day 08:00. Do not add both repo principal
  and a maturity cash credit to liquid cash. Apply actual settlement once. Source
  flags are not position-level execution receipts. Validate early-break permissions.
- Response trades provide instrument/action, gross principal, market units,
  position references, execution/settlement timing, repo maturity, expected costs,
  and explanations. BUY/SELL amounts are before separately reported costs.
  Reconcile budget/targets, source policy, reserve, all cash legs, fees, credit limits,
  holdings, timing, and quote freshness before execution. Preserve trade tuple order;
  no atomicity is promised. The schema does not implement this execution gate.
- Borrowing is liability financing, never return. Keep realized financing,
  market losses, liquidation slippage, and transaction fees distinguishable.
  Observed bond index changes already mark the position; duration stress is
  hypothetical and must not be charged again to the same mark.
- `recommendation_only=true` / `execution_status=NOT_EXECUTED` are fixed. Store
  actual execution receipts in Member 2's own models; do not label a recommendation
  as executed. The example response is illustrative, not an optimizer output.

Serialize with `model_dump_json()` or `model_dump(mode="json")`; Decimal fields
become strings. Read the request/response fixtures and ENGINE_CONTRACT.md for the
complete field contract. Legacy single-vault APIs remain operational for compatibility.

RJ-M1-08 adds `instrument_economics` pure helpers (also package exports). Use supplied
Decimal rate fixings for repo/overdraft accrual, source index marks for bonds/equity,
and conditional sale P&L for execution planning. Results are calculation_only=true,
not accounting receipts. Repo defaults to forfeiting positive interest on early break
unless the product explicitly permits payment. ACT/365 fixed uses actual duration;
income rounds half up, fees/funding round upward. Read the RJ-M1-08 contract section
for repayment timing, cost-basis allocation, and no-double-counting conventions.

RJ-M1-10 adds a separate canonical boundary: import PortfolioState,
FourTierTreasuryPolicy, and HourlyForecastPoint from `treasury_intelligence.portfolio`,
and FourTierLiquidityRiskRequest/calculate_four_tier_liquidity_risk from
`treasury_intelligence.liquidity_risk`. Do not pass the older root four_tier models.
The input path must cover the first hour at portfolio.as_of. Explicitly attest
repo settlement timing, obligations already included in forecasts, calibrated
allowance provenance or complete weighted scenarios, liquidation delays, and
available new credit. Do not include the same repo receipt in forecast deposits
and repo_settlements. Result.reserve is canonical FourTierReserveResult; projected
shortages and hypothetical liquidation are not executions. actual_payout_failure
is null. Read the RJ-M1-10 contract section for the two uncertainty modes, expected
shortfall definitions, buffer floors, and funding-cost assumptions.

RJ-M1-11's executable **recommendation** boundary is
`recommend_four_tier_allocation(AllocationOptimizerRequest) -> AllocationOptimizerResult`
in `optimizer.py` (also root/API). Pass the canonical RJ-M1-10 liquidity request
and explicit AllocationRewardModel; market purchases additionally require declared
USD/index/quantity conversion and explicit exposure caps. Current quotes/cutoffs
are validated without loading future data. Result.decision is canonical
FourTierDecisionResult with targets and ordered RecommendedOrders. The canonical
`portfolio.recommend_portfolio_allocation` dispatcher returns that decision for
the new request; old envelopes without assumptions retain their explicit refusal.
Read summary_action, disclosed reward_assumptions, baseline risk, selected-plan
funding checks, and search_truncated. Targets exclude exogenous future cash flows;
late sale proceeds are not immediate buying cash. Revalidate balances, contractual
settlement, fees, unit/lot conventions, source versions and all constraints before
execution. Stable IDs are recommendations, never fill confirmations. Legacy
single-repo hints do not flatten multi-asset orders into one vault.

## RJ-M1-13: Official Four-Tier Pipeline & Execution Loop Handoff

The standalone four-tier pipeline demo is implemented in `treasury_intelligence.four_tier_demo`
(executable via `python -m treasury_intelligence.four_tier_demo`).

### 1. Canonical Public Imports
```python
from treasury_intelligence import (
    # Core state & contracts
    PortfolioState,
    CashPosition,
    RepoPosition,
    BondPosition,
    EquityPosition,
    OverdraftLiability,
    PortfolioValuation,
    MarketRateObservation,
    MarketPriceObservation,
    FourTierTreasuryPolicy,
    FourTierReserveResult,
    FourTierDecisionResult,
    RecommendedOrder,
    AllocationTargets,
    TierAllocationLimit,
    HourlyForecastPoint,
    # Optimizer & recommendation boundary
    AllocationOptimizerRequest,
    AllocationOptimizerResult,
    AllocationRewardModel,
    AssetRewardAssumption,
    recommend_four_tier_allocation,
    # Liquidity & Monte Carlo risk
    FourTierLiquidityRiskRequest,
    FourTierLiquidityRiskResult,
    calculate_four_tier_liquidity_risk,
    simulate_multi_asset_monte_carlo_risk,
    MultiAssetMonteCarloRiskResult,
    # Forecasting & loader
    load_organizer_dataset,
    forecast_hourly_cashflows,
    HourlyForecastConfig,
    HourlyForecastResult,
    # Demo pipeline
    run_four_tier_demo,
    FourTierDemoSuiteResult,
    FourTierDemoScenarioResult,
    build_demo_portfolio_state,
)
```

### 2. Portfolio Context Construction from Simulation Ledger
When constructing `PortfolioState` at simulation cutoff timestamp $T$ (`as_of`):
1. **Clock & Timezone**: Time basis is strictly `"UNSPECIFIED"`. All timestamps must be native, naive `datetime` objects on hourly boundaries (`minute=0, second=0, microsecond=0`).
2. **Provenance**: Set `source_type="ORGANIZER_HISTORICAL"`, `dataset_id="treasury_4tier_dataset:sha256:2e7c1d2e5b678e9975250211e7e0017022049c510e1dd90cd7f29e931837b0c5"`, and `source_observation_timestamp=as_of`.
3. **Cash Position**: Map available checking balance in cents to `cash.balance_cents` with `liquidity.classification="IMMEDIATE"`.
4. **Active Repos**: Repos entered at 17:00 remain locked until next-day 08:00. Set `status="LOCKED"`, `liquidity.classification="LOCKED"`, `locked_cents=principal_cents`. Do NOT credit repo principal to available cash until 08:00 settlement.
5. **Mark-to-Market Assets**: Bonds (Tier 2) and Equities (Tier 3) are marked to the current hourly observation prices:
   - Bond mark: `current_market_price_index = obs.tier2_bond_price_index`, `market_value_cents = round(units * price * 100)`.
   - Equity mark: `current_market_price_index = obs.tier3_stock_index_price`, `market_value_cents = round(units * price * 100)`.
   - Haircuts: `liquidity.liquidatable_value_cents = market_value_cents - haircut_fee`.
6. **Liabilities**: Outstanding overdraft borrowings are separately accounted in `overdrafts` with active APR.
7. **Valuation**: Ensure `total_portfolio_value_cents == cash + repo + bond + equity` and `net_portfolio_value_cents == total - liabilities`.

### 3. Policy & Reward Configuration
- `FourTierTreasuryPolicy`:
  - `base_buffer_cents`: Operational liquidity floor (e.g. $1,000,000 / 100,000,000 cents).
  - `uncertainty_multiplier_bps`: Scaling factor for forecast drain.
  - `repo_sweep_window_open`: Set to `obs.repo_sweep_window_open` (True at 17:00, False otherwise).
  - `allow_early_repo_redemption`: Controls early-break permission (incurs 0.5% fee and interest forfeiture).
  - `tier_limits`: Optional concentration bounds per asset tier.
- `AllocationRewardModel`:
  - `holding_hours`: Planning horizon (e.g. 15 hours for overnight session).
  - `risk_aversion`: Sensitivity parameter for downside volatility.
  - Tier 1: Floating repo APY from quote; 0 price return; 0 units.
  - Tier 2: Bond yield and modified duration stress; 2% liquidation haircut.
  - Tier 3: Equity volatility risk; 15% emergency slippage; **zero guaranteed equity return**.

### 4. How Proposed Trades Must Be Passed to Execution
Inspect `opt_res.decision.orders`:
- Every order is strictly `recommendation_only=True` with `execution_status="NOT_EXECUTED"`.
- Member 2's execution simulator is the sole authority for order validation, execution, and ledger persistence.
- Order types:
  - `INVEST_REPO`: Settle at 17:00, debits cash, locks principal until 08:00 next day (`expected_maturity_at`).
  - `REDEEM_REPO`: Early termination (only if permitted), returns principal minus 0.5% penalty.
  - `BUY_BONDS` / `BUY_EQUITIES`: Market purchases, debit cash + transaction fee, credit position units.
  - `SELL_BONDS` / `SELL_EQUITIES`: Market sales, debit position units, credit proceeds after haircuts.
  - `BORROW_OVERDRAFT` / `REPAY_OVERDRAFT`: Financing actions adjusting overdraft liability.
- Member 2 must validate current balance availability, settlement cutoff, and policy constraints prior to execution.

### 5. Feeding Execution Outcomes into Subsequent Decision Cycles
1. **Executed Orders**: Create corresponding immutable simulation ledger entries. Update cash balance and position tables.
2. **Next Hour Decision**: At timestamp $T+1$:
   - Build a fresh `PortfolioState` reflecting settled transactions and updated source market quotes.
   - For repo investments made at 17:00: at 08:00 (15 hours later), credit principal + earned interest ($P \times APY \times 15 / 8760$) to cash ledger, and retire the matured repo position.
3. **Rejected/Unfilled Orders**: If Member 2 rejects an order (e.g. due to simulated settlement delay or balance mismatch), do NOT update ledger positions. The engine will evaluate the unaltered portfolio at the next cycle.
4. **Zero Future Lookahead**: Historical observation filters must strictly enforce `timestamp <= as_of`. Never expose future rows to forecasting or decision models.
