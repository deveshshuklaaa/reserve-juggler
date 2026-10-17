# Quantitative engine contracts: legacy v1 and four-tier v1

RJ-M1-06 adds the authoritative organizer four-tier contracts in
`treasury_intelligence.portfolio`; see the section at the end and
[Member 2 field mapping](FOUR_TIER_HANDOFF.md). All earlier sections below describe
the preserved **legacy generic-vault v1 pipeline only**. Its UTC, integer-rate-bps
and forecasting defaults must not be imposed on the organizer's hourly data.

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

## RJ-M1-06 — Authoritative organizer four-tier contracts

The canonical definitions are `treasury_intelligence/portfolio.py`, exported from
`treasury_intelligence`. There was no existing four-tier wire model on the Member 1
branch at `c35da91`. The types were reconciled with Member 2's already committed
four-tier storage at `52e58bc`, not independently redesigned. ORM storage models
remain Member 2-owned; no ORM, database, HTTP or frontend imports are required.

| Contract | Purpose |
| --- | --- |
| `PortfolioSource` | Run ID, source type, dataset ID, observation timestamp and explicit time basis |
| `PositionLiquidity` | Immediate, locked, liquidatable or unavailable classification; separate available/locked/liquidatable amounts |
| `CashPosition` | Tier 0 identity, cash balance, latest ledger reference, 0% APY and full immediate liquidity |
| `RepoPosition` | Tier 1 principal, entry/maturity, supplied APY, status, redemption haircut/cost, accrued/realized interest and proceeds |
| `BondPosition` | Tier 2 quantity, acquisition/current price indices, market value, supplied yield, modified duration, signed P&L and liquidation costs |
| `EquityPosition` | Tier 3 quantity, acquisition/current indices, market value, volatility, signed P&L and slippage; no guaranteed-interest fields |
| `TreasuryPosition` | Discriminated union keyed by integer tier 0/1/2/3 |
| `OverdraftLiability` | Separate borrowing/outstanding/repaid principal, APR, financing cost and breach reference |
| `PortfolioValuation` | Separate four-tier assets, repo principal/value, liquidity, restrictions, liabilities and signed net value |
| `PortfolioState` | One current, consistently valued snapshot with typed instrument collections and liabilities |
| `PortfolioTreasuryContext` | Alias of `PortfolioState`, not a second definition |
| `FourTierTreasuryPolicy` | Reuses legacy buffer/limit units; adds explicit repo window, liquidation permissions and per-tier caps |
| `FourTierReserveResult` | Reuses `ReserveResult` fields and component identity; explicit timestamp basis replaces blanket UTC |
| `RecommendedOrder` | Typed instrument recommendation with caller-assigned ID, amount, optional quantity/cost/proceeds estimates and explanation |
| `FourTierDecisionResult` | HOLD, ALLOCATE or LIQUIDITY_WARNING; ordered multi-instrument recommendations and supplied reserve |

### Units, identity and time

- Every money amount named `_cents` is a strict integer, rejecting floats, booleans
  and numeric strings. Signed P&L, interest and net value are permitted; other cash,
  asset, cost and principal amounts are nonnegative.
- Market quantities, rates, indices and duration use finite `Decimal`. Python
  accepts Decimal, decimal strings or integers; JSON uses decimal **strings** to
  preserve precision. Binary floats, NaN and infinities are rejected. There is no
  rounding or conversion to integer bps. `4.308` in `applicable_apy_pct` means
  **4.308%**, matching the organizer CSV and Member 2's NUMERIC columns.
- Percentage haircuts remain supplied Decimal percentages: organizer values are
  0.5% repo, 2% bonds, 15% equities. They are required inputs, not silently substituted
  defaults. Floating yields may be negative. Equity volatility is a risk input,
  not a guaranteed return. Policy allocation caps/multipliers retain integer bps.
- Position, liability, run and order identities use UUIDs compatible with Member 2.
  IDs and record order are caller-supplied: no random defaults or implicit sorting.
