# Four-tier Member 1 release handoff - RJ-M1-15

Readiness: **BLOCKED for an unqualified single-contract integration release**.
Canonical imports and the example below work without ML/database/frontend packages.
No engine redesign or runtime changes were made in RJ-M1-15. The remaining contract
boundary must be explicitly handled by Member 2 or reconciled in a separately
assigned task; completed compatibility functionality has been preserved.

## Member 2: exact imports and execution boundary

```python
from treasury_intelligence.portfolio import (
    PortfolioState, CashPosition, RepoPosition, BondPosition, EquityPosition,
    OverdraftLiability, PortfolioValuation, PositionLiquidity,
    MarketRateObservation, MarketPriceObservation, OrganizerHourlyObservation,
    FourTierTreasuryPolicy, HourlyForecastPoint, RecommendedOrder,
    FourTierReserveResult, FourTierDecisionResult, TierAllocationLimit,
    recommend_portfolio_allocation,
)
from treasury_intelligence.hourly_forecasting import forecast_hourly_cashflows, HourlyForecastConfig
from treasury_intelligence.liquidity_risk import (
    FourTierLiquidityRiskRequest, calculate_four_tier_liquidity_risk,
    RepoCashSettlement, CommittedObligation, LiquidityScenario,
)
from treasury_intelligence.monte_carlo_risk import simulate_multi_asset_monte_carlo_risk
from treasury_intelligence.optimizer import (
    AllocationOptimizerRequest, AllocationOptimizerResult, AllocationRewardModel,
    AssetRewardAssumption, recommend_four_tier_allocation,
)
```

Canonical contract: treasury_intelligence/portfolio.py. Reserve/risk implementation:
liquidity_risk.py. Multi-asset simulation: monte_carlo_risk.py. Allocation:
optimizer.py. Do not use root-level overlapping model names: some still refer to
four_tier.py compatibility contracts, not the canonical schemas above.

Recommended flow: validate current canonical portfolio and policy; generate a
causal forecast; explicitly convert forecast points; supply calibrated allowance
OR weighted scenarios; calculate reserve/risk; supply explicit rewards; call
recommend_four_tier_allocation. Consume result.decision. The portfolio dispatcher
also accepts AllocationOptimizerRequest at runtime and returns only its decision;
its legacy signature annotation still names FourTierRecommendationRequest. That
older envelope raises NotImplementedError because it lacks reward/unit assumptions.

Forecast point conversion is explicit:

```python
points = tuple(HourlyForecastPoint(
    time_basis=portfolio.time_basis, **point.model_dump()
) for point in forecast.points)
```

Preserve forecast.metadata separately. Its net_flow_target is
"deposits_minus_withdrawals"; canonical ForecastRiskMetadata permits only
"source_net_flow_usd". Do not relabel or coerce this mismatch. Source net_flow_usd
remains an independent source field. Historical timestamps are naive/UNSPECIFIED,
not UTC. The risk path begins at portfolio.as_of, with withdrawals at hour start
and deposits at hour end. Specify start_at explicitly and supply only observations
known at decision time; row publication timing is not defined by the dataset.

## Full JSON example and verified consumer

Input: docs/member1/integration_request.json.
Output: docs/member1/integration_response.json.
These are full typed JSON documents, not excerpts. Current source quotes and a
15-hour seasonal forecast come from the checked-in real hourly fixture; $400M
starting cash, reward/policy settings and a single nominal scenario are illustrative.
This example demonstrates wire compatibility, not calibrated risk coverage or
strategy performance. Production must supply appropriate scenarios/calibration.

Run from repository root with only the declared core dependency:

```powershell
$env:PYTHONPATH='.'
uv run --with pydantic python -c "from pathlib import Path; from treasury_intelligence.optimizer import AllocationOptimizerRequest, AllocationOptimizerResult, recommend_four_tier_allocation; q=AllocationOptimizerRequest.model_validate_json(Path('docs/member1/integration_request.json').read_text()); r=recommend_four_tier_allocation(q); expected=AllocationOptimizerResult.model_validate_json(Path('docs/member1/integration_response.json').read_text()); assert r==expected; assert r.model_validate_json(r.model_dump_json())==r; print(r.summary_action, r.execution_status)"
```

