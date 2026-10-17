# Quantitative engine contract v1

**Four-tier migration:** RJ-M1-06 adds the authoritative four-tier boundary below.
The original models/functions in this document remain supported as legacy interfaces;
they do not model the full organizer problem. Their UTC, integer-bps, and optional
15-minute demo assumptions must not be applied to organizer observations.

Package: `treasury_intelligence`. Requires Python 3.10+ and Pydantic 2
(`treasury_intelligence/requirements.txt`). No database, HTTP, or frontend imports.
RJ-M1-01 defined validated immutable models and public function declarations.
RJ-M1-02 implements `calculate_required_reserve` and the pure helpers below.
RJ-M1-03 implements forecasting and RJ-M1-04 implements treasury recommendations.
Model evaluation, risk scenarios, and allocation evaluation remain declarations.
Existing forecasting and backend classes are unchanged; no execution path is implemented.

The referenced Member 1 prompt signatures, MEMBER1_SCOPE.md, and AGENT_RULES.md
were absent when this contract was written. These are new standalone signatures,
not replacements for the existing float-based backend interfaces. Any later adapter
must explicitly convert currency units and supply UTC timestamps.

## Units and serialization

All `_cents` fields are nonnegative strict integers in the context's single currency;
floats, strings, and booleans are rejected. For pathwise reserve calculations,
`net_drain_cents` is the maximum cumulative shortfall, floored at zero.
All `_bps` values are integer basis points: 100 = 1%, 10,000 = 100%.
The uncertainty multiplier may exceed 10,000 (19,600 means 1.96 times uncertainty).
Other bps fields range from 0 through 10,000. Negative yields are outside v1.
Currency is an uppercase three-letter code, not a validated currency registry entry.
All timestamps must be timezone-aware UTC; JSON uses ISO 8601 with `Z`.
Intervals are half-open [start_at, end_at). Amounts are never automatically converted.

Construct via keyword arguments or `Type.model_validate(payload)`. Parse JSON with
`Type.model_validate_json(text)`; serialize with `value.model_dump_json()` or
`value.model_dump(mode="json")`. Invalid input raises `pydantic.ValidationError`.
Unknown fields are rejected. Nested collections are immutable tuples, JSON arrays.
Canonical examples for every structure are in
`tests/treasury_intelligence/fixtures/contracts.json`.

## Structures

| Structure | Fields and interpretation |
| --- | --- |
| CashFlowBucket | start_at, end_at, inflow_cents, outflow_cents; positive interval |
| ForecastPoint | CashFlowBucket fields plus uncertainty_cents (nonnegative uncertainty magnitude) |
| ForecastResult | generated_at, model_version, points; nonempty ordered nonoverlapping intervals starting at or after generation |
| TreasuryContext | as_of, currency, checking_balance_cents, vaults (default empty); unique vault IDs |
| VaultPosition | vault_id, balance_cents, withdrawable_cents <= balance, annual_yield_bps, withdrawal_delay_minutes >= 0 |
| TreasuryPolicy | base_buffer_cents, uncertainty_multiplier_bps, tolerance_bps, min_transfer_cents, max_allocation_bps |
| ReserveResult | as_of, net_drain_cents, uncertainty_buffer_cents, base_buffer_cents, required_reserve_cents; required reserve equals component sum |
| DecisionResult | as_of, recommendation_only=true, action, amount_cents, vault_id, reserve, reason; matching reserve timestamp |
| EvaluationResult | model_version, sample_count > 0, mean_absolute_error_cents, root_mean_squared_error_cents, coverage_bps |
| RiskScenarioResult | scenario_id, seed >= 0, probability_bps, forecast, reserve, liquidity_shortfall_cents; matching forecast/reserve timestamps |
| OptimizationResult | candidate_id, recommendation_only=true, allocation_bps, allocation_cents, expected_yield_cents, liquidity_shortfall_cents, feasible, reason |

