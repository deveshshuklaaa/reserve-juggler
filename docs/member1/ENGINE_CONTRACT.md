# Quantitative engine contract v1

Release authority: read the RJ-M1-14 clarification at the end and the current
MEMBER2_INTEGRATION.md / MEMBER3_FRONTEND_FIELDS.md handoffs for canonical
portfolio consumers. Earlier single-vault and four_tier examples are compatibility
contracts, not interchangeable canonical portfolio schemas. See FINAL_AUDIT.md
for measured validation and unresolved integration boundaries.

**Canonical boundary (2026-10-18):** The reviewed portfolio model definitions from
`1fcff80` are inputs for liquidity risk and the RJ-M1-11 optimizer. The portfolio
recommendation function now dispatches additive optimizer requests with explicit
assumptions; older envelopes alone still cannot select an investment safely.
Prior RJ-M1-07/08/09 implementations and root four_tier schema exports remain
legacy-compatible; they have not been silently converted. Import canonical inputs
explicitly from `treasury_intelligence.portfolio`. See the RJ-M1-10 section and
[historical compatibility findings](CANONICAL_ALIGNMENT_CHECK.md).

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

## RJ-M1-07 Official hourly forecast foundation

Native hourly forecasting and causal feature engineering for the organizer dataset.
Preserves existing 15-minute synthetic forecasting (`forecast_cashflows`, `CashFlowBucket`, `ForecastResult`) without alteration.

### Core Contracts and Configuration

| Model / Enum | Fields and interpretation |
| --- | --- |
| `ForecastResolution` | `HOURLY = "1h"`, `QUARTER_HOURLY = "15m"` |
| `HourlyCashFlowBucket` | `timestamp`, `deposits_usd`, `withdrawals_usd`, `net_flow_usd`; property helpers for integer cents (`deposits_cents`, `withdrawals_cents`, `net_flow_cents`) |
| `HourlyForecastConfig` | `resolution="1h"`, `horizon_hours` (1, 3, 6, 15, 24), `model_version`, `rolling_window_hours=24`, `season_hours=24`, `uncertainty_multiplier=1.0`, `uncertainty_status="provisional_uncalibrated"` |
| `HourlyForecastResult` | `generated_at`, `model_version`, `resolution="1h"`, `horizon_hours`, `points: tuple[HourlyForecastPoint, ...]`, `metadata: ForecastRiskMetadata`; helper properties for totals and path vectors |
| `SUPPORTED_HOURLY_HORIZONS` | `(1, 3, 6, 15, 24)` hours |

### Public Hourly Forecasting Signatures

```python
forecast_hourly_cashflows(
    history: Sequence[OrganizerHourlyObservation | HourlyCashFlowBucket],
    *,
    as_of: datetime,
    horizon_hours: int = 24,
    model_version: str = "hourly-seasonal-naive-v1",
    config: HourlyForecastConfig | None = None,
    start_at: datetime | None = None,
) -> HourlyForecastResult

hourly_rolling_mean_forecast(
    history: Sequence[Any],
    *,
    as_of: datetime,
    horizon_hours: int = 24,
    window_hours: int = 24,
    start_at: datetime | None = None,
    model_version: str = "hourly-rolling-mean-v1",
    uncertainty_multiplier: Decimal | float = Decimal("1.0"),
) -> HourlyForecastResult

hourly_seasonal_naive_forecast(
    history: Sequence[Any],
    *,
    as_of: datetime,
    horizon_hours: int = 24,
    season_hours: int = 24,
    start_at: datetime | None = None,
    model_version: str = "hourly-seasonal-naive-v1",
    uncertainty_multiplier: Decimal | float = Decimal("1.0"),
) -> HourlyForecastResult
```

### Baseline Behavior and Fallback Governance

1. **Separate Inflows and Outflows**: Deposits and withdrawals are forecasted separately. Predictions are strictly non-negative integer cents.
2. **Causality**: Strictly causal. No future data leakage. History timestamps must be strictly ordered and $\le \text{as\_of}$.
3. **No Synthetic Splitting**: Hourly observations are never split or interpolated into fabricated quarter-hour records.
4. **Horizons**: Explicitly supports 1-hour, 3-hour, 6-hour, 15-hour (overnight repo 17:00 to 08:00 next day), and 24-hour (daily cycle) horizons.
5. **Path Output**: Returns a complete ordered sequence of `HourlyForecastPoint` models, directly satisfying `FourTierRecommendationRequest.forecast`.
6. **Safe Short-History Fallback**:
   - If history is empty: returns 0-flow forecast path with 0 uncertainty.
   - If history has fewer observations than `season_hours` (e.g. < 24h): seasonal-naive automatically falls back to rolling mean over all available observations.

### Causal Hourly Feature Engineering

```python
extract_hourly_calendar_features(dt: datetime) -> dict[str, Any]
compute_hourly_lag_features(observations: Sequence[Any], lags=(1, 2, 3, 24, 168), fill_value=None) -> list[dict[str, Any]]
compute_hourly_rolling_features(observations: Sequence[Any], windows=(3, 6, 24, 168), strictly_prior=True) -> list[dict[str, Any]]
build_hourly_feature_matrix(observations: Sequence[Any], lags=(1, 2, 3, 24, 168), windows=(3, 6, 24, 168), strictly_prior=True) -> list[dict[str, Any]]
```

- **Calendar Features**: `hour_of_day` (0-23), `day_of_week` (0-6), `is_weekend` (0/1), cyclical `sin/cos` representations. Naive hourly datetimes only.
- **Lag Features**: Lags 1h, 2h, 3h, 24h (same hour on previous day), and 168h (same hour in previous week when available).
- **Rolling Features**: Rolling means and sample standard deviations (volatility) over 3h, 6h, 24h, and 168h windows. `strictly_prior=True` prevents same-step lookahead.

### Read-Only Organizer Dataset Loader

```python
load_organizer_dataset(source: str | Path | TextIO, *, limit: int | None = None) -> tuple[OrganizerHourlyObservation, ...]
```
Read-only adapter for organizer CSV rows. Preserves native Decimal scale and unspecified timezones. Does not duplicate or overwrite Member 2's loader.

## RJ-M1-08 Four-tier instrument economics

