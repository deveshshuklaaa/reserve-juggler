# RJ-M1-06 — Member 2 four-tier contract handoff

Authoritative wire types: `treasury_intelligence.portfolio`, also exported at the
package root. Consume these classes rather than copying their definitions into a
backend schema. This is a contract handoff, **not** an implemented backend adapter.

```python
from treasury_intelligence import (
    PortfolioState, PortfolioTreasuryContext, CashPosition, RepoPosition,
    BondPosition, EquityPosition, OverdraftLiability, PortfolioValuation,
    FourTierTreasuryPolicy, FourTierReserveResult, RecommendedOrder,
    FourTierDecisionResult,
)

snapshot = PortfolioState.model_validate_json(payload)
assert PortfolioTreasuryContext is PortfolioState
wire_json = snapshot.model_dump_json()
```

## Existing storage mapping (Member 2 commit 52e58bc)

Storage source: `backend/app/persistence/models.py` and additive migration
`003_four_tier_persistence.sql` on `feat/simulation-backend`. These are not present
on the Member 1 branch and are not recreated, imported or modified here.

| Wire contract | Existing storage | Mapping / supplied view data |
| --- | --- | --- |
| `PortfolioSource` | Run/source and observation foreign keys | `run_id`, `source_type`, `dataset_id`, `source_observation_timestamp` have the existing names and units |
| `CashPosition` | `cash_accounts` | `id`, `balance_cents`, `last_ledger_entry_id`, source fields map directly; tier/zero APY/liquidity are explicit view metadata |
| `RepoPosition` | `repo_positions` | Principal, entry/maturity, applicable APY, status, early redemption, accrued/realized interest, cost/proceeds and IDs retain existing names |
| Repo `market_value_cents` | `position_valuations.market_value_cents` | Supplied valuation, separate from position principal; no price or accrual calculation here |
| `BondPosition` | `bond_positions` | Quantity, acquisition/current index/value, yield/duration, P&L, liquidation cost/proceeds, market observation time retain existing names |
| `EquityPosition` | `equity_positions` | Same market fields, but volatility instead of yield/duration; no guaranteed interest |
| `OverdraftLiability` | `overdraft_liabilities` | Borrowed/outstanding/repaid principal, APR, financing cost, breach/reference IDs and timestamps map directly |
| `PortfolioValuation` | `portfolio_valuations` | All financial and source fields retain existing names; storage generates record ID and recorded_at |
| `FourTierDecisionResult` | `treasury_decisions` | Its action fits the existing HOLD/ALLOCATE/LIQUIDITY_WARNING storage actions; retain the full typed plan in `decision_details_json` and explanation in `explanation_json` |
| `RecommendedOrder` | Future execution -> `investment_movements` / `overdraft_movements` + ledger | Recommendation is not a movement. Executor supplies actual filled amounts, costs, times, ledger links and per-run idempotency references |

Do **not** pass the full wire model directly to an ORM constructor. The wire
`time_basis`, tier and `PositionLiquidity` are view/control metadata, not new table
columns. Obtain time basis from the owning run's `source_timezone_status`.
Member 2's synthetic event columns use naive UTC wall-clock values; an eventual
adapter may remove timezone information **only after** verifying explicit UTC.
Historical timestamps remain naive without conversion in both layers.

`PortfolioState.native_interval_seconds` comes from the owning run. Portfolio
state is an aggregate view, not a new persistence table. Cash and investment
liquidity, repo current value and portfolio totals must be supplied by the caller;
this contract migration does not derive them. Database-only `recorded_at` stays
outside quantitative models. Per-run idempotency and transaction atomicity remain
the executor/repository's responsibility.

The existing decision row still requires `step`, its legacy timestamp/amount fields
and execution status. Member 2 supplies step/reference metadata; historical legacy
timestamp stays NULL, action-plan `amount_cents` can remain 0 as its compatibility
envelope, and recommendation status is PENDING, not EXECUTED. Preserve all orders
in `decision_details_json`; never collapse multi-instrument amounts into one fake
vault action. Optional target-allocation columns must not be populated by guessing
an optimized portfolio from these orders. Source/run columns remain mandatory for
new repository writes. No such persistence calls are implemented here.

## Financial boundaries / unresolved execution questions

- Supplied current market values and P&L are independent from acquisition values.
  The contract deliberately does not invent a bond pricing model or an index-unit
  conversion formula. The future valuation/execution milestone must agree the
  quantity/notional convention and fill-price/rounding rules.
- Repo entry/maturity are explicit, using the organizer clock. No guessed timezone,
  automatic sweep, rollover, accrual day-count or rounding convention is introduced.
- Financing cost is a supplied incurred/cumulative cost, not automatically added
  to outstanding principal. Portfolio liabilities must cover outstanding principal
  but may additionally include separately recognized unpaid financing costs.
  Cost capitalization/payment treatment must be agreed before execution; otherwise
  financing costs could be double-counted against cash and liabilities.
- Model permissions/limits are not proof that an order is executable. Reserve,
  cash, market prices, fees, maturity and source freshness require revalidation.
- The old forecasting/pipeline contracts remain UTC generic-vault v1. Supporting
  hourly organizer forecasts and four-tier decision mathematics belongs to a later
  explicitly assigned task. No 15-minute organizer observations may be synthesized.
- This branch does not modify the public API or OpenAPI. Member 2's earlier
  API/adapter placeholders and this pure contract handoff still need an explicitly
  approved integration milestone; no engine signatures are invented here.