Names and reasons are nonempty strings. Rounded money metrics are integer cents;
future algorithms must round reserve requirements upward and disclose metric rounding.
Forecast error metrics concern net flow; coverage is empirical interval coverage.
Expected allocation yield is annual gross yield before costs. Allocation bps applies
to checking balance at context.as_of; existing vault balances are excluded.
Feasibility includes policy limits, reserve coverage, and withdrawal timing.
Scenario probabilities describe mutually exclusive outcomes and must sum to 10,000
across a generated batch. Seeds must make scenario generation reproducible.

SWEEP and WITHDRAW recommend a positive amount and one vault. HOLD has zero amount
and no vault. LIQUIDITY_WARNING is an alert with zero amount and no vault.
Recommendations never authorize, initiate, or confirm transfers. An external execution
layer must revalidate balances, timing, currency, permissions, and policy.

## Public signatures

```python
forecast_cashflows(history: Sequence[CashFlowBucket], *, as_of: datetime,
                   horizon_minutes: int, bucket_minutes: int,
                   model_version: str = "baseline-v1") -> ForecastResult
calculate_required_reserve(forecast: ForecastResult,
                           policy: TreasuryPolicy) -> ReserveResult
recommend_treasury_action(context: TreasuryContext, forecast: ForecastResult,
                          policy: TreasuryPolicy) -> DecisionResult
evaluate_forecasting_models(history: Sequence[CashFlowBucket], *,
                            model_versions: Sequence[str], horizon_minutes: int,
                            bucket_minutes: int) -> tuple[EvaluationResult, ...]
generate_risk_scenarios(context: TreasuryContext, forecast: ForecastResult,
                        policy: TreasuryPolicy, *, seed: int,
                        scenario_count: int) -> tuple[RiskScenarioResult, ...]
evaluate_allocation_candidates(context: TreasuryContext, forecast: ForecastResult,
                               policy: TreasuryPolicy, *,
                               candidate_allocations_bps: Sequence[int]
                               ) -> tuple[OptimizationResult, ...]
```

Future implementations must validate positive integer horizons/bucket sizes/counts,
exact horizon divisibility, nonempty model/candidate sequences, unique candidate bps,
UTC as_of, nonoverlapping ordered history ending by as_of, and sufficient history
for evaluation. Context.as_of must equal forecast.generated_at. No silent clipping,
implicit defaults for missing data, or automatic execution is permitted. Inadequate
history and incompatible inputs must raise ValueError. These algorithm-level checks
are deferred alongside the algorithms; model-level validation is active now.
Evaluation uses chronological holdout windows without future data leakage; scenario
generation returns scenario_count results; allocation evaluation returns one result
per candidate in input order, including infeasible candidates with reasons.

## RJ-M1-02 pure financial mathematics

The frozen original structures and six function signatures remain unchanged.
Additional helpers are exported from `treasury_intelligence`:

```python
maximum_cumulative_shortfall(forecast: ForecastResult, *,
    context: TreasuryContext | None = None,
    maturities: Sequence[VaultMaturity] = ()) -> int
known_vault_maturities(context: TreasuryContext,
    maturities: Sequence[VaultMaturity]) -> tuple[VaultMaturity, ...]
reserve_for_path(forecast: ForecastResult, *, uncertainty_buffer_cents: int,
    operational_buffer_cents: int, context: TreasuryContext | None = None,
    maturities: Sequence[VaultMaturity] = ()) -> ReserveResult
candidate_deployable_surplus(checking_balance_cents: int,
    required_reserve_cents: int) -> int
simple_annualized_vault_yield(principal_cents: int, annual_yield_bps: int, *,
    holding_minutes: int) -> int
early_redemption_penalty(redeemed_principal_cents: int, penalty_bps: int, *,
    early_redemption: bool, fixed_fee_cents: int = 0) -> int
expected_net_economic_benefit(expected_yield_cents: int, *, penalty_cents: int = 0,
    transaction_cost_cents: int = 0, opportunity_cost_cents: int = 0) -> int
```

Peak shortfall starts with zero opening cash. Outflows debit at each bucket's
start; inflows credit at its end. This conservative convention avoids assuming
that unspecified intrabucket inflows arrive before withdrawals. Use narrower
buckets to represent known ordering. At a shared timestamp, settlements and
inflows are available before withdrawals. The peak is never reduced retroactively
by a later arrival. Existing checking is compared with the reserve separately.