For actual use, replace the request's portfolio, policy, forecast/scenarios and
rewards with current Member 2 state. Validate using model_validate_json or
model_validate; serialize with model_dump_json or model_dump(mode="json"). Cash
ledger fields are integer cents. Supply precise prices/percentages as Decimal or
JSON decimal strings, never float. Validate source identifiers, all valuation
identities and settlement receipts. Never book a recommendation as an execution.

All orders remain recommendation_only=true and execution_status=NOT_EXECUTED.
Member 2 must revalidate balances, prices, quantities, fees, caps, locks and order
settlement; execute and persist receipts separately. Future repo receipts are not
current cash; do not include receipts in both deposits and repo_settlements. Debt
principal and unpaid financing are liabilities, not existing liquid assets.

## Files and dependencies

Member 2 needs the entire treasury_intelligence package plus
requirements.txt (pydantic>=2.0.0,<3); copying portfolio.py alone omits dependencies.
No ORM/FastAPI/frontend is needed for canonical recommendations. Optional ML fit,
predict and evaluation require scikit-learn, which is not in core requirements;
RJ-M1-14 measured pydantic 2.13.4 / scikit-learn 1.9.0. Install separately or use
`uv run --with pydantic --with scikit-learn ...`. Pytest is a test dependency.
Read ENGINE_CONTRACT.md, MEMBER2_INTEGRATION.md and FINAL_AUDIT.md. Example inputs
and outputs above are the current canonical recommendation sample; the older
four_tier_request/response fixtures are compatibility schemas. The existing
canonical_liquidity_portfolio.json fixture illustrates all four assets and debt.

Member 3 needs MEMBER3_FRONTEND_FIELDS.md and the canonical output sample. Display:
summary_action; decision.targets.tier0_target_cents / tier1_allocation_cents /
tier2_allocation_cents / tier3_allocation_cents; decision.reserve; decision.orders;
estimated_income_cents / estimated_price_change_cents / modeled_financing_cost_cents;
decision.expected_costs / instrument_returns / explanations / feasible;
model_version / policy_version / reward_assumptions; execution_status.
Result.risk describes baseline risk, not selected-plan risk; use
projected_nominal_funding_gap_cents, projected_scenario_failure_weight and
decision.estimated_market_risk_loss_cents for plan checks. Current balances and
marks come from the separate portfolio snapshot. Preserve decimal strings and
naive timestamp labels. Expected income is not realized return; UI fills come from
Member 2 receipts. Do not label a provisional buffer a calibrated confidence band.

## Unresolved boundaries and readiness

- four_tier.py still defines overlapping models and a contract-only recommendation
  function. It is actively imported by hourly_forecasting.py, ml_forecasting.py,
  instrument_economics.py, four_tier_demo.py and __init__.py. These imports resolve,
  but a blanket "no competing schemas/obsolete imports" certification is false.
  Do not delete them: existing public contracts/tests depend on compatibility.
- Canonical versus forecast metadata net targets differ. Explicit point conversion
  works; a unified metadata-preserving adapter is not implemented.
- Source row availability/timezone remain unspecified; replay must establish what
  information was known when. Source CSV itself is unchanged and hourly.
- No canonical Member 2 backend execution wiring or Member 3 frontend wiring was
  found/certified. This release verifies the import/JSON boundary, not execution.
- Legacy API evaluate_forecasting_models, generate_risk_scenarios and
  evaluate_allocation_candidates remain contract-only NotImplementedError stubs.
  Use evaluate_hourly_forecast_models, generate_multi_asset_scenarios and
  recommend_four_tier_allocation for implemented four-tier capabilities.

Measured metrics exist in MODEL_EVALUATION_REPORT.md / RELEASE_RESULTS.json;
no new metrics were invented or substituted in RJ-M1-15. Three-hour ML MAE is worse
than baseline. FINAL_AUDIT.md records statistical/search limitations. The package is
usable through the documented canonical boundary, but the single-contract release
criterion and end-to-end integration remain BLOCKED.