- Historical source type `ORGANIZER_HISTORICAL` requires dataset identity, naive
  source timestamp and `time_basis="UNSPECIFIED"`. All event/valuation timestamps
  on the same record preserve that basis. No timezone is guessed or attached.
  Synthetic source type `SYNTHETIC` requires explicitly aware UTC timestamps,
  `time_basis="UTC"` and no organizer observation reference.
- Historical snapshots require `native_interval_seconds=3600`. The original
  dataset's 8,760 hourly observations and supplied `net_flow_usd` remain authoritative;
  this migration neither ingests/recomputes cash flows nor creates 15-minute rows.
  `CashFlowBucket`/`ForecastResult` remain legacy UTC contracts; converting the
  organizer source into them is **not** an approved adapter.

### Snapshot and recommendation semantics

`PortfolioState` is the only four-tier context. It contains current unsettled repo
and open market positions; closed/redeemed records belong to history. Snapshot
validation checks identity/source isolation, no future observations/acquisitions,
current valuation completeness, tier totals, liquidity totals and minimum liability
coverage. A maturity date is not a cash credit. Repo entry and maturity are explicit:
17:00 to 08:00 next morning is a 15-hour representation, not a generic 24-hour vault.
The schema checks ordering, not holiday calendars or automatic schedule execution.

Portfolio gross assets are not available cash. Net value deducts liabilities and
can be negative. Liquidatable value includes immediately available cash plus
supplied potential net liquidation proceeds; it is **not additional cash** to add
to available liquidity. Locked value can overlap liquidatable value (e.g. early
break of repo). No partition identity between those liquidity categories is assumed.
Snapshot validation reconciles supplied values; it never computes prices, returns,
accrual, fees, trading decisions or accounting postings.

`RecommendedOrder` supports INVEST_REPO, REDEEM_REPO, BUY_BONDS, SELL_BONDS,
BUY_EQUITIES, SELL_EQUITIES, BORROW_OVERDRAFT and REPAY_OVERDRAFT. Action/tier must
agree; selling/redemption/repayment must identify the existing position/liability.
Buy/invest orders can omit position ID until the executor assigns the new position.
Market quantity is optional and only valid for bonds/equities. `amount_cents` is
the requested gross investment/redemption/market notional or borrowing/repayment
principal; `estimated_cost_cents` is separate, and `expected_proceeds_cents` is an
optional modeled net inflow, never a confirmed fill or realized income. A future
executor must validate quantity/notional consistency against actual prices.

`recommendation_only` is always boolean true. ALLOCATE requires one or more uniquely
identified orders. HOLD and LIQUIDITY_WARNING require no orders. Orders and reserves
must share the decision's time; sources/runs must agree. No execution-status or
ledger mutation is implied. The caller must revalidate balances, reserve coverage,
eligibility, settlement, costs and permissions before execution. This task adds no
four-tier recommendation function or forecasting algorithm.

### Compatibility decisions

Legacy `TreasuryContext`, `VaultPosition`, `TreasuryPolicy`, `ReserveResult`,
`DecisionResult`, `EvaluationResult`, `RiskScenarioResult` and `OptimizationResult`
were inspected. Their fields and six public algorithm signatures are preserved.
Only the old context/vault docstrings now explicitly identify them as legacy.
The completed RJ-M1-05 pipeline continues to consume v1 inputs and return v1
results. The new context is not flattened into `vaults`, and new order plans are
not reduced to the legacy single-vault SWEEP/WITHDRAW result. Model evaluation,
risk scenarios and optimization declarations remain deferred and do not acquire
invented four-tier execution behavior.

All new models are frozen, forbid unknown fields, and serialize with the existing
Pydantic API. Nested collections are tuples (JSON arrays). Read
`tests/treasury_intelligence/fixtures/four_tier_portfolio.json` as a **constructed
contract example**, not an assertion of actual organizer market values or trades.
JSON schemas are available with `model_json_schema()` and
`TypeAdapter(TreasuryPosition).json_schema()`; no OpenAPI change is included.