`VaultMaturity` adds an immutable validated schedule with `vault_id`, UTC
`available_at`, integer `amount_cents`, and boolean `already_in_checking=false`.
Its JSON API matches the other contracts. The caller must attest contractual
availability at the actual checking settlement timestamp, including any delay;
a maturity date before settlement is insufficient. This helper does not infer
or guarantee a product's legal availability. Only principal is supported; uncertain
future yield is excluded. No vault balance, including withdrawable balance, is
automatically an inflow. A supplied schedule requires a context with the same
as_of as forecast generation; each vault may occur once, must exist, and an unbooked
amount cannot exceed its balance. Past unbooked settlements are rejected for
reconciliation. Booked settlements cannot be future-dated and are excluded because
checking already contains the cash. Beyond-horizon settlements do not fund the path.

Forecast inflows must exclude vault settlements supplied separately. The frozen
forecast points contain no source IDs, so cross-source duplicate detection is not
possible; callers must choose one representation. Duplicate vault schedules and
booked cash are handled explicitly by the helpers. No checking balance is mutated.

`reserve_for_path` adds peak shortfall, supplied uncertainty buffer, and operational
buffer exactly. `calculate_required_reserve` uses the same peak without maturities
(its frozen signature has no schedule); it sums the forecast's supplied uncertainty
magnitudes, scales by policy.uncertainty_multiplier_bps / 10,000, and rounds upward
once. This conservative aggregation assumes no diversification benefit. It does
not estimate uncertainty or simulate risk. Reserve amounts are nonnegative and
never rounded down. Candidate surplus is max(0, checking - reserve), before policy
limits, costs, or an execution decision; unarrived funds are never added to checking.

Simple expected interest is principal * annual rate * minutes / (365 * 24 * 60),
with basis point conversion, no compounding, Decimal arithmetic, and half-up rounding
to integer cents. This is a fixed 365-day convention even in leap years. Early
redemption cost is the ceiling of redeemed principal * penalty_bps / 10,000 plus
the supplied fixed fee; a zero redemption or non-early redemption has zero cost.
This models a specified principal haircut, not every possible vault penalty rule,
and does not imply that a locked product supports early withdrawal. Net economic
benefit subtracts penalty, transaction cost, and opportunity cost from the expected
rounded yield. Unlike financial inputs, that returned integer may be negative.
These values are expected economics, never realized earnings. Inputs are validated
as nonnegative strict integers; floats/bools are rejected, and rates cannot exceed
10,000 bps. There is no Monte Carlo or allocation optimization in this task.

## RJ-M1-03 Causal feature engineering and baseline forecasting

Implements `forecast_cashflows`, feature engineering utilities, and baseline forecasting models:

```python
forecast_cashflows(history: Sequence[CashFlowBucket], *, as_of: datetime,
                   horizon_minutes: int, bucket_minutes: int,
                   model_version: str = "baseline-v1") -> ForecastResult
extract_calendar_features(dt: datetime, bucket_minutes: int = 15) -> dict[str, float | int]
compute_lag_features(buckets: Sequence[CashFlowBucket], lags: Sequence[int] = (1, 2, 4, 96),
                     fill_value: int | None = None) -> list[dict[str, int | None]]
compute_rolling_features(buckets: Sequence[CashFlowBucket], windows: Sequence[int] = (4, 16, 96),
                         strictly_prior: bool = False) -> list[dict[str, float | None]]
build_feature_matrix(buckets: Sequence[CashFlowBucket], bucket_minutes: int = 15,
                     lags: Sequence[int] = (1, 2, 4, 96),
                     windows: Sequence[int] = (4, 16, 96)) -> list[dict[str, Any]]
rolling_mean_forecast(history: Sequence[CashFlowBucket], *, as_of: datetime,
                      horizon_minutes: int, bucket_minutes: int, window: int = 16,
                      model_version: str = "rolling-mean-v1") -> ForecastResult
seasonal_naive_forecast(history: Sequence[CashFlowBucket], *, as_of: datetime,
                        horizon_minutes: int, bucket_minutes: int,
                        season_intervals: int | None = None,
                        model_version: str = "seasonal-naive-v1") -> ForecastResult
```