## Exact public signatures (inspected on the verified release)

```text
treasury_intelligence.hourly_forecasting.forecast_hourly_cashflows(history: 'Sequence[Any]', *, as_of: 'datetime', horizon_hours: 'int' = 24, model_version: 'str' = 'hourly-seasonal-naive-v1', config: 'HourlyForecastConfig | None' = None, start_at: 'datetime | None' = None, ml_model: 'Any | None' = None) -> 'HourlyForecastResult'
treasury_intelligence.ml_forecasting.hourly_ml_forecast(history: 'Sequence[Any]', *, as_of: 'datetime', horizon_hours: 'int' = 24, ml_model: 'HourlyCashFlowMLModel | None' = None, start_at: 'datetime | None' = None, model_version: 'str' = 'hourly-hist-gb-v1', fallback_model: "Literal['seasonal_naive', 'rolling_mean']" = 'seasonal_naive') -> 'HourlyForecastResult'
treasury_intelligence.ml_forecasting.evaluate_hourly_forecast_models(history: 'Sequence[Any]', *, horizons: 'Sequence[int]' = (1, 3, 6, 15, 24), train_ratio: 'float' = 0.7, val_ratio: 'float' = 0.15, eval_stride: 'int' = 12, algorithms: "Sequence[Literal['hist_gradient_boosting', 'random_forest']]" = ('hist_gradient_boosting',), random_state: 'int' = 42) -> 'tuple[HourlyModelEvaluationReport, ...]'
treasury_intelligence.liquidity_risk.calculate_four_tier_liquidity_risk(request: treasury_intelligence.liquidity_risk.FourTierLiquidityRiskRequest) -> treasury_intelligence.liquidity_risk.FourTierLiquidityRiskResult
treasury_intelligence.monte_carlo_risk.generate_multi_asset_scenarios(history: Sequence[treasury_intelligence.portfolio.OrganizerHourlyObservation], nominal_forecast: Sequence[treasury_intelligence.portfolio.HourlyForecastPoint], *, as_of: datetime.datetime, planning_horizon_hours: int = 24, scenario_count: int = 500, seed: int = 42, time_basis: Literal['UNSPECIFIED', 'UTC'] = 'UNSPECIFIED') -> tuple[treasury_intelligence.liquidity_risk.LiquidityScenario, ...]
treasury_intelligence.monte_carlo_risk.simulate_multi_asset_monte_carlo_risk(portfolio: treasury_intelligence.portfolio.PortfolioState, history: Sequence[treasury_intelligence.portfolio.OrganizerHourlyObservation], nominal_forecast: Sequence[treasury_intelligence.portfolio.HourlyForecastPoint], policy: treasury_intelligence.portfolio.FourTierTreasuryPolicy, *, planning_horizon_hours: int = 24, scenario_count: int = 500, seed: int = 42, confidence: decimal.Decimal = Decimal('0.95'), repo_settlements: Sequence[treasury_intelligence.liquidity_risk.RepoCashSettlement] = (), obligations: Sequence[treasury_intelligence.liquidity_risk.CommittedObligation] = (), available_overdraft_credit_cents: int = 0, operational_buffer_cents: int | None = None) -> treasury_intelligence.monte_carlo_risk.MultiAssetMonteCarloRiskResult
treasury_intelligence.optimizer.recommend_four_tier_allocation(request: treasury_intelligence.optimizer.AllocationOptimizerRequest) -> treasury_intelligence.optimizer.AllocationOptimizerResult
treasury_intelligence.portfolio.recommend_portfolio_allocation(request: treasury_intelligence.portfolio.FourTierRecommendationRequest) -> treasury_intelligence.portfolio.FourTierDecisionResult
treasury_intelligence.api.forecast_cashflows(history: collections.abc.Sequence[treasury_intelligence.types.CashFlowBucket], *, as_of: datetime.datetime, horizon_minutes: int, bucket_minutes: int, model_version: str = 'baseline-v1') -> treasury_intelligence.types.ForecastResult
treasury_intelligence.reserve.calculate_required_reserve(forecast: treasury_intelligence.types.ForecastResult, policy: treasury_intelligence.types.TreasuryPolicy) -> treasury_intelligence.types.ReserveResult
treasury_intelligence.policy.recommend_treasury_action(context: treasury_intelligence.types.TreasuryContext, forecast: treasury_intelligence.types.ForecastResult, policy: treasury_intelligence.types.TreasuryPolicy) -> treasury_intelligence.types.DecisionResult
```

