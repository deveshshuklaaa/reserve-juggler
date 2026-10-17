# Quantitative engine contract v1

Package: `treasury_intelligence`. Requires Python 3.10+ and Pydantic 2
(`treasury_intelligence/requirements.txt`). No database, HTTP, or frontend imports.
RJ-M1-01 defined validated immutable models and public function declarations.
RJ-M1-02 implements `calculate_required_reserve` and the pure helpers below.
The other five original functions still raise `NotImplementedError`.
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