### Key Principles & Behavior
- **Causality**: Strictly causal. No future information is ever accessed or leaked into prior steps.
- **Separate Inflow/Outflow**: Separate non-negative predictions for inflow and outflow at each interval.
- **Uncertainty**: Empirical net-flow sample variance / seasonal error variance, rounded to non-negative integer cents.
- **Automatic Fallback**: If history is shorter than the seasonal cycle (e.g. < 96 intervals for 15-min daily cycle), seasonal-naive automatically falls back to rolling-mean. If history is empty, falls back to zero-flow baseline.
- **Horizons**: Validated for arbitrary horizons exactly divisible by bucket_minutes, including 1, 2, 4, and 96 future 15-minute intervals.
- **JSON Serialization**: Strict Pydantic 2 schema compatibility with integer cents and UTC timestamps.

## RJ-M1-04 Treasury decisions

`recommend_treasury_action(context, forecast, policy) -> DecisionResult` retains
its frozen signature. Additive immutable types `TreasuryDecisionPolicy(TreasuryPolicy)`
and `VaultTerms` provide the previously absent controls. Both support the same
Pydantic validation and JSON serialization as the original contracts. Consumers
must deserialize extended policies as TreasuryDecisionPolicy to retain controls.

TreasuryDecisionPolicy adds `sweep_window_open: bool = false`, optional nonnegative
`sweep_cap_cents = None`, positive `holding_minutes = 1440`, and `vault_terms`
(a tuple, default empty). The caller evaluates the sweep window at context.as_of;
the engine does not infer a bank calendar. Vault terms must have unique IDs present
in the context. Missing terms disqualify that vault for both sweeps and withdrawals.
A plain TreasuryPolicy therefore permits HOLD or LIQUIDITY_WARNING only.

VaultTerms contains `vault_id`, optional UTC `maturity_at = None` (explicitly no
time lock), `early_redemption_allowed = false`, `early_redemption_penalty_bps = 0`,
`early_redemption_fixed_fee_cents = 0`, `sweep_eligible = false`,
`transaction_cost_cents = 0`, and `opportunity_cost_cents = 0`. Boolean fields are
strict, cents are nonnegative integers, and penalty bps range from 0 to 10,000.
Terms describe this position/product, including the proposed placement's lock;
callers must supply current product terms rather than assume an old maturity
applies to a new investment. Transaction cost is the total cost supplied for the
modeled action, charged from checking for sweeps or deducted from withdrawal
proceeds. Opportunity cost affects investment economics, not cash settlement.

Decision precedence and calculations:

1. Calculate pathwise reserve with the existing frozen reserve function and require
   context.as_of == forecast.generated_at. If checking is below reserve, address
   the entire deficit immediately before considering sweep windows, minimums,
   tolerance, or yield. Only vaults with zero withdrawal delay and explicit terms
   qualify. Before maturity, early redemption permission is mandatory. Redemption
   never exceeds withdrawable_cents, even after maturity. A maturity date alone
   neither books checking cash nor increases the withdrawable balance.
2. For each permitted position, compute net available principal after the existing
   ceiling-rounded penalty and transaction cost. Choose a single vault able to
   cover the deficit, minimizing total cost (vault ID breaks ties). Binary search
   finds the smallest gross redemption whose net proceeds cover it. WITHDRAW's
   amount_cents is **gross principal**, while its reason records penalty, fee,
   net proceeds, and resulting checking. Immediate liquidity takes precedence
   over the economic return of an existing investment.
3. If no single position covers the deficit, return LIQUIDITY_WARNING with zero
   transfer amount, deficit, aggregate accessible net cash, and remaining funding
   gap. Even if several positions together suffice, the frozen one-vault result
   cannot express that plan; return a warning requiring separate coordination.
   Delayed funds are conservatively excluded even for a later forecast shortfall.
4. Otherwise HOLD within the reserve tolerance corridor, below the minimum sweep,
   or when the sweep window is closed/unspecified. No eligibility is inferred.
