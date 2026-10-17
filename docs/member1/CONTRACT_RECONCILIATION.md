# RJ-M1-06 concurrent contract reconciliation

Compared before integration: local `87a8217` (`portfolio.py`) and teammate
`974154e` (`four_tier.py`), both based on `c35da91`. Neither commit is automatically
authoritative. Member 2 storage at `52e58bc` is the field/unit compatibility check.

## Decision

**One canonical module: `treasury_intelligence.portfolio`.** Retain the
UUID/provenance, instrument-specific positions, liquidity, explicit valuation,
signed P&L, source precision and legacy compatibility from `87a8217`. Reconcile
the independently useful source/quote, schedule, forecast-provenance, cost,
target and timing validation from `974154e` into that module. Remove
`four_tier.py`; do not keep its old schemas, aliases or a wire-format adapter.
Old four-tier payloads must be rebuilt against the canonical JSON schemas.
The unrelated pre-RJ-M1-06 generic-vault v1 pipeline remains supported unchanged.

## Field-by-field decisions

| Topic / 974154e fields | 87a8217 fields | Final resolution |
| --- | --- | --- |
| `FourTierContract` frozen/forbid extras | `TimedPortfolioContract` reuses legacy configuration | Keep canonical timed base; all auxiliary contracts reuse the same frozen/forbid policy |
| `InstrumentId`: four assets + OVERDRAFT | Integer `tier` discriminator on positions | Position discriminator stays integer 0–3. Retain InstrumentId only for return-estimate labels; overdraft is never a fifth asset tier |
| Position `position_id: Name`; cash/overdraft have no ID | `id: UUID`, `run_id`, `source_type`, `dataset_id`, observation timestamp | Keep canonical UUID identities and source/run isolation for all positions/loans; `position_id` remains a UUID reference only on orders |
| `timestamp_basis=timezone_unspecified`, all new timestamps naive | Per-record `time_basis` UNSPECIFIED/UTC | Keep historical naive and explicitly UTC synthetic support; reject implicit offset conversion and epoch inputs |
| `OrganizerHourlyObservation`: exactly 16 source fields | No duplicate source row model | Retain the source-row contract in the canonical module; finite Decimal values, literal CSV booleans, native hourly timestamps and independent net_flow_usd. Match Member 2's strictly positive modified duration |
| `MarketRateObservation`: observed_at, repo_apy_pct, bond_yield_pct, equity_volatility_pct, overdraft_apr_pct | Position-specific rates and source timestamps | Retain the quote view with explicit time_basis; rates remain Decimal percentage points, not integer bps |
| `MarketPriceObservation`: observed_at, bond_price_index, bond_modified_duration_years, equity_index_price | Position acquisition/current index and market observation timestamp | Retain the quote view; when supplied, current marks/risk inputs must match its timestamp/index/duration/volatility |
| Tier 0 `available_cents`, annual_yield_pct=0 | CashPosition balance_cents, zero apy_pct, liquidity, last_ledger_entry_id | Keep identified cash account and fully liquid zero-yield validation; availability is not a second cash balance |
| Repo `principal_cents`, entered_at, matures_at, entry_apy_pct | principal_cents, entered_at, scheduled_maturity_at, applicable_apy_pct | Keep storage-compatible names; adopt exact 17:00–next-day 08:00 validation for organizer historical sessions. Explicit UTC synthetic sessions are not assigned a guessed bank timezone |
| Repo early_break_allowed, default early_break_fee_pct=0.5 | Required early_redemption_haircut_pct; early_redemption_at/status/cost/proceeds | Keep required supplied haircut and actual history fields; add optional early_redemption_allowed view permission. No silent fee default |
| Repo estimated_interest_cents | accrued_interest_cents / realized_interest_cents | Keep accrued and realized separate; adopt expected_interest_cents as a distinct optional estimate. Never reinterpret an estimate as booked interest |
| Market index_units, cost_basis_cents, observed_price_index, marked_at, market_value_cents | quantity, acquisition_price_index/acquired_at, current_market_price_index/value, signed realized/unrealized P&L | Keep canonical stored fields. Add optional acquisition_cost_cents view data for cost-basis reporting, without a second market-value formula |
| Bond matures_at, tenor_years=2, annual_yield_pct, modified_duration_years | supplied_yield_pct, modified_duration | Keep supplied yield/duration names; retain optional contractual_maturity_at and fixed tenor_years=2 as view data. A 2Y instrument label does not manufacture a maturity date |
| Equity annual_volatility_pct, emergency_sale_slippage_pct | supplied_volatility_pct, liquidation_haircut_pct | Keep canonical field names; no interest/APY field on equities |
| Market-value validator: round_half_up(index_units × index × 100) | Supplied current market value independent of quantity/index | Reject the invented normalized-USD unit/rounding convention. Preserve exact quantity/index and supplied value; no financial calculation engine in a schema |
| Default bond haircut 2%, equity slippage 15% | Required haircut input plus cost/proceeds/P&L | Keep required source percentages and separately supplied actual costs/proceeds. Do not charge observed market loss again as a fee or duration stress |
| Aggregate overdraft principal_cents, accrued_financing_cost_cents, annual_apr_pct, mandatory credit_limit_cents | Per-loan borrowed/outstanding/repaid principal, APR, incurred financing cost, breach and audit references | Keep canonical per-loan model/list and principal identity. Credit capacity belongs to explicit policy, not an invented loan balance field |
| Accrued overdraft cost treated as debt | financing_cost_cents was cumulative with unpaid treatment unspecified | Define cumulative incurred cost = paid + outstanding financing cost. Require an explicit split in a complete portfolio; net liabilities include outstanding principal + unpaid cost only. Paid cost is not deducted a second time |
| FourTierPortfolioState cash/repos/bonds/equities/overdraft, quotes, realized_costs; no balance sheet | PortfolioState cash/repo_positions/bond_positions/equity_positions/overdrafts + PortfolioValuation | Keep canonical state and valuation. Retain optional shared market quotes. Historical currency is USD; synthetic currency remains explicit. No aggregate debt or duplicate realized-cost balance |
| Implicit cash-only liquidity | PositionLiquidity available/locked/liquidatable and portfolio totals | Keep explicit liquidity. Locked may overlap liquidatable; market values are not cash. Maturity alone is not cash settlement |
| No explicit valuation / P&L fields | Tier values, gross assets, liquidity, restrictions, liabilities, signed net value; signed position P&L | Keep all canonical fields and reconcile every total against positions and liabilities |
| CostBreakdown liquidation_fee/repo_break_fee/transaction/funding/market_loss cents | Optional estimated_cost_cents; actual per-position costs | Retain four fee/funding components; remove market_loss_cents from fees. Signed market P&L and estimated price changes/stress losses remain separate. Reconcile supplied total estimate to component sum |
| ExposureConstraint Decimal fractions minimum_fraction/maximum_fraction per instrument | TierAllocationLimit integer max_allocation_bps | Extend canonical limits with min_allocation_bps and Tier 0; exact integer bps only. No silent rounding of fractional bounds. Validate ordered bounds and full-portfolio feasibility when all four limits are supplied |
| FourTierRiskPolicy minimum_liquid_reserve/operational_buffer/max_loss/overdraft limits, exposure constraints, bond_risk_method | FourTierTreasuryPolicy inherited buffers/limits + explicit repo/liquidation permissions | Keep canonical policy; map operational_buffer to base_buffer, retain optional minimum reserve/risk limits and explicit overdraft policy. Preserve observed-index/separate-duration-stress distinction |
| ForecastRiskMetadata model_version/generated_at/training_data_through/granularity_hours/net_flow_target/uncertainty/evaluation_reference/notes | No new forecasting metadata | Retain explicit hourly metadata with time_basis; organizer forecast target is source_net_flow_usd only. Evaluated status requires a reference, not invented metrics |
| HourlyForecastPoint start_at, predicted deposits/withdrawals/net, supplied uncertainty | No new forecast-point family | Retain hourly input contract with explicit basis, separate signed predicted net flow and no algorithm/resampling |
| FourTierRecommendationRequest request_id, portfolio, history, policy, metadata, forecast | Canonical state/policy separately | Retain envelope using canonical models only; explicit historical source-row availability cutoff prevents assuming same-hour totals were known at hour start |
| AllocationTarget instrument/target_cents; response budget | No target fields | Use AllocationTargets with exact Member 2 column names: tier0_target_cents, tier1_allocation_cents, tier2_allocation_cents, tier3_allocation_cents. Targets sum to supplied gross asset budget, not net worth; debt separate |
| TradeRecommendation trade_id/instrument/action/principal_cents/index_units/position_id | RecommendedOrder id/tier/typed action/amount_cents/quantity/position_id | Keep canonical order IDs, numeric tiers and typed instrument actions. Do not retain generic BUY/SELL with a competing instrument discriminator. Repayment requires liability ID |
| earliest_execution_at, expected_settlement_at, expected_maturity_at, expected_costs | Only order as_of/estimated_cost/expected_proceeds/reason | Adopt optional paired execution/settlement times, repo maturity and fee breakdown into RecommendedOrder. Historical repo entry uses 17:00/08:00 when a schedule is supplied |
| recommendation_only=true, execution_status=NOT_EXECUTED | recommendation_only=true | Keep recommendation-only and add fixed NOT_EXECUTED display status. Never store an execution receipt in these models |
| InstrumentReturnEstimate income/price change/costs/stress/horizon/basis/realized=false | No separate estimate DTO | Retain expected-only return estimate; equity expected price change is not guaranteed interest, and duration stress is not charged to the observed mark |
| PortfolioRecommendation request_id/as_of/HOLD-REBALANCE-WARNING/feasible/budget/targets/debt target/reserve/trades/cost/risk/returns/bounds/metadata/explanations | FourTierDecisionResult source/as_of/HOLD-ALLOCATE-WARNING/reserve/orders/reason | Keep canonical ALLOCATE action (Member 2 supports it). Adopt optional target/budget/feasibility/debt/cost/risk/return/policy/metadata/explanation fields with consistency validation. No parallel response type |
| recommend_portfolio_allocation request -> PortfolioRecommendation stub | No four-tier algorithm function | Retain a contract-only declaration returning FourTierDecisionResult; it raises NotImplementedError and cannot route to the legacy vault algorithm |
| Separate MEMBER2_INTEGRATION / MEMBER3_FRONTEND_FIELDS docs | FOUR_TIER_HANDOFF and ENGINE_CONTRACT | Rewrite all handoff/display references to the same canonical classes and fields; documentation only, no frontend/API edits |
| Independently named request/response JSON and tests | Portfolio fixture + 90 tests | Migrate the request/response examples to canonical models and preserve source-row fixture. Retain the local 90-test coverage; port teammate checks into a separate reconciliation suite |

## Explicitly deferred execution decisions

The contract fixes units and meanings, not a strategy: supplied quantity is opaque
until an approved index exposure/notional convention is selected; acquisition cost
and supplied market/P&L are independent inputs. Fill-price, partial-fill, fee and
accrual rounding, rate path/day-count and posting order remain execution work.
No half-up market/accrual calculation is implied. Source-hour availability must
be declared by the caller; a row label does not prove its full flows were known.
No optimizer, hourly replay, Member 2 persistence, API or frontend implementation
is added. Neither old four-tier JSON family remains independently executable.