`treasury_intelligence.instrument_economics` adds pure calculations and immutable,
JSON-compatible result models, re-exported at the package root. All results carry
`calculation_only=true`; none books a trade, changes a portfolio, or records realized
accounting. Original functions/models remain unchanged. Decimal inputs reject
floats, booleans, and nonfinite numbers; time inputs retain the new unspecified
timezone semantics. Calculations use local Decimal precision, independent of the
caller's precision/rounding mode. Source percentage points are never converted to
integer bps. Source CSV and hourly observations remain unchanged.

### Rounding, quantities, and day count

- `usd_to_ledger_cents(amount_usd)` converts signed Decimal USD to integer cents
  using ROUND_HALF_UP (half away from zero).
- `percentage_cost_cents(amount_cents, percentage)` applies a percentage-point
  haircut to a nonnegative cent value and rounds upward. Market values are first
  rounded to ledger cents; their liquidation haircut is then rounded upward.
- `calculate_index_acquisition(budget_cents, acquisition_price_index, *,
  unit_decimal_places=18)` calculates normalized dollar-per-index-point units.
  Units round down to the declared precision (0–1000 decimal places). The returned
  IndexAcquisitionResult includes budget, price, units, exact Decimal acquisition
  notional, half-up cent cost basis, and remaining unallocated cents. Source price
  precision is preserved. Unit rounding is a stated modeling convention, not an
  exchange-lot specification. Fees require separate budgeting by Member 2.
- Repo/overdraft simple interest uses **ACT/365 fixed**: principal cents times
  annual percentage-point quote / 100 times actual elapsed microseconds /
  (365 * 86400 * 1,000,000). No compounding, no leap-year denominator adjustment,
  no per-hour rounding, and no yield-to-effective-rate conversion. Repo source
  APY is treated as the annual simple quote under this explicit convention.
  Repo income rounds half up once; financing costs round upward once per supplied
  constant-principal interval. Splitting a ledger accrual into separately rounded
  intervals can change its total; the accounting cadence belongs to Member 2.

### Repo

```python
repo_maturity_at(entered_at: datetime) -> datetime
rate_fixings_from_observations(observations, *, instrument="repo" | "overdraft")
    -> tuple[AnnualRateFixing, ...]
calculate_repo_economics(position: Tier1RepoPosition, *, as_of: datetime,
    rate_history: Sequence[AnnualRateFixing],
    pay_accrued_interest_on_early_break: bool = False) -> RepoEconomicsResult
```

Repo entry must be exactly 17:00; maturity is next-day 08:00 (15 hours). Accrual
stops at maturity. AnnualRateFixing holds observed_at and Decimal annual_rate_pct.
Fixings are effective from their timestamp to the next fixing (piecewise constant,
no interpolation). History must be strictly ordered/unique, cover the accrual
start when nonzero, and contain no fixing after as_of. The latest fixing at/before
entry seeds the rate; subsequent known fixings change it. A fixing exactly at the
interval end does not apply retroactively. The adapter copies actual organizer
repo/overdraft rate observations; it loads no data and invents no fixings. The
calculation uses supplied fixings, not the position's estimated_interest_cents or
an assumed immutable entry quote. Zero principal/duration needs no starting quote.

RepoEconomicsResult separates principal, accrued_interest_cents, gross_claim_cents,
interest_payable_on_redemption_cents, early_break_fee_cents,
net_redemption_proceeds_cents, immediately_redeemable, accessible_redemption_cents,
matured, holding_seconds, and maturity/as_of timestamps. Principal plus modeled
accrual is a claim, never checking cash. Before maturity, source early-break haircut
applies to principal; default 0.5% comes from the position contract. A locked position
without early_break_allowed has zero accessible proceeds even though a conditional
redemption quote is shown. At maturity, no early fee applies and claim redemption
is available; actual cash settlement still belongs to Member 2.

The dataset does not specify whether positive interest survives an early break.
Default behavior forfeits positive accrued interest; callers may explicitly enable
payment via pay_accrued_interest_on_early_break under the applicable contract.
Negative accrued interest is retained under either rule, not silently forgiven.
Rates/costs implying a negative claim or redemption proceeds raise ValueError.
For example $5M at 5% for 15 hours yields $428.08, rather than one day's $684.93.

### Bonds and equity

```python
calculate_bond_economics(index_units, acquisition_price_index, current_price_index,
    *, quoted_yield_pct, liquidation_haircut_pct=Decimal("2"),
    cost_basis_cents=None) -> MarketEconomicsResult
calculate_equity_economics(index_units, acquisition_price_index, current_price_index,
    *, annual_volatility_pct, emergency_sale=False, slippage_pct=Decimal("15"),
    cost_basis_cents=None) -> MarketEconomicsResult
calculate_duration_sensitivity(modified_duration_years, *, previous_yield_pct,
    current_yield_pct) -> DurationSensitivityResult
calculate_equity_risk(market_value_cents, gross_asset_value_cents, *,
    current_price_index, peak_price_index, annual_volatility_pct) -> EquityRiskResult
```

MarketEconomicsResult reports normalized units, acquisition/current indices,
Decimal acquisition_notional_usd and market_value_usd, cost_basis_cents,
market_value_cents, signed unrealized_pnl_cents, haircut/cost, net liquidation
proceeds, and signed realized_pnl_if_sold_cents. Default basis is the half-up
acquisition mark; an explicit actual allocated cost basis may include acquisition
fees. Member 2 supplies the appropriate units/basis for a partial lot. Actual
mark is units * current observed index, without adding quoted yield or expected
return. Unrealized P&L equals marked cents minus basis; conditional sale P&L equals
net proceeds minus basis. Conditional sale P&L is a pure calculation, not a claim a sale occurred.

Bond liquidation uses the supplied haircut, default 2%. YTM is preserved as quote
metadata only; no synthetic coupon is credited. Duration sensitivity returns the
separate approximation -Dmod * (current_yield_pct - previous_yield_pct) / 100,
both as a fraction and percentage-point price change. A 1-percentage-point yield
rise with duration 1.92 implies -1.92% hypothetical price sensitivity. It never
adjusts the observed-index mark a second time, and is not added as realized P&L.

Equity ordinary sale has zero modeled slippage unless emergency_sale=true;
emergency slippage defaults to the source 15%. Source volatility is preserved as
risk input, never converted to actual income. No expected 10% annual return is
assumed or added to observed price gains. Exposure is equity market value divided
by gross asset value (not debt-netted value); empty assets/exposure returns zero.
Drawdown is (known running peak - current) / peak. Peak must be positive and at
least current; the caller must supply a peak observed by the calculation cutoff.

