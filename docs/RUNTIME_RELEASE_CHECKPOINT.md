# Core runtime release checkpoints

Owner: Agent 1. Work remains local on `codex/runtime-api-acceptance`.
Base runtime: `1ff1e655070d6b13e24c060d30c9782457d01598`.
Base provenance/contracts: `f60ee70688d3a94c302376faa305cef3dab788d9`.
These objects and ancestry were checked locally, not fetched by assuming that
an unpublished SHA exists remotely. Main, the frontend integration checkout,
Member 1 source, persistence schema, and Agent 2's branch are untouched.

## Market execution receipt v1

Shared implementation: `backend/app/services/market_execution.py`,
`execute_market_order(session, run, cash, recommendation, observation, step,
minimum_cash_cents=0)`, dispatched by `execute_hourly_step`.
Input is the existing canonical `treasury_intelligence.portfolio.RecommendedOrder`;
it is revalidated, not replaced with a competing portfolio contract.

Persisted evidence:

- `InvestmentMovement`: INVESTMENT for purchases, LIQUIDATION for sales;
  run, source observation, tier, position foreign key, timestamp, actual
  signed cash delta, actual acquisition/released cost basis in principal_cents,
  source haircut in haircut_cost_cents, and the fill ledger foreign key.
  Unique reference `market-order-{recommendation UUID}` prevents repeat fills.
- `LedgerEntry`: MARKET_PURCHASE_DEBIT or MARKET_LIQUIDATION_CREDIT,
  plus a separate MARKET_TRANSACTION_FEE debit when nonzero. Every entry
  stores actual before/after cash, amount, step, run and source.
- `PositionValuation`: one closing mark per lot/hour. realized_pnl_cents is
  the sum of gross realized sale P&L events in that hour; market value and
  unrealized P&L describe the remaining position, not a fabricated fill.
- `TreasuryDecision.decision_details_json.orders_executed[]`: run_id,
  step, order_id, action, position_id, requested_amount_cents,
  executed_amount_cents, status=EXECUTED, reason, quantity and price_index
  (exact decimal strings), principal_cents, gross_cents, cash_delta_cents,
  transaction_cost_cents, liquidation_cost_cents, realized_market_pnl_cents,
  remaining_cost_basis_cents, ledger_entry_ids and movement_id.
  UUIDs are serialized as strings in persisted decision JSON.
- Rejected recommendations have zero executed amount, status=REJECTED and
  reason in orders_rejected; no cash, movement or position mutation.

Execution is transaction-scoped; the caller commits or rolls back. Market
orders are full fills or rejections, not silently clamped recommendations.
Purchases create separate lots. Deferred market settlement is rejected
explicitly; it is not modeled as immediate cash. One unit equals one USD per
index point, matching the existing adapter assumption, not an invented bond
pricing model. Purchases round cash principal upward; sale gross proceeds round
downward; source haircuts and explicit transaction costs remain separate.
Recommendation-driven sales currently use organizer liquidation haircuts too
(2% bonds / 15% equities), not a made-up lower normal-sale fee.
Expected costs remain estimates; receipts contain actual execution costs.

Partial sales release proportional actual cost basis, HALF_UP; the final sale
releases every remaining basis cent. Closed lots retain a positive recorded
quantity because the existing schema requires it, but status=CLOSED, zero
market value and zero remaining basis mean they are no longer holdings.
No schema migration is introduced. Existing opening lots without purchase
movements use their persisted value-minus-unrealized basis; source acquisition
quantity/price is a final legacy fallback.

Agent 2 integration requirement: its receipt reader currently accepts only
LIQUIDATION for Tier 2/3 and does not recognize market purchase/transaction-fee
ledger types. It must consume the above evidence and charge transaction fees
once, separately from liquidation haircuts. Do not enable market-order
historical comparisons with the older reader. Its code has not been edited.

## Verification and remaining gates

First regression run: eight PostgreSQL market tests failed because the shared
runtime had no purchase/partial-sale callable. After implementation those eight
passed. Additional real-hourly dispatch tests inject only the recommendation
boundary; execution, PostgreSQL positions, ledger and valuation are real.
They are not evidence that calibrated production market recommendations exist.
Focused market result: 11 passed, 4.75 seconds. Broader PostgreSQL runtime,
backtesting and receipt/report regression result before the additional optional
cost guard: 200 passed, 7 skipped, 145.55 seconds. The optional-cost guard had
its own failing regression (None estimate caused TypeError), then passed with
all 11 market tests. The seven historical acceptance gates remain skipped.
Graphify AST update succeeded; schema synchronization verified 22 PostgreSQL
tables without migrations. SQL AST support is unavailable; no dependency
installation was attempted. Organizer SHA-256 remains
`2e7c1d2e5b678e9975250211e7e0017022049c510e1dd90cd7f29e931837b0c5`.

