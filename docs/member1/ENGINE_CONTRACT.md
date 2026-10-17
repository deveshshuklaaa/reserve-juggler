# Quantitative engine contract v1

Package: `treasury_intelligence`. Requires Python 3.10+ and Pydantic 2
(`treasury_intelligence/requirements.txt`). No database, HTTP, or frontend imports.
RJ-M1-01 defines validated immutable models and public function declarations only.
All six functions currently raise `NotImplementedError`; no financial algorithm or
execution path is implemented. Existing forecasting and backend classes are unchanged.

The referenced Member 1 prompt signatures, MEMBER1_SCOPE.md, and AGENT_RULES.md
were absent when this contract was written. These are new standalone signatures,
not replacements for the existing float-based backend interfaces. Any later adapter
must explicitly convert currency units and supply UTC timestamps.

## Units and serialization

All `_cents` fields are nonnegative strict integers in the context's single currency;
floats, strings, and booleans are rejected. Net drain means max(outflow - inflow, 0).
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