### Emergency overdraft and portfolio summary

```python
calculate_overdraft_economics(principal_cents, *, start_at, end_at, rate_history,
    draw_cents=0, principal_repayment_cents=0, accrued_financing_cost_cents=0,
    paid_financing_cost_cents=0) -> OverdraftEconomicsResult
calculate_portfolio_values(portfolio: FourTierPortfolioState, *,
    repo_rate_history=(), pay_accrued_interest_on_early_break=False)
    -> PortfolioValueResult
```

Overdraft calculations explicitly place designated draws, principal repayments,
and prior-cost payments at interval start. Use separate constant-principal calls
for later changes; do not pretend a later repayment reduced earlier financing
cost. Financing APR must be nonnegative; known fixings must cover interval start
and must not extend past end_at (the calculation cutoff). For a decision at an
earlier time, do not supply future historical fixings; these are accrual calculations,
not a forecast of unknown rates. Existing unpaid costs do not earn interest.
Principal and financing-cost overpayments are rejected, never silently clipped.

OverdraftEconomicsResult separates closing_principal_cents,
unpaid_prior_financing_cost_cents, interval_financing_cost_cents,
outstanding_liability_cents, net_cash_change_cents, net_liability_change_cents,
and signed net_portfolio_value_effect_cents. A draw increases cash and principal
equally; its net-worth effect is zero before cost. Financing accrual decreases
net worth. Outstanding liability includes principal plus unpaid prior/new cost.
Credit-limit eligibility and actual payment booking belong to Member 2.

PortfolioValueResult reports immediately_available_cash_cents, fixed zero
cash_investment_yield_cents, repo_gross_claim_cents, bond_market_value_cents,
equity_market_value_cents, gross_asset_value_cents, potential_liquidation_proceeds_cents,
outstanding_liability_cents, signed net_portfolio_value_cents and net_liquidation_value_cents.
Only Tier 0 is checking cash. Gross assets sum cash, repo modeled claims, and
observed-index market marks exactly once. Potential liquidation includes permitted
repo proceeds plus bond/equity values after their source haircuts; it is not settled
cash. Overdraft is subtracted once as principal plus already accrued financing cost.
The summary does not accrue overdraft again; pass current liability observations.
Recorded realized costs and market losses are already reflected in the snapshot
and are not subtracted again. Member 2 must remove a repo from holdings when its
proceeds are booked to cash, and must preserve exclusive cash/position accounting.

## RJ-M1-10 Four-tier liquidity reserve and risk

### Canonical boundary and integration

`treasury_intelligence/portfolio.py` was copied selectively from reviewed commit
`1fcff80f05136a1d90faf8b88adacc8d313dc072`, without merging its branch or replacing
completed forecasting/economics. Git blob is unchanged:
`ed86bc45fae6421aa518c0cc10df3aa0e7dd142f`.
It supplies PortfolioState, FourTierTreasuryPolicy, HourlyForecastPoint, and
FourTierReserveResult. Their UUID/source/run/time-basis, valuation and liability
checks apply. New contracts/calculation live in `treasury_intelligence.liquidity_risk`:

```python
from treasury_intelligence.portfolio import (
    PortfolioState, FourTierTreasuryPolicy, HourlyForecastPoint,
)
from treasury_intelligence.liquidity_risk import (
    FourTierLiquidityRiskRequest, calculate_four_tier_liquidity_risk,
)

request = FourTierLiquidityRiskRequest.model_validate(payload)
result = calculate_four_tier_liquidity_risk(request)
assert result.reserve.time_basis == request.portfolio.time_basis
wire_json = result.model_dump_json()
```

The request/result/calculation are also package-root exports; the calculation is
available in `api.py`. Use module-qualified canonical input imports because old
root names such as HourlyForecastPoint and OverdraftLiability still belong to the
preserved old family. No model aliases, heuristic unit conversions, ML loading,
database changes, allocation optimizer, or payout execution is introduced.
Risk inputs include supplied separate deposit/withdrawal forecasts; generating
those forecasts remains the forecasting layer's responsibility.

### Request and timing

FourTierLiquidityRiskRequest contains canonical portfolio/policy/forecast,
planning_horizon_hours, uncertainty_mode, optional calibrated_allowance,
confidence (Decimal fraction), scenarios, repo_settlements, obligations,
liquidation_settlements, default_liquidation_delay_hours (default 1), optional
operational_buffer_cents, market_stress, available_overdraft_credit_cents, and
optional modeled_overdraft_apr_pct.

The path must cover the first hour beginning at portfolio.as_of, with contiguous
native hourly points. A longer path is truncated to the requested horizon;
insufficient coverage is rejected. No interpolation or assumed zero missing hour.
Legacy forecasters that start after the snapshot do not automatically satisfy this
coverage requirement; provide an explicit forecast covering the missing hour.
Clocks must match the portfolio: UNSPECIFIED naive historical or explicit UTC
synthetic. There is no timezone inference or future historical quote lookup.

Forecast withdrawals debit at each point's start; forecast deposits credit at the
hour's end. This conservative ordering resolves unspecified intrahour timing.
Payments and settlements at an exact shared timestamp net available credits before
debits. Cash is carried through the entire event path, so a late deposit/maturity/
sale cannot erase an earlier funding shortage. The independent
predicted_net_flow_cents/source-net field is retained and not overwritten; this
reserve's timing calculation explicitly uses separate deposits and withdrawals.
No claim is made that the legacy source-net forecast/evaluation mismatch is fixed.

RepoCashSettlement supplies time_basis, position_id, actual available_at,
amount_cents, and already_in_cash=false. Only explicitly attested contractual
settlements count; maturity alone does not credit cash. An unbooked settlement
must reference a current repo, arrive no earlier than its scheduled maturity or
snapshot time, and not exceed known principal plus already accrued interest.
Unknown future floating interest is excluded. Extra settlement delay is honored.
Only one settlement per repo is allowed. A booked settlement is excluded and must
be in the past/current time with that position removed from current holdings;
keeping both the cash and repo is rejected. Known settlements after the horizon
do not fund it.

CommittedObligation supplies time_basis, obligation_id, due_at, amount_cents, and
already_in_forecast=false. Add only explicit obligations; no fabricated schedules.
Duplicates and past-due input are rejected. Already-in-forecast obligations are
not added twice; matching forecast inclusion is a caller attestation because
forecast buckets carry no obligation/source IDs. Beyond-horizon obligations are
excluded. The same source-exclusivity rule applies to separately supplied repo
settlements versus forecast deposits: callers must not forecast the same cash
credit in both representations.

