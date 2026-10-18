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

## Confirmed publication and delayed repo convention

Member 1 confirmed the availability convention during this work:
`row.timestamp + 1 hour + publication_delay <= decision_at`.
Public policy / patch field publication_delay_seconds defaults to zero and
accepts nonnegative integer seconds. Source timestamps remain naive with
time_basis=UNSPECIFIED. At 09:00 with zero delay, 08:00 is eligible and 09:00
is not. With a one-hour delay, 07:00 is the latest eligible row.

The same cutoff gates cashflow forecast history, REACTIVE history, published
market/rate quotes, direct risk inputs, calibration-through timestamps and
canonical optimizer requests. The first dataset hour still executes; its
opening canonical optimizer input has no published market quotes. Its required
source reference is provenance only, not an assertion that the first row is
available. No synthetic prior row or timezone is invented.
The allowance remains explicitly named fallback-baseline-v1, not an
empirically calibrated model; model_evaluation remains null.

Market fills now reference the canonical recommendation's actual published
source quote. The simulation's explicit fill convention uses that available
index at one USD/index-point/unit, not an unavailable same-hour price.
quote_observation_timestamp and quote_available_at are recorded in each fill.
Closing marks and emergency liquidation quotes use the last row published by
the closing boundary; new debt uses its available APR. With no published APR,
the payout remains unpaid rather than borrowing at an invented rate.
Cashflow application remains actual shared-ledger execution; unknown future
cashflows are not passed as forecast features or opening cash.

Repo entry remains 17:00, with the APY and early-break fee available then;
maturity remains 08:00. Confirmed **simulation convention**, not an assertion
about the actual organizer instrument:

1. For each earned interval [h,h+1h), freeze the latest source APY satisfying
   `source_time+1h+delay <= h+1h`.
2. Carry forward that last eligible APY if the earning-hour rate is unpublished.
3. Accumulate selected Decimal APYs, apply simple ACT/365, round aggregate
   interest once (HALF_UP cents). Zero-delay results retain the verified
   source-hour convention.
4. At contractual maturity settle principal plus that frozen earned amount.
   There is no automatic later true-up or rewriting of past receipts.

MATURITY InvestmentMovement / REPO_MATURITY_CREDIT remain actual settlement
evidence. The decision's maturity receipt now adds position_id, interest_cents,
hourly_rates[] (earned_at, accrual_cutoff, rate_observed_at, rate_available_at,
apy_pct) and automatic_true_up=false. All rate strings retain source precision.

Availability metadata is persisted under decision_details_json.availability:
rule=completed-source-hour-v1, status=MEMBER1_CONFIRMED, delay seconds,
decision_at, observation_cutoff, opening/closing market observation timestamps,
named fallback calibration and null model evaluation.

Agent 2/public projection handoff: FourTierPortfolioSnapshot adds
market_data_available, market_observation_timestamp, publication_delay_seconds.
Source-derived price/rate/duration display fields can be null when no quote
has been published. This prevents invented initial prices/APYs; monetary
balances remain integer cents. Agent 2 must verify these nullable quote fields
in its frontend integration. No frontend or backtesting implementation is edited.

Fail-first evidence: two optimizer availability cases initially failed; direct
risk initially accepted unpublished quotes; a positive-delay closing mark used
an unpublished price; delayed repo execution initially produced no repo.
All have focused regressions. The existing calibration test now supplies the
available decision view rather than an unpublished raw closing observation.
The original future-calibration rejection assertion is preserved.

Focused PostgreSQL result: 34 passed in 25.49 seconds (market-data availability,
delayed repo, market fills, payouts and strategy dispatch). Additional closing
fee-source edits only replace the unavailable current-hour fee with the same
published entry quote; they will be included in final verification.
The positive-delay maturity test verifies selected rates, exact interest,
08:00 credit, cash/NAV, and no second settlement after late publication.

Remaining gates supersede earlier historical notes: Agent 2's new receipt/
unpaid-payout and nullable-quote compatibility; calibrated quantitative reward/
risk assumptions; complete historical acceptance and RJ-M1-16 owner sign-off.
The publication convention itself is now confirmed, not an open question.

Exact final availability checkpoint focused rerun: 34 passed in 26.63 seconds,
including the published entry-fee changes. Graphify verified 22 PostgreSQL
tables and indexed 2117 nodes / 6198 relationships.

## Snapshot projection follow-up

Five fail-first projection cases cover initial unavailable quotes, next-hour
quote leakage, missing financing expense in NAV, non-cumulative repo accrual,
and omitted partial-sale P&L/benefit. All pass after the projection correction.
The held-repo fixture explicitly zeros source flows in its rollback-only
database so that it really exercises multiple earned hours rather than an
already redeemed position. The organizer file is never changed.

GET snapshot now uses the same available canonical portfolio and exact
remaining cost basis as execution. Gross assets include accrued repo interest;
liabilities include principal plus unpaid financing expense. Fee-only debt
remains ACTIVE until settled. The latest persisted reserve target is used.
Public forecast metadata no longer claims evaluated-gb-v1 for the actual
hourly-seasonal-naive-v1 runtime.

Shared read-only financial_performance derives economic benefit as
`NAV - initial capital - actual settled customer cash delta`.
This reconciles actual fees, market gains/losses, interest and financing expense
without treating borrowing as income or unpaid requests as paid outflows.
Gross realized return is separately reported before fees. It does not invent
a second financial executor or replace Agent 2's detailed report accounting.

An aggregate acquisition_price is now null for zero or mixed-price open lots;
there is no single truthful acquisition index in those cases. One-price open
lots expose their actual Decimal index string. Position receipts retain every
lot's actual acquisition quote. Agent 2 must handle this nullable aggregate
display field in addition to nullable unpublished market quotes.

Focused snapshot/live-route PostgreSQL verification: 15 passed in 12.33 seconds.

Additional Agent 2 gate: its runtime provider still pins RUNTIME_SHA and
engine_version to 1ff1e655070d6b13e24c060d30c9782457d01598. It must pin the
new core checkpoint when adapting receipts. A healthy response from that old
provider is not evidence of the new runtime's provenance or full historical
acceptance. This file is the handoff because no verified messaging destination
was provided; no Agent 2 implementation or branch is changed.
