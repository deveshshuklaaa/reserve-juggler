# Member 3: four-tier display fields

Read the additive request/response JSON; no frontend edits are part of RJ-M1-06.

| Display | Fields |
| --- | --- |
| Operational liquidity | portfolio.cash.available_cents, response.required_liquid_reserve_cents, Tier 0 target |
| Repo | repos[].principal_cents, entered_at, matures_at, entry_apy_pct, early_break_fee_pct, estimated_interest_cents |
| Bonds | bonds[].market_value_cents, cost_basis_cents, observed_price_index, annual_yield_pct, modified_duration_years, liquidation_haircut_pct |
| Equity | equities[].market_value_cents, cost_basis_cents, observed_price_index, annual_volatility_pct, emergency_sale_slippage_pct |
| Borrowing | overdraft.principal_cents, accrued_financing_cost_cents, annual_apr_pct; response.target_overdraft_principal_cents |
| Targets and limits | targets[].instrument/target_cents; exposure_constraints[].minimum_fraction/maximum_fraction |
| Proposed trades | trades[].instrument, action, principal_cents, index_units, expected_settlement_at, expected_maturity_at, expected_costs, reason |
| Returns and risk | instrument_returns[].expected_income_cents, expected_price_change_cents, estimated_stress_loss_cents, horizon_hours, estimate_basis; estimated_market_risk_loss_cents |
| Explanation/status | action, feasible, explanations[], recommendation_only, execution_status, metadata.uncertainty_status/notes |

Display Decimal strings with a decimal-aware formatter. Percent fields use
percentage points (4.292 = 4.292%); exposure fractions use 0–1 (0.5 = 50%). Cash
fields are integer cents; guard against JavaScript unsafe integers for large values.
Keep source net_flow_usd separate from any calculated deposits-minus-withdrawals.
Use the supplied hourly timestamps as timezone-unspecified strings; do not append
Z or silently let browser timezone conversion change labels. No 15-minute source
history exists. Distinguish cash, locked repo, marked investments, and debt; do not
sum overdraft into asset income. Marked value and estimated risk are different.

Label returns as **expected/estimated**, not realized or guaranteed. Show estimated
fees/funding separately from portfolio.realized_costs. Duration stress is separate
from observed bond price movement. Every new recommendation/trade is NOT_EXECUTED;
execution status must come from Member 2's receipts, not an inferred UI state.
Fixtures are examples with not_evaluated metadata; do not present their estimates
as historical performance metrics.

RJ-M1-10's canonical liquidity-risk response adds reserve (with explicit time_basis),
available_cash_cents versus restricted_liquidity_cents, pre/post-liquidation funding
shortages, stress liquidation quotes, policy_violations, and full timed cash paths.
Keep reserve_breach distinct from projected_funding_failure_* and from
actual_payout_failure (always null here). Scenario failure probabilities and tail
expected shortfall are supplied-model estimates, not realized payout statistics;
without scenarios those fields are null. Modeled overdraft draw/cost is new
financing, not an existing asset. Render uncertainty_mode and explanations so
scenario quantiles are not displayed as a second added uncertainty buffer.

RJ-M1-11 returns summary_action (HOLD/INVEST/REBALANCE/LIQUIDATE/WARNING), a canonical
decision with four targets/orders, model_version/policy_version, reward_assumptions,
objective_cents, expected income/price/exit/funding costs, target stress loss,
candidate counts/rejections, and search_truncated. Show current post-order buying
cash separately from pro-forma target cash that may include later sale proceeds.
Baseline risk is not the selected plan's risk: display projected nominal funding
gap, scenario failure weight, and decision.estimated_market_risk_loss_cents for the
plan. All rewards are expected/user-supplied unless a calibration reference is
explicitly supplied. Never label the best generated candidate globally optimal,
executed, or guaranteed profitable. NOT_EXECUTED remains fixed.