### Required cash reserve and uncertainty

Nominal peak = max(0, max over event times of cumulative withdrawals + explicit
obligations - deposits - contractually available repo settlements). Opening cash
is deliberately excluded from this required initial funding calculation. Compare
it with checking separately; risky assets and credit capacity do not lower it.

- `calibrated_allowance`: require a CalibratedForecastAllowance with explicit
  amount_cents, calibration_reference, calibrated_through <= as_of, confidence,
  and matching time_basis. Required reserve = nominal peak + supplied allowance +
  operational buffer. Calibration is a caller-supplied attestation, not measured
  or invented here. Request and allowance confidence must agree.
- `scenario_quantile`: require supplied weighted LiquidityScenarios and **forbid**
  a calibrated_allowance. Required reserve = inverse-CDF weighted quantile of
  scenario peaks + operational buffer. Scenario probabilities must sum exactly to
  one; no automatic renormalization. No Monte Carlo generator is implemented.
- Per-point provisional supplied_uncertainty_buffer_cents and legacy policy
  uncertainty multipliers are not added again in either mode. The explicit
  allowance/peak distribution is the complete uncertainty treatment for this API.
- Operational buffer defaults to policy.base_buffer_cents, with explicit override
  supported. Policy.minimum_liquid_reserve_cents is a floor. Floor top-up is
  reported separately and included in canonical reserve.base_buffer_cents so the
  canonical component-sum identity remains exact. In quantile mode the canonical
  reserve.net_drain_cents is the selected scenario peak; nominal peak is separate.

All cash arithmetic uses integer cents. Decimal fees/costs round upward; stressed
asset marks round downward before source haircuts, and scenario expected monetary
shortfalls round upward. No binary floating calculations or reserve rounding down.

### Stress liquidation and policy

MarketStress supports bond_method (price_drawdown OR yield_shock),
bond_drawdown_pct, bond_yield_change_pct (percentage points), equity_drawdown_pct,
and equity_volatility_multiplier. Bond risk starts from the supplied current
market value, never inferred quantity-times-index units. Price drawdown and
duration stress cannot be combined for the same bond. Yield stress is the
separate hypothetical loss fraction max(0, Dmod * yield_change_pct / 100), not a
second adjustment to actual historical mark-to-market. Loss stress is capped at
100%; favorable yield moves are not credited as guaranteed liquidity.

Equity loss fraction = explicit drawdown / 100 + multiplier * annual source
volatility / 100 * sqrt(horizon_hours / 8760), capped at 100%. This is a supplied
scenario/sensitivity convention, not a calibrated Gaussian probability model.
No expected equity return is added. After stress, the **source position's** bond
haircut or equity fire-sale slippage applies once to the stressed gross mark.
Existing liquidatable-value fields are not haircut again; they are not the mark.

StressLiquidationResult reports position/tier, arrival time, observed/stressed
value, modeled market loss, liquidation fee, net proceeds, permission, and reason.
Bond/equity liquidation requires explicit policy permission and LIQUIDATABLE
classification. Early repo break requires policy permission and position permission
explicitly true; unknown permission fails closed. It returns principal less known
negative accrual and the full source early-break haircut, excluding uncertain
positive interest. A fee exceeding available proceeds disqualifies a self-funded
break rather than silently reducing the fee. Once broken, that repo's future
maturity credit is removed from the after-liquidation path.

LiquidationSettlement provides an optional position-specific actual arrival
time; otherwise modeled arrival is as_of + default_liquidation_delay_hours.
Default 1 hour is a risk assumption, not a guaranteed settlement speed. Early
break candidates must arrive before repo maturity; normal maturity receipts use
the contractual settlement schedule exclusively. The engine models hypothetical
full permitted sales, not optimal amounts or executable recommended orders.
Such an assumed early-break plan can forfeit interest/pay fees; it is not promised
to dominate waiting for maturity. Potential proceeds are never added to current
cash or asset totals and are only credited to the projected path at arrival.

Current tier min/max allocation limits, existing overdraft policy limits, and
max_estimated_loss_cents are reported as violations. Market loss checks cover
nominal and worst supplied scenario stress. Permissions remain enforced even
when a shortage exists; a positive mark is not a risk-free cash balance.
The exposure checks describe current holdings. Hypothetical full-sale projections
are not a claim that every resulting allocation meets post-trade exposure bounds;
the allocation optimizer/executor must perform that plan-level feasibility check.

### Risk response, borrowing, and interpretation

FourTierLiquidityRiskResult contains the canonical reserve, as_of/end clock,
uncertainty mode/reference/confidence, nominal peak, configured buffer/floor top-up,
available cash, source-reported immediate and restricted liquidity, existing
liabilities, hypothetical liquidation quotes/proceeds/losses, pre/post-liquidation
funding shortages, scenario summaries/probabilities, borrowing consequences,
policy violations, full event paths, and calculation explanations.

Only portfolio.cash.balance_cents is initial checking. Source-reported restricted
and liquidatable categories can overlap; they are not partitions or extra assets.
Existing per-loan liabilities equal outstanding principal plus **unpaid** financing
cost; already paid costs are not deducted again. Outstanding overdraft is never
cash capacity or an asset. Optional newly available credit is constrained by the
explicit borrowing policy/remaining principal limit. It covers only the residual
modeled post-liquidation shortage and never reduces required reserve. Financing
cost uses ACT/365 fixed, ceiling cents, with supplied APR or the current quote
held constant over the full horizon as a conservative illustration. It is not
actual realized cost or an assertion future APR is known. Missing APR with a
positive modeled draw yields null cost, not a fabricated zero. Actual draw/
repayment timing, credit approval, and executions remain Member 2 responsibilities.

Definitions are intentionally distinct:

- funding_shortfall_before/after_liquidation_cents: maximum projected cash deficit
  at any event; they preserve interim timing even if ending cash becomes positive.
- reserve_breach: checking is below the reserve including buffers/floor. This
  can be true with no projected payout funding shortage at all.
- expected_unfunded_cash_cents: scenario-weighted mean of positive pre-liquidation
  peak funding deficits; not tail expected shortfall.
- tail_expected_shortfall_cents: mean deficit in the worst 1-confidence scenario
  mass, including fractional quantile-boundary mass; at confidence=1, worst loss.