5. Sweep cap is min(optional absolute cap, floor(checking * max_allocation_bps /
   10,000)). For each sweep-eligible position, candidate principal is min(cap,
   max(0, checking - reserve - transaction_cost)). This bounds the **new transfer**,
   not total existing portfolio exposure. Apply the minimum again after cap/costs.
   The modeled holding period must allow the supplied withdrawal delay; an exit
   before maturity requires early redemption permission.
6. Compute simple expected interest for holding_minutes, applicable early-exit
   penalty, transaction and opportunity costs using the existing economics helpers.
   Reject zero or negative net benefit. Among valid candidates choose greatest
   expected net benefit (vault ID breaks ties). SWEEP's amount_cents is invested
   principal. Checking after principal and upfront fee is always at least reserve.

Every result sets recommendation_only=true and includes calculation values in
integer cents in its reason. No execution, ledger mutation, future-maturity cash
credit, database access, or random simulation occurs. Expected yield is never
reported as realized earnings. Balances and forecasts remain immutable snapshots.

## RJ-M1-05 Standalone treasury pipeline demo

Connects all Member 1 modules into an executable pure Python pipeline:

```python
run_treasury_pipeline(scenario_name: str, history: Sequence[CashFlowBucket],
                     context: TreasuryContext,
                     policy: TreasuryPolicy | TreasuryDecisionPolicy, *,
                     horizon_minutes: int = 60, bucket_minutes: int = 15,
                     model_version: str = "baseline-v1",
                     forecast: ForecastResult | None = None) -> TreasuryPipelineResult
run_demo() -> None
```

### Pipeline Flow
1. Historical Cash Flows ->
2. Baseline Forecast (or supplied path) ->
3. Supplied Provisional Uncertainty Policy ->
4. Required Reserve ->
5. Treasury Recommendation ->
6. Expected Economic Result ->
7. Structured Explanation

### Executable Demo
Run standalone without web framework or database:
```powershell
$env:PYTHONPATH="."
uv run python -m treasury_intelligence.demo
```
Demonstrates five deterministic operational scenarios:
1. Normal operation (`HOLD`)
2. Valid safe sweep (`SWEEP`)
3. High-withdrawal stress (`WITHDRAW`)
4. Locked vault with insufficient liquidity (`LIQUIDITY_WARNING`)
5. Successful HOLD (`HOLD`)
6. Full JSON serialization and 100% round-trip validation.

Uncertainty is explicitly marked as `provisional_uncalibrated`.

## RJ-M1-06 Additive four-tier contracts

Public module: `treasury_intelligence.four_tier`, also exported from the package.
Original `types.py` schemas, function signatures, pipeline, demo, and prior fixtures
are unchanged. `VaultPosition` lacks asset identity, quantities, prices, repo
maturities, duration/volatility, and debt; `TreasuryContext` cannot represent a
marked multi-asset balance sheet or timezone-unspecified source history. New models
use an independent immutable `FourTierContract`, not the legacy UTC base class.
No lossy automatic conversion to/from legacy bps or UTC contracts is supplied.

### Source fidelity and units

The supplied CSV was inspected read-only: 8,760 contiguous hourly rows, 16 columns,
2026-01-01 00:00:00 through 2026-12-31 23:00:00. SHA-256:
`2e7c1d2e5b678e9975250211e7e0017022049c510e1dd90cd7f29e931837b0c5`.
No CSV file is copied into the repository, edited, or resampled.

`OrganizerHourlyObservation` has exactly these source fields:

| Type | Source fields |
| --- | --- |
| Timezone-unspecified timestamp, on the hour | timestamp |
| Nonnegative Decimal USD | deposits_usd, withdrawals_usd |
| Signed Decimal USD, independent source value | net_flow_usd |
| Boolean (also accepts CSV strings True/False) | repo_sweep_window_open, repo_sweep_mature |
| Signed finite Decimal source rate | tier1_repo_rate_apy, tier2_bond_yield_pct |
| Positive Decimal index | tier2_bond_price_index, tier3_stock_index_price |
| Nonnegative Decimal years | tier2_bond_mod_duration |
| Nonnegative Decimal percentage points | tier3_stock_volatility_pct, emergency_overdraft_penalty_apr_pct |
| Decimal percentage points in [0,100] | tier1_early_redemption_haircut_pct, tier2_bond_liquidation_haircut_pct, tier3_stock_liquidation_haircut_pct |

