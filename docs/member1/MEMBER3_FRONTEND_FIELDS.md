# Member 3 display handoff — RJ-M1-14

Use canonical portfolio snapshots and AllocationOptimizerResult JSON. Do not mix
older four_tier fixture field names with canonical portfolio fields.

| Display | Canonical field |
| --- | --- |
| Available checking cash | portfolio.cash.balance_cents |
| Repo holdings | portfolio.repo_positions[]: principal_cents, scheduled_maturity_at, applicable_apy_pct, early_redemption_haircut_pct |
| Bond/equity marks | portfolio.bond_positions[] / equity_positions[]: quantity, current_market_price_index, current_market_value_cents, unrealized_pnl_cents |
| Borrowing | portfolio.overdrafts[]: outstanding_principal_cents, outstanding_financing_cost_cents, apr_pct |
| Gross/net asset value | portfolio.valuation.total_portfolio_value_cents / net_portfolio_value_cents |
| Liabilities | portfolio.valuation.liabilities_cents |
| Four targets | result.decision.targets.tier0_target_cents, tier1_allocation_cents, tier2_allocation_cents, tier3_allocation_cents |
| Required reserve | result.decision.reserve.required_reserve_cents |
| Proposed orders | result.decision.orders[]: tier, action, amount_cents, quantity, position_id, expected_costs, expected_settlement_at, expected_maturity_at |
| Recommendation | result.summary_action; result.decision.reason / explanations / feasible |
| Return assumptions | result.reward_assumptions; estimated_income_cents; estimated_price_change_cents |
| Version/status | result.model_version, policy_version; decision.execution_status / recommendation_only |

Use the typed result schema for additional cost, risk and search fields. Show
search_truncated; the result is the best generated feasible candidate, not a proof
of global optimality. Baseline risk differs from selected-plan risk.

Cash fields are integer cents. Format Decimal strings without binary-float
precision loss. Percentages are percentage points (4.292 means 4.292%); allocation
limits use basis points. Preserve unspecified hourly timestamp labels without
adding Z or implicit browser timezone conversion. Guard JavaScript integer limits.

Keep source net_flow_usd separate from forecast deposits-minus-withdrawals.
Provisional supplied_uncertainty_buffer_cents is not a calibrated confidence band.
In scenario_quantile mode required reserve uses the scenario peak quantile plus
operational buffer; uncertainty_buffer_cents is zero, not a second MC allowance.

Display risk available_cash_cents separately from restricted_liquidity_cents and
hypothetical stress-liquidatable proceeds. Reserve breach, projected funding
shortfall, tail expected shortfall and actual payout failure are different;
actual_payout_failure is null because no execution occurs. Scenario probabilities
are model estimates, not observed banking failure rates or guaranteed coverage.

Monte Carlo portfolio_downside represents an adverse hypothetical full permitted
liquidation endpoint including operational flows, fees and financing; it is not
pure investment drawdown, realized performance, or optimizer-selected execution.
Market losses have separate market_risk fields. A positive market value does not
imply immediately accessible cash. Bond yield is quoted YTM; equity expected price
return is uncertain. Label all modeled income/costs/returns as estimated.

All proposed orders are NOT_EXECUTED. Execution receipts must come from Member 2.
Demo results expose scenarios[].calculation_breakdown, human_readable_summary,
targets, recommended_orders and optional optimizer_result; they do not embed a
forecast chart series or full MC result. Fetch those result objects separately.
The four-scenario demo uses illustrative starting balances and synthetic market
shocks, not measured strategy returns. See RELEASE_RESULTS.json for actual forecast
error measurements and FINAL_AUDIT.md for limitations. No frontend was modified.

RJ-M1-15: docs/member1/integration_response.json is a complete canonical optimizer
output for consumer development; its single nominal scenario is illustrative, not
calibrated risk. See FOUR_TIER_HANDOFF.md and RELEASE_VERIFICATION.md for current
wire examples, exact imports and outstanding integration boundaries.