- scenario_reserve_breach_probability: model weight of scenarios whose peak plus
  buffer/floor exceeds cash; do not add another calibration allowance to scenarios.
- scenario_funding_failure_probability_before/after: model weights of positive
  pre/post-liquidation deficits. Weights are supplied scenario-model probabilities,
  not empirically validated payout failure frequencies.
- Without supplied scenarios, probability/expected-shortfall fields are null and
  scenario_metrics_basis is not_estimated. Deterministic path shortages remain.
- actual_payout_failure is always null: this pure calculation observes/executes
  no payout. Projected funding-failure flags are not realized payout outcomes.

Every response is recommendation_only=true and NOT_EXECUTED. Forecasts, quotes,
calibrations, scenarios, portfolios, source CSV, databases and ledgers are not mutated.
No risky-asset expected return, paid fee, floating repo estimate, or matured cash
credit is counted as a second asset or realized income.

## RJ-M1-11 Deterministic constrained allocation optimizer

### Public interface and output

```python
from treasury_intelligence.optimizer import (
    AssetRewardAssumption, AllocationRewardModel,
    AllocationOptimizerRequest, AllocationOptimizerResult,
    recommend_four_tier_allocation,
)

request = AllocationOptimizerRequest.model_validate(payload)
result = recommend_four_tier_allocation(request)
canonical_plan = result.decision  # portfolio.FourTierDecisionResult
assert canonical_plan.execution_status == "NOT_EXECUTED"
```

New types/function are also package exports; `api.py` exports the function.
`portfolio.recommend_portfolio_allocation(request)` (also root/API export) now
recognizes AllocationOptimizerRequest and returns its canonical decision. The
older FourTierRecommendationRequest/legacy envelope does not contain reward or
quantity conventions and retains an explicit NotImplementedError rather than
receiving invented financial assumptions. Prior generic-vault APIs are unchanged.
Portfolio model fields are unchanged; only its recommendation dispatcher changed
since the byte-identical RJ-M1-10 import. Import canonical input models from
`treasury_intelligence.portfolio`, not the old root four_tier schema family.

AllocationOptimizerRequest contains request_id, the complete RJ-M1-10 `liquidity`
request, `rewards`, optional `supplied_reserve`, allocation_grid_bps (default
0/5000/10000), max_candidates (default 2048, maximum 10000), and
new_repo_settlement_delay_hours (default 0). Supplied reserve can only strengthen
the newly calculated minimum. Risk forecast must cover the reward horizon; USD
and explicit source/time-basis rules are retained.

AllocationOptimizerResult contains:

- summary_action: HOLD, INVEST, REBALANCE, LIQUIDATE, or WARNING;
- canonical decision: all four exact target fields, reserve, policy constraints,
  gross asset budget, separate debt target, identified typed orders, expected
  costs, instrument return estimates, stress loss and mathematical explanations;
- baseline `risk` response plus selected-plan projected_nominal_funding_gap_cents
  and projected_scenario_failure_weight (null without scenarios);
- full reward_assumptions, model_version, policy_version, assumption_reference,
  objective_cents, estimated income/price change, conditional forced-exit cost,
  modeled financing cost/savings, and immediate wealth loss;
- cash_available_at_decision_after_orders_cents (excludes later sale receipts),
  evaluated/feasible unique-plan counts, search_truncated and candidate assessments;
- recommendation_only=true and execution_status=NOT_EXECUTED.

Canonical action is ALLOCATE for any INVEST/REBALANCE/LIQUIDATE plan. WARNING has
LIQUIDITY_WARNING and no orders; HOLD has no orders. legacy_action_hint gives HOLD,
LIQUIDITY_WARNING, or SWEEP/WITHDRAW only for a single pure repo buy/redemption.
Multi-instrument plans have no generic-vault hint. No implicit UTC conversion,
execution adapter, DB mutation, trade fill, or realized P&L booking occurs.

### Explicit reward assumptions

AllocationRewardModel requires model/policy versions, assumption_reference,
assumptions_available_at <= as_of, holding_hours, and exactly one
AssetRewardAssumption for each investment tier. assumption_status defaults to
user_supplied; calibrated requires an actual supplied calibration_reference.
The engine does not create a calibration or fabricate evaluation metrics.
risk_aversion defaults to 1; equity_volatility_multiplier defaults to 2. Values
are finite precision-preserving Decimal, not binary floats.

Each asset assumption supplies horizon expected_income_pct and
expected_price_return_pct (default 0), stress_loss_pct, forced_liquidation_probability,
liquidation_haircut_pct, optional trade_fee_pct/fixed_trade_fee_cents, and the
quantity convention for market purchases. Income/price percentages are **over the
declared holding horizon**, not silently annualized or realized returns. Bonds
receive no coupon from quoted YTM. Equities receive no automatic 10% yield.

Repo expected income uses only current observed APY held constant as an explicit
modeling assumption: annual simple percentage points * actual remaining holding
hours / 8760, stopping at 08:00. New repo uses 15 hours, not 24. Future floating
fixings are not looked up or treated as known. Repo price-gain and manual income
assumptions must be zero. Past accrued/realized interest is not earned again.

Market purchases require positive `usd_per_index_point_per_unit`: USD per source
index point for one declared quantity unit. The organizer index alone does not
define an exchange lot; **Member 2 must supply/confirm this convention**.
New quantity = floor-to-declared-quantity-precision(gross budget USD / observed
index / convention). Purchase notional then rounds upward to cents within its
budget. Existing holdings use supplied current valuations, with partial-sale
quantities proportional to supplied quantity/value, not an imposed mark formula.
The executor must validate actual price/quantity/lot rules before fills.

### Objective and feasible candidates

For a common holding horizon, compare:

`expected income + expected price change - conditional forced-exit cost
 - expected financing cost - immediate wealth loss - risk_aversion * stress loss`.

Financing cost includes existing outstanding principal plus any new draw, less
explicit principal-repayment savings, using current quoted APR held constant and
ACT/365 fixed. Unpaid past interest is not compounded or deducted twice. Debt
repayment is a financing alternative, not investment yield. New borrowing is only
a cash-reserve/funding repair; a borrowing seed cannot buy investments.