Source rates retain their original scale and names. The dataset's repo APY values
(for example 4.292) are carried unchanged; `MarketRateObservation.repo_apy_pct`
explicitly uses percentage points, where 4.292 means 4.292%, not fraction 4.292.
The normalized quote also exposes bond_yield_pct, equity_volatility_pct, and
overdraft_apr_pct with observed_at provenance. MarketPriceObservation exposes
bond_price_index, bond_modified_duration_years, and equity_index_price.

Decimal fields accept decimal strings, Decimal, or integers; reject binary floats,
booleans, NaN, and infinity; and serialize to decimal strings without truncating
to bps. Source dollar amounts remain Decimal USD. Stored/proposed cash amounts
are strict integer cents. Exposure bounds are Decimal fractions in [0,1], distinct
from percentage-point quotes. Do not parse a decimal string through binary float
before model validation. Source net flow is never recomputed or overwritten.

All new timestamps are naive ISO strings/datetimes with explicit
`timestamp_basis="timezone_unspecified"` on the portfolio. Aware timestamps and
epoch numbers are rejected. No conversion, appended Z, or inferred timezone occurs.
Native history and forecasts are hourly, not fabricated quarter-hour observations.
The caller must establish when a source row becomes available: its timestamp alone
does not prove that a whole future hour's flows were known at its start.

### Positions, policy, and provenance

| Model | Fields/semantics |
| --- | --- |
| InstrumentId | TIER0_CASH, TIER1_REPO, TIER2_BOND, TIER3_EQUITY, OVERDRAFT; the last is a liability, not an asset tier |
| Tier0CashPosition | available_cents; fixed zero annual yield |
| Tier1RepoPosition | position_id, principal_cents, entered_at at 17:00, matures_at next-day 08:00, entry_apy_pct, early_break_allowed, early_break_fee_pct (default 0.5), estimated_interest_cents |
| Tier2BondPosition | position_id, index_units, cost_basis_cents, observed_price_index, marked_at, market_value_cents, matures_at, tenor_years=2, annual_yield_pct, modified_duration_years, liquidation_haircut_pct (default 2) |
| Tier3EquityPosition | shared market position fields plus annual_volatility_pct and emergency_sale_slippage_pct (default 15) |
| OverdraftLiability | principal_cents, accrued_financing_cost_cents, annual_apr_pct, credit_limit_cents; principal cannot exceed credit limit |
| CostBreakdown | liquidation_fee_cents, repo_break_fee_cents, transaction_cost_cents, funding_cost_cents, market_loss_cents; nonnegative integer cents |
| FourTierPortfolioState | as_of, timestamp_basis, USD currency, cash, repos, bonds, equities, overdraft, market_rates, market_prices, realized_costs |
| ExposureConstraint | instrument (asset only), minimum_fraction (default 0), maximum_fraction |
| FourTierRiskPolicy | minimum_liquid_reserve_cents, operational_buffer_cents, max_estimated_loss_cents, overdraft_allowed, max_overdraft_cents, all four exposure_constraints, bond_risk_method |
| ForecastRiskMetadata | model_version, generated_at, training_data_through, granularity_hours=1, net_flow_target, uncertainty_status, optional evaluation_reference, notes |
| HourlyForecastPoint | start_at, predicted_deposits_cents, predicted_withdrawals_cents, signed predicted_net_flow_cents, supplied_uncertainty_buffer_cents |

Market index units mean normalized USD exposure per source index point. Positions
validate market_value_cents = units * observed index * 100, rounded half up with
local Decimal precision. This is a schema consistency check, not a valuation engine
or real exchange-lot convention. Mark timestamps/prices must match the supplied
price snapshot, which cannot be from the future. Cost basis is not current value.
Supplied index changes already mark bond value; never subtract duration-implied
loss again from that same mark. Duration stress is a separate hypothetical risk
estimate (`observed_index_with_separate_duration_stress`), not another realized loss.