Reproduce focused and integration verification:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:BACKTEST_TEST_DATABASE_URL='postgresql+psycopg2://postgres:postgres@127.0.0.1:5432/reserve_juggler_m2_test'
& 'D:\Hackathon\projects\reserve-juggler\.venv\Scripts\python.exe' -u tests/backtesting/run_postgres_suite.py tests/integration tests/backtesting -q -p no:cacheprovider --tb=short
```

Historical comparisons remain blocked: capped/unpaid payout execution and its
Agent 2 receipt adaptation, conservative market-data availability, Member 1
publication/calibration confirmation, deferred settlement, unsupported repo/
borrowing recommendation actions, seven gated historical acceptance cases and
RJ-M1-16 owner acceptance still require verification. Passing unit tests or
unlimited-borrowing runs are not release approval.

## Capped financing and payout receipt v1

Emergency principal drawn never exceeds
`max(0, max_overdraft_cents - existing outstanding principal)`.
Disabled borrowing has zero capacity. Unpaid interest is a separate liability,
not silently capitalized principal or income. Run-level row locking serializes
execution, capacity checks and step idempotency. Existing above-cap debt is
preserved but cannot draw additional funds.

Backend TreasuryPolicy / PolicyPatch expose allow_overdraft and
max_overdraft_cents using existing Member 1 names. Defaults remain enabled /
5,000,000,000 cents. Disabling without an explicit limit sets zero; a positive
explicit limit with disabled borrowing is invalid. OpenAPI is regenerated;
frontend and Member 1 source remain unchanged.

`TreasuryDecision.decision_details_json.payout` is frozen per completed hour:
receipt_version=runtime-execution-v1, run_id, step, recommendation_reference
(null for customer instructions), source_observation_timestamp,
requested_amount_cents, executed_amount_cents, unpaid_amount_cents, status,
settlement_status, reason, cash_delta_cents, fees_cents, realized_pnl_cents,
overdraft_draw_cents, borrowing_outstanding_cents, unpaid_financing_cost_cents,
remaining_financial_liability_cents, ledger_entry_ids,
overdraft_ledger_entry_ids, automatic_retry=false.

| Actual funding | status | settlement_status |
| --- | --- | --- |
| All requested cents paid | EXECUTED | PAID |
| Some, not all, paid | PARTIALLY_EXECUTED | PARTIALLY_PAID |
| None paid | FAILED | UNPAID |

An unpaid request has no cash leg, no invented overdraft liability and no
financing charge on its unpaid portion. It remains an unresolved customer
payment instruction in its persisted receipt, not a funded payment.
There is no automatic resubmission or claim of successful fulfillment.
Consumers must surface unpaid requests; retained cash or smaller paid outflows
are not strategy profit. NAV remains the existing financial-asset/borrowing
balance sheet, not a newly invented customer-deposit accounting model.
Payment-obligation settlement/retry and its balance sheet treatment need an
explicit integration contract before release.

Decision execution_status is FAILED or PARTIALLY_EXECUTED when unpaid, never
EXECUTED. Actual payout ledger legs sum to executed_amount_cents. A residual
shortfall produces LiquidityBreach even when borrowing is disabled. Only
actual draws produce OverdraftLiability/BORROW rows; cash stays nonnegative.
Reallocation orders are rejected while the current payout is unpaid.

`decision_details_json.financing[]` links each actual OverdraftMovement by
movement_id, liability_id, run_id, step, kind, status (ACCRUED for expenses,
EXECUTED for cash legs), reason, principal_cents, financing_cost_cents,
cash_delta_cents, ledger_entry_id, outstanding_principal_cents and
unpaid_financing_cost_cents; recommendation_reference is null for automatic
emergency funding/settlement. BORROW, REPAYMENT and FINANCING_COST rows remain
authoritative. Principal repayment does not erase unpaid expense; fee payment
is a separate cash debit/REPAYMENT financing-cost field, not another expense.
Closing NAV deducts principal plus unpaid expense.

Fail-first evidence: five payout regressions failed against the market
checkpoint (over-cap/disabled borrowing, absent receipts and disabled-policy
default). Public policy configuration separately failed on forbidden fields
before the additive backend policy fields.

Compatibility evidence: unchanged Agent 2 endpoint regressions
`test_public_backtest_retains_fields_and_honors_requested_subset` and
`test_backtest_repeat_is_ephemeral_and_preserves_parent` now fail with 422:
Requested customer flow lacks complete settled-payout ledger legs.
Their windows exhaust the real principal cap. This is the older receipt
reader rejecting actual unpaid payouts, not grounds to bypass the cap or
fabricate successful payments. Agent 2 must extend its receipt/accounting
contract and endpoint acceptance to expose unpaid requests explicitly.
Its implementation and tests remain untouched. Historical comparisons stay blocked.

Checkpoint verification: new market/payout cases and preserved diagnostic/
accounting probes: 47 passed, 2 explicitly deselected in 20.99 seconds.
The two deselections are exactly the endpoint incompatibilities above; the
unfiltered run recorded 47 passed / 2 failed, not a green integration result.
Graphify refreshed successfully (2098 nodes / 6093 relationships). No push.
