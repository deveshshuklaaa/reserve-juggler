# Canonical Member 2 handoff — reconciled RJ-M1-06

**Import only treasury_intelligence.portfolio or its identical package-root
exports.** four_tier.py, FourTierPortfolioState, PortfolioRecommendation and
TradeRecommendation are retired, not parallel schemas. See
[all field decisions](CONTRACT_RECONCILIATION.md). The pre-RJ-M1-06 generic-vault
v1 pipeline remains legacy, not a four-tier adapter.

```python
from treasury_intelligence.portfolio import (
    PortfolioState, PortfolioTreasuryContext, CashPosition, RepoPosition,
    BondPosition, EquityPosition, OverdraftLiability, PortfolioValuation,
    FourTierTreasuryPolicy, FourTierReserveResult, RecommendedOrder,
    AllocationTargets, FourTierDecisionResult, FourTierRecommendationRequest,
    OrganizerHourlyObservation, recommend_portfolio_allocation,
)
snapshot = PortfolioState.model_validate_json(payload)
assert PortfolioTreasuryContext is PortfolioState
wire_json = snapshot.model_dump_json()
```

The future boundary is recommend_portfolio_allocation(FourTierRecommendationRequest)
-> FourTierDecisionResult. It raises NotImplementedError. Do not route to the old
vault engine or regard fixture responses as optimizer output.

## Exact persistence mapping

Verified against Member 2 models/migration 003 at commit 52e58bc, without importing
or modifying ORM code. These tables remain on feat/simulation-backend.

| Canonical fields | Existing storage |
| --- | --- |
| run_id, source_type, dataset_id, source_observation_timestamp | Same-named source/run/observation references |
| CashPosition id, balance_cents, last_ledger_entry_id | cash_accounts |
| RepoPosition id, principal_cents, entered_at, scheduled_maturity_at, applicable_apy_pct, status, early_redemption_at, early_redemption_haircut_pct, accrued_interest_cents, realized_interest_cents, early_redemption_cost_cents, proceeds_returned_cents | repo_positions, same names/units |
| RepoPosition market_value_cents | position_valuations.market_value_cents, never principal |
| BondPosition/EquityPosition quantity, acquisition_price_index, acquired_at, current_market_price_index, current_market_value_cents, realized_pnl_cents, unrealized_pnl_cents, liquidation_haircut_pct, liquidation_cost_cents, liquidation_proceeds_cents, market_observation_timestamp, status | bond_positions / equity_positions, same names/units |
| BondPosition supplied_yield_pct, modified_duration | bond_positions |
| EquityPosition supplied_volatility_pct | equity_positions |
| OverdraftLiability id, borrowed_at, borrowed_cents, outstanding_principal_cents, repaid_principal_cents, apr_pct, financing_cost_cents, breach_id, reference_id | overdraft_liabilities |
| PortfolioValuation valued_at, tier0_cash_cents, tier1_principal_cents, tier1_value_cents, tier2_market_value_cents, tier3_market_value_cents, total_portfolio_value_cents, immediately_available_cents, liquidatable_value_cents, restricted_value_cents, liabilities_cents, net_portfolio_value_cents, reference_id | portfolio_valuations; storage supplies ID/recorded_at |
| FourTierDecisionResult action / reserve.required_reserve_cents | treasury_decisions action / required_reserve_cents |
| AllocationTargets four fields | treasury_decisions tier0_target_cents, tier1_allocation_cents, tier2_allocation_cents, tier3_allocation_cents |
| Whole decision / reason and explanations | decision_details_json / explanation_json; preserve all typed orders and expected-only metadata |
| RecommendedOrder | Not a financial movement; future executor writes actual fills/costs to investment_movements or overdraft_movements with ledger links |

Do not expand a complete wire dictionary into ORM constructors. These are
view/control data, not new columns:

- time_basis, tier, liquidity and cash apy_pct; aggregate state and quotes;
- repo market_value_cents (separate valuation), expected_interest_cents,
  early_redemption_allowed;
- market acquisition_cost_cents; bond tenor_years and contractual_maturity_at;
- overdraft paid_financing_cost_cents and outstanding_financing_cost_cents.

The paid/unpaid split must come from actual supplied financing-movement/ledger
history, not an assumption that cumulative cost was paid. Raw loan DTOs may leave
it unknown; a complete portfolio rejects unknown splits. Cumulative incurred
financing_cost_cents = paid + outstanding cost. Net liabilities include outstanding
principal plus unpaid cost only; paid cost is already reflected in cash. These
fields add no persistence mapper, column or posting implementation.

The run supplies time_basis from source_timezone_status and native_interval_seconds.
Historical uses UNSPECIFIED/naive/hourly/USD. Explicit UTC synthetic events may
lose their offset for Member 2's naive UTC columns only after UTC verification.
No guessed timezone or synthetic source row is permitted.

OrganizerHourlyObservation retains exactly 16 source columns. Quote mappings:
repo_apy_pct -> tier1_repo_rate_apy; bond_yield_pct -> tier2_bond_yield_pct;
equity_volatility_pct -> tier3_stock_volatility_pct; overdraft_apr_pct ->
emergency_overdraft_penalty_apr_pct; bond_price_index -> tier2_bond_price_index;
bond_modified_duration_years -> tier2_bond_mod_duration; equity_index_price ->
tier3_stock_index_price. observed_at is the source timestamp. Preserve Decimal
strings, supplied net_flow_usd, and fractional rate precision; never convert via float.

Existing decision rows still require step/reference metadata, legacy timestamp/
amount and execution status. Historical legacy timestamp stays NULL; the multi-
order envelope amount can remain 0. Persist recommendation status PENDING, not
EXECUTED. Fixed wire NOT_EXECUTED is not a database receipt. Do not guess targets
when absent. Use order UUIDs for future idempotency and an atomic execution transaction.

## Explicitly deferred execution questions

- Quantity, acquisition cost, index, current market value and P&L remain supplied,
  without an invented quantity × index × 100 formula. Agree exposure/notional,
  fill/partial-fill, fee/accrual rounding and rate/day-count rules before execution.
- history_available_at is a caller attestation, not derived from a row label.
  Window eligibility, quote freshness, settlement and all cash legs need revalidation.
- CostBreakdown contains fee/funding estimates, not market P&L. Observed bond marks
  and duration stress are not two realized charges. Equity expectations are not interest.
- Feasibility checks supplied policy/reserve/targets/risk, not actual fill-to-target
  reconciliation. Response cost covers its modeled horizon, not just order fees.
- This reconciliation adds no forecasting, optimizer, replay, API/OpenAPI,
  persistence or frontend behavior. No RJ-M1-07 work is started.