Immediate wealth loss reconciles original gross assets + new borrowing - principal
repaid - target gross assets. It captures entry/sale costs and early-repo interest
forfeiture once. Transaction fees, source liquidation haircuts, repo break fees,
and modeled funding cost remain separately labeled. Positive early repo accrual
is conservatively forfeited; negative accrual remains payable. After maturity,
known accrued interest can enter redemption proceeds. Early break requires explicit
policy and position permission; a source-known future receipt cannot also be
redeemed again at/after its scheduled arrival.

Conditional exit cost = target asset value * supplied forced-liquidation
probability * applicable haircut. Existing source haircuts are conservative floors
for that estimate; they are never silently replaced by smaller assumptions.
This expected contingent cost is separate from fees on the proposed actual orders.
Stress utility is a separate risk penalty, not another booked market loss.
Stress loss uses the greater of declared asset stress, current/supplied-scenario
RJ-M1-10 stress, and an equity volatility floor. The floor is multiplier * current
annual volatility * sqrt(holding_hours / 8760); it is a sensitivity convention,
not a claimed calibrated Gaussian probability. New assets are stress-tested even
when there are no current positions in their tier. Observed bond marks are not
adjusted again by duration; duration is hypothetical forward stress only.

Mandatory cash is max(calculated reserve, supplied stronger reserve, policy cash
floor). New investment can spend only decision-time cash above that amount after
entry fees. Future maturities/late sales do not provide current buying power.
Repo entry requires open window, exactly 17:00 on the explicit portfolio clock,
current quote, and enough covered/reward horizon for next-day 08:00 maturity plus
declared settlement delay. Only principal is projected back into cash, not
uncertain future interest. Breaking an existing repo removes the corresponding
share of its known maturity receipt from the projected cash path.

New bond/equity purchases require **explicit tier exposure caps**, not just the
generic vault maximum. Caps/bounds apply to target assets divided by post-trade,
post-fee gross assets, with debt separate. Missing other tier caps use the legacy
max_allocation_bps ceiling (Tier 0 defaults to 100%); the returned effective policy
discloses these bounds. Fees shrinking the denominator are included in purchase-cap
calculations. Market liquidation requires its policy permission and LIQUIDATABLE
classification; source haircuts apply once. Selling can repair a reserve shortfall
or current concentration breach, but cannot create positive current cash before
its explicit settlement. Orders settling beyond forecast coverage are rejected.

Every candidate is checked for target reserve, nonnegative amounts, post-fee
exposures, debt limit, stress-loss limit, nominal intrahorizon payout funding,
and weighted scenario funding-failure mass <= 1-confidence. Scenario checks use
provided forecasts/weights, not future historical prices. Delayed liquidation may
repair a buffer later only if interim payouts remain fundable; the response
separates current cash from the pro-forma target. Borrowing may repair the gap only
with explicit capacity/permission and known financing quote. Available credit is
not an existing asset and never finances new investment in this search.

### Deterministic P0 search and limitations

Candidate seeds include HOLD, individual/full permitted sales, a minimal-sale
cash-reserve repair, a minimal-sale concentration repair, debt repayment, and
permitted emergency funding. Each seed is compared with a bounded allocation grid,
per-tier cap endpoints, and minimum allocations. Exact-cent binary searches account
for grossing up fees and quantity steps. Orders are returned in settlement-aware
plan order (sales/financing before immediate purchases); execution still requires
confirmed fills and Member 2 revalidation. UUID5 order IDs derive deterministically
from run/time/request/plan facts. Input objects and record identities are not mutated.

Highest objective wins; ties prefer fewer orders, then a deterministic conservative
allocation ordering. Necessary safety repairs can have negative expected economic
benefit while HOLD is infeasible. If no generated plan is feasible, return WARNING
without executable orders, not an invented allocation. Search truncation and
candidate failure reasons are disclosed. This is a real constrained finite search,
not a global-optimality certificate or an exhaustive optimizer over all positions.

Targets are trade-only pro-forma assets, before exogenous banking cash flows and
automatic maturity accounting; they are not predicted end-of-horizon portfolio
wealth. Baseline risk remains separately identified; selected-plan funding checks
and target stress are reported alongside it. Expected monetary benefits are
conservatively displayed with downward cent rounding; costs/stress round upward.
The Decimal objective retains precision for ranking. All forecasts, rate/price
quotes, return assumptions, source data, current holdings and accounting remain
unchanged. No execution, realized outcome, or ML model training occurs here.

## RJ-M1-09 Hourly ML forecasting and chronological evaluation

`treasury_intelligence.ml_forecasting` provides native machine learning cash flow forecasting
and rigorous chronological evaluation against the organizer's hourly historical data, fully integrated
with the `HourlyForecastResult` contract.

### ML Forecasting Contracts and Public API

```python
HourlyCashFlowMLModel(
    algorithm: Literal["hist_gradient_boosting", "random_forest"] = "hist_gradient_boosting",
    random_state: int = 42,
    uncertainty_multiplier: Decimal = Decimal("1.0"),
    **estimator_kwargs: Any,
)
```

- **Algorithms**: Lightweight Scikit-Learn `HistGradientBoostingRegressor` (default) and `RandomForestRegressor`.
- **Zero Eager Overhead**: Scikit-Learn regressors and metrics are imported lazily inside model execution; importing `treasury_intelligence` does not trigger ML dependencies.
- **Model Methods**:
  - `fit(observations: Sequence[Any]) -> HourlyCashFlowMLModel`: Trains independent deposit and withdrawal estimators.
  - `predict_path(history: Sequence[Any], *, as_of: datetime, horizon_hours: int, model_version: str = "hourly-hist-gb-v1") -> HourlyForecastResult`: Generates causal multi-step forecasts with non-negative clipping.
  - `to_bytes() -> bytes` / `from_bytes(data: bytes) -> HourlyCashFlowMLModel`: Binary serialization.
  - `save(path: str | Path) -> Path` / `load(path: str | Path) -> HourlyCashFlowMLModel`: Disk persistence.

### Unified Hourly Dispatch

```python
hourly_ml_forecast(
    history: Sequence[Any],
    *,
    as_of: datetime,
    horizon_hours: int = 24,
    ml_model: HourlyCashFlowMLModel | None = None,
    model_version: str | None = None,
    fallback_to_baseline: bool = True,
) -> HourlyForecastResult

forecast_hourly_cashflows(
    history: Sequence[Any],
    *,
    as_of: datetime,
    horizon_hours: int = 24,
    config: HourlyForecastConfig | None = None,
    ml_model: Any = None,
) -> HourlyForecastResult
```