## Constructor requirements

These are exact schema-required keyword names; conditional validators add the
requirements immediately below. Use model_json_schema() to obtain full types,
constraints and defaults, or validate the complete example request.

| Model | Required constructor fields |
| --- | --- |
| PortfolioState | time_basis, run_id, source_type, as_of, native_interval_seconds, currency, cash, valuation |
| CashPosition | time_basis, run_id, source_type, id, liquidity, balance_cents |
| RepoPosition | time_basis, run_id, source_type, id, liquidity, principal_cents, entered_at, scheduled_maturity_at, applicable_apy_pct, status, early_redemption_haircut_pct |
| BondPosition | time_basis, run_id, source_type, id, liquidity, quantity, acquisition_price_index, acquired_at, liquidation_haircut_pct, status, supplied_yield_pct, modified_duration |
| EquityPosition | time_basis, run_id, source_type, id, liquidity, quantity, acquisition_price_index, acquired_at, liquidation_haircut_pct, status, supplied_volatility_pct |
| OverdraftLiability | time_basis, run_id, source_type, id, borrowed_at, borrowed_cents, outstanding_principal_cents, repaid_principal_cents, apr_pct, breach_id, reference_id |
| PortfolioValuation | time_basis, run_id, source_type, valued_at, tier0_cash_cents, tier1_principal_cents, tier1_value_cents, tier2_market_value_cents, tier3_market_value_cents, total_portfolio_value_cents, immediately_available_cents, liquidatable_value_cents, restricted_value_cents, liabilities_cents, net_portfolio_value_cents, reference_id |
| FourTierTreasuryPolicy | base_buffer_cents, uncertainty_multiplier_bps, tolerance_bps, min_transfer_cents, max_allocation_bps, repo_sweep_window_open |
| HourlyForecastPoint | time_basis, start_at, predicted_deposits_cents, predicted_withdrawals_cents, predicted_net_flow_cents, supplied_uncertainty_buffer_cents |
| FourTierLiquidityRiskRequest | portfolio, policy, forecast, planning_horizon_hours, uncertainty_mode |
| AllocationOptimizerRequest | request_id, liquidity, rewards |
| AllocationRewardModel | time_basis, model_version, policy_version, assumption_reference, assumptions_available_at, holding_hours, assets |
| AssetRewardAssumption | tier, stress_loss_pct, forced_liquidation_probability, liquidation_haircut_pct |

Historical source records additionally require dataset_id and
source_observation_timestamp, with one matching run/source identity across nested
records. UUID fields must be valid UUIDs. Include only current unsettled repos and
OPEN market positions. Complete snapshots require repo market_value_cents,
market current_market_value_cents, explicit unpaid financing costs (even zero),
and reconciled valuation/liquidity totals. Position quote/risk fields must agree
with supplied current source observations. Tier 0 available/liquidatable cash must
equal balance. Historical repo entry/maturity are 17:00/next-day 08:00.

Risk forecast and all scenario paths must be contiguous, cover planning horizon,
begin at as_of and share the portfolio clock. scenario_quantile requires scenario
weights summing exactly to one and forbids calibrated_allowance; calibrated_allowance
mode requires explicit allowance provenance/cutoff. Do not add uncertainty twice.

Rewards need exactly one AssetRewardAssumption per tier 1/2/3, available by as_of,
and a horizon covered by the risk request. Tier 1 uses quoted repo income, with
zero explicit income/price return and no unit conversion. Tiers 2/3 additionally
require usd_per_index_point_per_unit even when not purchased. Calibrated rewards
require an actual calibration reference. Market purchases require explicit exposure
caps and current quotes; repo purchases require an open 17:00 window. Policy must
not enable a positive overdraft cap when borrowing is disabled.