Repo principal remains a separate asset until actual settlement. Crossing maturity
does not automatically add it to cash, and a source maturity flag is not proof a
particular position has settled. Entry APY/estimated interest are observations and
estimates, not guaranteed realized cash. Future interest implementation must use
actual 15-hour holding time and known rate path, not a fixed 24-hour return.
Member 2 must remove settled repo positions when crediting cash exactly once.
Overdraft drawing increases both cash and liability; it is never investment income.
Realized costs belong to portfolio history; estimated costs belong to recommendations.
Index losses, liquidation fees/slippage, and financing cost must remain distinguishable
and must not be charged twice through both mark changes and cost reporting.

All positions have unique IDs. Exposure constraints require exactly one entry per
asset tier, ordered minimum/maximum bounds, and bounds that permit full allocation.
Disabled overdraft has a zero policy limit. Training/market/history observations
cannot be from the future. Request history must be sorted and contiguous hourly;
missing hours require an explicit upstream policy, not invented data. Metadata can
identify a source-net-flow target independently of deposits-minus-withdrawals.
`evaluated` uncertainty requires an actual evaluation reference; no metrics are
generated or fabricated by this milestone.

### Additive recommendation interface

```python
recommend_portfolio_allocation(
    request: FourTierRecommendationRequest,
) -> PortfolioRecommendation
```

This interface is available in the package and `api.py`, and raises
`NotImplementedError` until the optimizer milestone. It does not invoke the legacy
single-vault optimizer or execute trades. FourTierRecommendationRequest contains
request_id, portfolio, history, policy, metadata, and supplied hourly forecast.

PortfolioRecommendation contains request_id, as_of, action (HOLD/REBALANCE/
LIQUIDITY_WARNING), recommendation_only=true, execution_status=NOT_EXECUTED,
feasible, allocation_budget_cents, four asset targets, target_overdraft_principal_cents,
required_liquid_reserve_cents, proposed trades, expected_costs,
estimated_market_risk_loss_cents, instrument_returns, exposure_constraints,
metadata, and explanations. Target amounts must sum to the asset allocation budget;
overdraft is separately stated debt, not a fifth asset target. Feasible targets
must satisfy exposure bounds and target Tier 0 cash must cover required reserve.
The allocation budget is post-estimated-cost gross assets, not net worth.

TradeRecommendation specifies trade_id, instrument, action, principal_cents,
index_units for market BUY/SELL, position_id for SELL/REDEEM_REPO,
earliest_execution_at, expected_settlement_at, expected_maturity_at for ENTER_REPO,
expected_costs, and reason. All trades are recommendations with NOT_EXECUTED status.
Actions are instrument-checked: repo ENTER_REPO/REDEEM_REPO, bonds/equities BUY/SELL,
and overdraft BORROW/REPAY. Cash is the settlement leg rather than an orderable
security. Repo entries explicitly settle at 17:00 and mature next-day 08:00.
The tuple preserves proposed order; it does not promise atomicity or permission.

InstrumentReturnEstimate separates expected_income_cents, expected_price_change_cents,
expected_costs, estimated_stress_loss_cents, horizon_hours, and estimate_basis by
instrument. `realized=false` is mandatory. Equity expected price change may be signed;
it is not guaranteed interest. Recommendation-level estimated risk is separate from
expected transaction/liquidation costs and from already realized portfolio losses.

Schema validation is not trade execution validation. Member 2 must reconcile a
response with its request, current balances, positions, policy limits, fees, quote
freshness, repo windows/permissions, settlement timing, and financing before any
execution. This milestone does not compute target budgets, check the complete
trade-to-target accounting plan, or implement portfolio risk/optimization.

### Fixtures and integration notes

`tests/treasury_intelligence/fixtures/organizer_hourly_observation.json` preserves
the first real source row. `four_tier_request.json` includes two real hourly source
rows with an illustrative portfolio/policy/forecast. `four_tier_response.json` is
an illustrative recommendation, not a generated optimizer result. The repo return
example uses a stated constant-rate ACT/365 assumption for 15 hours; forecasts,
estimates, and stress amounts are explicitly examples, not evaluated metrics.

See [Member 2 integration](MEMBER2_INTEGRATION.md) and
[Member 3 frontend fields](MEMBER3_FRONTEND_FIELDS.md).