- When `ml_model` is supplied, `forecast_hourly_cashflows` delegates to `hourly_ml_forecast`.
- If `ml_model` is None or untrained, it safely falls back to `hourly_seasonal_naive_forecast` or `hourly_rolling_mean_forecast`.
- Multi-step horizons: 1h, 3h, 6h, 15h (overnight repo 17:00-08:00), and 24h (daily cycle). Intermediate lag steps are generated causally without peeking into future observations.

### Chronological Evaluation and Metrics Report

```python
evaluate_hourly_forecast_models(
    history: Sequence[Any],
    *,
    horizons: Sequence[int] = (1, 3, 6, 15, 24),
    train_ratio: float = 0.70,
    val_ratio: float = 0.15,
    eval_stride: int = 12,
    algorithms: Sequence[str] = ("hist_gradient_boosting",),
    random_state: int = 42,
) -> tuple[HourlyModelEvaluationReport, ...]
```

`HourlyModelEvaluationReport` fields (USD errors rounded to cents after numerical model evaluation, serialized as Decimal strings):
- `algorithm`: Machine learning algorithm evaluated (`"hist_gradient_boosting"` or `"random_forest"`).
- `horizon_hours`: Multi-hour forecast path length ($H \in \{1, 3, 6, 15, 24\}$).
- `train_cutoff`, `test_start`, `test_end`: Strict chronological evaluation window boundaries.
- `train_sample_count`: training feature/target pairs; `test_sample_count`: evaluated rolling paths (horizons can overlap).
- `mae_deposits_usd`: Pointwise deposit MAE (no deposit RMSE field).
- `mae_withdrawals_usd`: Pointwise withdrawal MAE (no withdrawal RMSE field).
- `mae_net_usd`, `rmse_net_usd`: Pointwise net cash flow error ($\text{net} = \text{deposits} - \text{withdrawals}$).
- `cumulative_net_mae_usd`: Cumulative net flow forecast error over the entire $H$-hour path.
- `peak_shortfall_mae_usd`: Maximum cumulative liquidity shortfall prediction error.
- `baseline_mae_net_usd`, `baseline_rmse_net_usd`: Comparative seasonal-naive baseline errors.
- `net_mae_improvement_pct`, `net_rmse_improvement_pct`: Measured improvement percentages without manual inflation.

## RJ-M1-12 Multi-Asset Monte Carlo Risk Simulation

`treasury_intelligence.monte_carlo_risk` models the joint uncertainty of cash flows, bond prices,
and equity returns using historical block bootstrap sampling, connecting directly with
`FourTierLiquidityRiskRequest` and `calculate_four_tier_liquidity_risk`.

### Public Signatures and Contracts

```python
from treasury_intelligence.monte_carlo_risk import (
    generate_multi_asset_scenarios,
    simulate_multi_asset_monte_carlo_risk,
    MultiAssetMonteCarloRiskResult,
    PercentileSummary,
    MarketRiskSummary,
    ShortfallDistributionSummary,
    PortfolioDownsideRiskSummary,
    MONTE_CARLO_RISK_MODEL_VERSION,
)

scenarios = generate_multi_asset_scenarios(
    history: Sequence[OrganizerHourlyObservation],
    nominal_forecast: Sequence[HourlyForecastPoint],
    *,
    as_of: datetime,
    planning_horizon_hours: int = 24,
    scenario_count: int = 500,
    seed: int = 42,
    time_basis: Literal["UNSPECIFIED", "UTC"] = "UNSPECIFIED",
) -> tuple[LiquidityScenario, ...]

result = simulate_multi_asset_monte_carlo_risk(
    portfolio: PortfolioState,
    history: Sequence[OrganizerHourlyObservation],
    nominal_forecast: Sequence[HourlyForecastPoint],
    policy: FourTierTreasuryPolicy,
    *,
    planning_horizon_hours: int = 24,
    scenario_count: int = 500,
    seed: int = 42,
    confidence: Decimal = Decimal("0.95"),
    repo_settlements: Sequence[RepoCashSettlement] = (),
    obligations: Sequence[CommittedObligation] = (),
    available_overdraft_credit_cents: int = 0,
    operational_buffer_cents: int | None = None,
) -> MultiAssetMonteCarloRiskResult
```

### Statistical Methodology and Joint Innovations

1. **Strictly Causal Block Bootstrap**: Samples contiguous historical blocks of length $H$ from observations $t \le \text{as\_of}$. Future observations are completely hidden from the sampler.
2. **Forecast Residuals**: Cash-flow uncertainty is modeled using 24-hour seasonal forecast residuals. Residuals are added to nominal predictions and clipped to $\ge 0$ (`sim_deposits >= 0`, `sim_withdrawals >= 0`).
3. **Contemporaneous Market Drawdowns**: Captures joint contemporaneous bond price index and equity index drawdowns within each sampled historical block, preserving empirical correlations without imposing artificial Gaussian copula assumptions.
4. **Observed Equity Volatility**: Uses observed `tier3_stock_volatility_pct` rather than claiming non-existent time-varying volatility dynamics.
5. **Repo Maturity Schedule**: 15-hour overnight repo entered at 17:00 matures at 08:00 next day; cash is not available earlier unless broken early.
6. **Pathwise Revaluation & Forced Costs**: Revalues ending portfolio cash, held positions, debt liabilities, forced liquidation haircuts, and overdraft financing costs along each path.
7. **Percentiles & Outputs**: Produces P90, P95, and P99 percentiles for peak cash requirements, shortfalls, market losses, portfolio value, and downside losses. All scenario probabilities sum exactly to `Decimal("1")`.
8. **Disclosed Confidence**: Notes explicitly state that scenario probabilities are empirical relative frequencies, avoiding claims of guaranteed real-world confidence intervals.

## RJ-M1-13 Official Four-Tier Engine Demo Pipeline

Executable standalone demonstration module: `treasury_intelligence.four_tier_demo`
(CLI: `python -m treasury_intelligence.four_tier_demo`).

```python
from treasury_intelligence import (
    run_four_tier_demo,
    run_scenario_repo_sweep,
    run_scenario_repo_unavailable,
    run_scenario_liquidity_shortage,
    run_scenario_market_decline,
    FourTierDemoSuiteResult,
    FourTierDemoScenarioResult,
    build_demo_portfolio_state,
    load_demo_observations,
    resolve_organizer_dataset_path,
)

suite_result: FourTierDemoSuiteResult = run_four_tier_demo(
    source_path=None,   # Autoresolves CSV or test fixture
    limit=200,          # Observations evaluated
    seed=42,            # Deterministic PRNG seed
)
```

