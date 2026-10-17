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

## RJ-M1-13: Official Four-Tier Demo UI Specifications

The demo output contract `FourTierDemoSuiteResult` and `FourTierDemoScenarioResult`
expose complete structured fields for charting, dashboard KPIs, and audit reporting.

### 1. Forecast Series Display
| UI Component | Data Path | Description |
| --- | --- | --- |
| Hourly Cash Flow Chart | `fc_result.points[]` | Array of hourly forecast intervals covering planning horizon (e.g. 15h or 24h). |
| Start Timestamp | `point.start_at` | Naive hourly timestamp (e.g. `2026-01-02T18:00:00`). |
| Predicted Deposits | `point.predicted_deposits_cents / 100` | Inflows expected in this interval (green bar/line). |
| Predicted Withdrawals | `point.predicted_withdrawals_cents / 100` | Outflows expected in this interval (red bar/line). |
| Net Cash Flow | `point.predicted_net_flow_cents / 100` | Net change (deposits minus withdrawals). |
| Uncertainty Band | `point.supplied_uncertainty_buffer_cents / 100` | Confidence band allowance for the interval. |

### 2. Uncertainty & Multi-Asset Risk Fields
| Metric | Data Path | Description |
| --- | --- | --- |
| Required Reserve | `mc_result.required_reserve.required_reserve_cents / 100` | Mandatory liquid reserve floor to protect cash solvency. |
| Net Drain | `mc_result.required_reserve.net_drain_cents / 100` | Peak cumulative cash outflow across the planning horizon. |
| Uncertainty Buffer | `mc_result.required_reserve.uncertainty_buffer_cents / 100` | Monte Carlo 95th percentile risk allowance. |
| Shortfall Risk | `mc_result.shortfall_distribution.shortfall_probability_before_liquidation` | Empirical probability of running negative cash without liquidation. |
| Tail Shortfall | `mc_result.shortfall_distribution.tail_expected_shortfall_cents / 100` | Expected deficit severity in tail loss scenarios. |
| Bond Risk Loss | `mc_result.market_risk.tier2_bond_loss_p95_cents / 100` | 95th percentile mark-to-market drawdown on 2Y bonds. |
| Equity Risk Loss | `mc_result.market_risk.tier3_equity_loss_p95_cents / 100` | 95th percentile mark-to-market drawdown on equity index. |
| Portfolio Drawdown | `mc_result.portfolio_downside.max_downside_loss_cents / 100` | Worst-case net asset value drawdown across all simulated scenarios. |

### 3. Four-Tier Portfolio Allocation Details
| Tier | Target Path | Units / Convention |
| --- | --- | --- |
| **Tier 0: Cash** | `opt_res.decision.targets.tier0_target_cents / 100` | 100% immediate operational liquidity; 0% yield. Must cover required reserve. |
| **Tier 1: Repo** | `opt_res.decision.targets.tier1_allocation_cents / 100` | Overnight repo; entered at 17:00, matures at 08:00 (15h). 0.5% early-break fee. |
| **Tier 2: Bonds** | `opt_res.decision.targets.tier2_allocation_cents / 100` | 2Y sovereign bonds; priced via price index. 2% liquidation haircut. |
| **Tier 3: Equity** | `opt_res.decision.targets.tier3_allocation_cents / 100` | Broad equity index; priced via index price. 15% emergency sale slippage. |
| **Overdraft** | `opt_res.decision.target_overdraft_principal_cents / 100` | Outstanding borrowing liability; APR financing cost. Not an asset! |

### 4. Tier-Specific Valuations & Fees Display
- **Valuation Breakdown**:
  - `portfolio.valuation.tier0_cash_cents / 100`
  - `portfolio.valuation.tier1_value_cents / 100`
  - `portfolio.valuation.tier2_market_value_cents / 100`
  - `portfolio.valuation.tier3_market_value_cents / 100`
  - `portfolio.valuation.total_portfolio_value_cents / 100` (Gross Assets)
  - `portfolio.valuation.liabilities_cents / 100` (Overdraft Debt)
  - `portfolio.valuation.net_portfolio_value_cents / 100` (Net Asset Value)
- **Haircut & Liquidation Proceeds**:
  - Display `liquidatable_value_cents` alongside mark-to-market value so users see post-haircut realizable cash.
- **Yield & Fees**:
  - Tier 1: Quoted Repo APY (e.g. 4.272%).
  - Tier 2: Quoted Bond Yield (e.g. 4.822%).
  - Tier 3: Equity return is **never labeled guaranteed**. Display as 0% expected fixed income with historical volatility metric.

### 5. Decision Explanations & Audit Trail
- **Action Badge**:
  - `summary_action`: Display prominently (`INVEST` in green, `HOLD` in blue, `WARNING` in red/amber).
  - `canonical_action`: Backend action (`ALLOCATE`, `HOLD`, `LIQUIDITY_WARNING`).
  - `feasible`: Show checkmark (True) or warning icon (False).
- **Narrative Rationale**:
  - `scenario.human_readable_summary`: Plain-text explanation of decision math and policy checks.
  - `opt_res.decision.reason`: Concise canonical reason string.
  - `scenario.calculation_breakdown`: Detailed numeric dictionary for drilldown modals.
- **Execution Notice**:
  - Always render `[RECOMMENDATION ONLY — NOT EXECUTED]` banner on proposed orders. Fills and receipts are managed exclusively by Member 2.
