# Four-tier display fields — canonical contracts only

Documentation only; no frontend or public API implementation is changed here.
Read PortfolioState and FourTierDecisionResult from treasury_intelligence.portfolio.
Do not consume the retired FourTierPortfolioState / PortfolioRecommendation payloads.

| Display | Canonical fields |
| --- | --- |
| Cash and availability | state.cash.balance_cents, state.cash.liquidity.available_cents, decision.reserve.required_reserve_cents |
| Repo | repo_positions[].principal_cents, entered_at, scheduled_maturity_at, applicable_apy_pct, early_redemption_haircut_pct; distinct expected/accrued/realized interest fields |
| Bonds | bond_positions[].acquisition_price_index, current_market_price_index, current_market_value_cents, acquisition_cost_cents, supplied_yield_pct, modified_duration, realized_pnl_cents, unrealized_pnl_cents, liquidation_haircut_pct |
| Equities | equity_positions[].current_market_price_index, current_market_value_cents, supplied_volatility_pct, realized_pnl_cents, unrealized_pnl_cents, liquidation_haircut_pct |
| Borrowing | overdrafts[].outstanding_principal_cents, apr_pct, financing_cost_cents, paid_financing_cost_cents, outstanding_financing_cost_cents |
| Balance sheet | valuation.total_portfolio_value_cents, immediately_available_cents, liquidatable_value_cents, restricted_value_cents, liabilities_cents, net_portfolio_value_cents |
| Targets | decision.targets.tier0_target_cents, tier1_allocation_cents, tier2_allocation_cents, tier3_allocation_cents; target_overdraft_principal_cents separately |
| Policy limits | decision.policy.tier_limits[].tier, min_allocation_bps, max_allocation_bps |
| Recommendations | orders[].id, tier, action, amount_cents, quantity, position_id, execution/settlement/maturity estimates, estimated_cost_cents, expected_costs, reason |
| Expected returns/risk | instrument_returns[].expected_income_cents, expected_price_change_cents, estimated_stress_loss_cents, horizon_hours, estimate_basis; decision.estimated_market_risk_loss_cents |
| Status and explanation | decision.action, feasible, reason, explanations, recommendation_only, execution_status, metadata.uncertainty_status |

Decimal values are JSON strings. Percent values are percentage points (4.308 means
4.308%); policy bps use 10000=100%, not 0–1 fractions. Money is integer cents; guard
JavaScript unsafe integers. Historical timestamps are naive/UNSPECIFIED; never
append Z or let browser timezone conversion relabel them. Only explicitly UTC
synthetic timestamps may be displayed as UTC.

Gross assets, liquidatable value and available cash are not additive categories.
Debt is not a fifth asset tier. Paid financing cost is not unpaid debt. Current
market P&L is not a transaction fee or a second duration stress loss. Expected
returns are not realized earnings or guaranteed equity interest. Fixed NOT_EXECUTED
on recommendations cannot substitute for Member 2's actual execution receipt.