### Core Pipeline Architecture

```
Organizer Hourly CSV (16 columns)
       │
       ▼
load_demo_observations() ──────────► Causal History Filter (t <= as_of)
                                              │
       ┌──────────────────────────────────────┴──────────────────────────────────────┐
       ▼                                                                             ▼
forecast_hourly_cashflows()                                              build_demo_portfolio_state()
(15h horizon, deposits & withdrawals)                                    (Cash, Repos, Bonds, Equities, Overdraft)
       │                                                                             │
       └──────────────────────────────────────┬──────────────────────────────────────┘
                                              ▼
                             simulate_multi_asset_monte_carlo_risk()
                             (Block bootstrap joint stress: cash flow, bond, equity)
                                              │
                                              ▼
                             recommend_four_tier_allocation()
                             (Deterministic candidate search under reserve, exposure, and loss limits)
                                              │
                                              ▼
                             FourTierDemoScenarioResult & FourTierDemoSuiteResult
                             (Typed recommendations, orders, economics, JSON serializable)
```

### Demonstrated Engine States

1. **Scenario 1 — Allowed Overnight Repo Sweep (17:00 Entry)**:
   - Evaluated at 17:00 when `repo_sweep_window_open == True` and quoted floating APY is 4.272%.
   - Required reserve of $142,563,501.06 is strictly protected in Tier 0 Cash.
   - Surplus cash of $257,436,498.94 is allocated to `INVEST_REPO`.
   - Order schedule: settles at 17:00, matures next day at 08:00 (15 hours).
   - Accrues positive overnight income ($18,831.65). Status is `NOT_EXECUTED` (`recommendation_only=True`).

2. **Scenario 2 — Repo Unavailable (Outside 17:00 Window)**:
   - Evaluated at 10:00 business hours when `repo_sweep_window_open == False`.
   - Engine enforces policy constraint: Repo candidates are strictly rejected outside the 17:00 window.
   - Output: `summary_action="HOLD"`, 0 repo orders. Capital is safely held in operational cash.

3. **Scenario 3 — Stressed Liquidity Shortage**:
   - Evaluated under low cash ($5M) and heavy projected net drain ($141.56M).
   - Mandatory required reserve exceeds available immediate cash by $137.56M.
   - Engine rejects all investment candidates; issues `LIQUIDITY_WARNING` (`feasible=False`).
   - Zero speculative investments proposed; full calculation audit trail generated.

4. **Scenario 4 — Market Decline Revaluation**:
   - Portfolio holding bonds and equities undergoes adverse market shock (-2% bond index, -10% equity index).
   - Net portfolio value drops dollar-for-dollar by -$1,197,712.00.
   - Stressed liquidation proceeds under haircuts (2% bond, 15% equity) drop to $67,193,946.82.
   - Confirms mark-to-market accuracy and strict prohibition of guaranteed equity return.


## RJ-M1-14 Final release contract clarification

The canonical portfolio, order, reserve and allocation schemas are explicitly
imported from `treasury_intelligence.portfolio`; recommendation implementation is
`optimizer.recommend_four_tier_allocation(AllocationOptimizerRequest)`.
Older `four_tier.py` contracts and legacy UTC vault APIs remain supported; root
aliases are mixed for compatibility. Do not interchange model families implicitly.
The older envelope-only recommendation function still refuses to invent missing
reward/unit assumptions. See MEMBER2_INTEGRATION.md for the working boundary.

Hourly forecast outputs still describe `deposits_minus_withdrawals`, not the
independent source net_flow_usd. Copy point fields explicitly into canonical hourly
points and preserve actual target metadata separately. Canonical metadata's
source-net-only restriction is a known unresolved integration boundary. Historical
hours remain timezone-unspecified; publication/availability semantics are external.
Missing hours are rejected rather than silently interpreted as contiguous lags.
Explicit seasonal start times now align to target timestamps; if no historical
seasonal match exists, the baseline uses the last known observation.

ML artifact training_cutoff now includes validation observations used for residual
calibration, survives serialization, and must not exceed inference as_of. Training
and evaluation remain chronological. Error metrics use numerical estimates rounded
to cent-valued Decimal strings, not arbitrary-precision ML. Net error is derived-net
error; peak-shortfall evaluation is hour-end netting, not realized payout failure.
Actual results are in MODEL_EVALUATION_REPORT.md and RELEASE_RESULTS.json.

Monte Carlo model `multi-asset-block-mc-v1.1` fixes asset conservation and endpoint
cash accounting. Endpoint cash equals opening cash plus simulated deposits minus
withdrawals/extra obligations plus eligible repo receipts and hypothetical sale
proceeds plus new borrowing. Sold assets and settled repo claims are removed from
remaining asset value once. Opening liabilities plus new principal and incremental
financing are subtracted; borrowing principal cancels its cash receipt in NAV.
Old booked financing is not charged twice. Full permitted hypothetical sales are
stress analysis, not execution or optimizer-selected trades. Only settlements by
horizon end count. Negative endpoint cash indicates an unfunded obligation.

Scenario weights have an exact finite-decimal unit sum (last weight is the residual
for repeating fractions). All hourly market innovations, including the first
sampled change, enter adverse block price stress. Per-position loss rounding is
consistent with the liquidity engine; summary monetary means use Decimal half-up.
Percentile NAV is the adverse lower-tail counterpart of loss percentile rank.
Current source APR or the latest available history APR supplies new borrowing cost;
there is no invented 12% fallback. Existing principal also incurs its contractual
APR over the modeled horizon. Full-horizon financing is conservative, not execution
accounting. Neither bond YTM nor equity expected return is realized cash income.

Scenario-quantile reserve already incorporates uncertainty: net_drain_cents holds
the selected scenario peak requirement and uncertainty_buffer_cents is zero.
Operational buffer/floor is separate. Bootstrap weights are model probabilities,
not measured real-world failure rates or guaranteed confidence coverage. Portfolio
downside includes operational flows and hypothetical fees; market-only loss is a
separate metric. No database, trading or frontend behavior is added by this audit.

FINAL_AUDIT.md records release findings, limitations and standalone instructions;
TESTING_REPORT.md records complete verification, and the two integration handoffs
supersede conflicting older field examples for canonical consumers.
