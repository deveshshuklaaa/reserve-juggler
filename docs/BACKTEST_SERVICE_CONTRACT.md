# Historical backtest service contract

Status: orchestration implemented; shared-runtime integration **pending Agent 1**.
This is a Python service boundary, not a new API, simulator, strategy algorithm,
database model, or replacement for Member 1's canonical portfolio contracts.

## Verified base and ownership

Implementation base: feat/simulation-backend,
52e58bcfcad766a1444b37a175b48158fd645409.
No use of unverified integration b3cc3d7. No finished integration base has been
merged. Work belongs on the isolated feat/backtesting-engine worktree.

Existing dependencies are app.data.organizer.OrganizerDatasetSource and its
immutable HourlyObservation, plus Python 3.10+ and the existing Pydantic 2
dependency. No database, API, frontend, intelligence, or forecasting imports.
The four-tier amounts in EngineState are an accounting projection of the shared
engine's actual portfolio, NOT another position/quantity/rate contract.

Source: treasury_4tier_dataset.csv, 8,760 hourly rows, 16 columns. Required SHA-256:
2e7c1d2e5b678e9975250211e7e0017022049c510e1dd90cd7f29e931837b0c5.

The existing loader reads and validates the source. The service loads it once
per comparison and uses the same immutable object for all strategies. No source
rows, precision, supplied net_flow_usd or one-cent reconciliation differences
are corrected, regenerated, resampled or persisted by this package. All source
financial quantities remain Decimal; observation JSON uses exact decimal strings.

## Calling interface

Modules:

- app.backtesting.contracts: request, immutable receipt/state and result models.
- app.backtesting.protocol: proposed hourly-backtest-v1 injectable protocol.
- app.backtesting.service: BacktestService.compare and fail-closed exceptions.

Example (shared_factory must be supplied by Agent 1; no default is installed):

~~~python
from datetime import datetime
from uuid import uuid4
from app.backtesting import BacktestRequest, BacktestService, ScenarioSpec

request = BacktestRequest(
    comparison_id=uuid4(),
    start=datetime(2026, 1, 1),  # source time: no timezone assumption
    days=7,
    initial_capital_cents=2_000_000_000,
    seed=42,
    scenario=ScenarioSpec(name="NORMAL"),
    policy_json='{"reserve_fraction":"0.20"}',
)
result = BacktestService(shared_factory).compare(request)
wire_json = result.model_dump_json()
~~~

The synchronous service returns ComparisonResult, with all three strategies in
stable order: STATIC, REACTIVE, RESERVE_JUGGLER. It does not expose an endpoint.

Request requirements:

- comparison_id: caller-supplied UUID, identifying one comparison. Repeating an
  identical request gives deterministic run IDs (UUIDv5(comparison_id, strategy)).
  Use a new comparison ID for changed conditions. A factory must create a fresh
  isolated run, or reproducibly replay that identical run from its beginning;
  it must never silently resume partially executed state.
- start: explicit naive ISO timestamp/datetime, exact source hour.
- days: strict integer 7, 14 or 30 => 168, 336 or 720 hourly executions.
- initial_capital_cents: nonnegative integer cents; all strategies start entirely
  in Tier 0, zero positions, zero accrued income, zero market P&L and zero debt.
- seed: nonnegative safe integer; a per-run RNG must not depend on strategy run
  order or a mutable global RNG.
- scenario: NORMAL, HIGH_WITHDRAWAL, LOW_DEPOSIT, SETTLEMENT_DELAY or
  LIQUIDITY_SHOCK, plus parameters_json (default empty JSON object).
- policy_json: default empty JSON object. Policy/scenario settings are immutable
  canonical JSON strings, with sorted keys. Reject duplicate keys, floats,
  nonfinite numbers and unsafe integers, including nested values. Encode exact
  rates/multipliers as decimal strings. These strings are configuration fields,
  not JSON money results; monetary results are strict integer cents.

The selected interval is [start, start + days). Both month/year boundaries and
non-midnight start hours are supported if every selected row exists. No invented
UTC conversion, 15-minute interpolation, padding or partial periods. A start of
2026-12-02 with 30 days is valid; 2026-12-26 with 7 days is incomplete.

ComparisonResult records source identity/hash, start/end_exclusive, steps,
native_interval_seconds=3600, time_basis=UNSPECIFIED, capital, seed, scenario,
canonical policy, conditions_sha256, provider engine_version and integration SHA.
The conditions hash covers source, window, capital, seed, policy, scenario and
engine/protocol provenance, and is common to all three strategies. Each run has
its own run_id. Results cannot contain partial/missing strategies.

## Required Agent 1 hourly provider (proposed, not an agreed published interface)

HourlyEngineFactory has:

~~~python
capabilities: EngineCapabilities
def start(spec: RunSpec) -> HourlyRun: ...

# Returned HourlyRun:
spec: RunSpec
initial_state: EngineState
def decide(frame: DecisionFrame) -> object: ...
def execute(frame: ExecutionFrame, decision: object) -> HourReceipt: ...
def close() -> None: ...
~~~

RunSpec contains comparison/run identity, strategy, interval/steps, initial
capital, seed, scenario, policy JSON, dataset ID/hash and common conditions hash.
It contains no dataset object, CSV path or future observation values.

EngineCapabilities must identify protocol_version=hourly-backtest-v1,
engine_version, execution_kind, integration_sha, supported strategies and
scenarios. A SHARED provider requires a full 40-character lowercase commit SHA;
this validates syntax, not publication. Publication must be verified separately.
A TEST_DOUBLE must have a null integration SHA. It is rejected unless the caller
explicitly sets allow_test_double=True; that option is for unit tests only.
Results preserve TEST_DOUBLE labeling. Missing provider/capabilities fails with
SharedEngineUnavailable; there is no hidden fallback or fabricated result.

Per source hour, in this order:

1. decide receives step, timestamp and only rows strictly BEFORE that timestamp.
   This includes pre-window history for causal warm-up, not execution or earnings.
2. After the opaque decision token returns, execute receives step, the current
   immutable HourlyObservation, and its source_digest.
3. The shared engine applies the chosen strategy/scenario via its **same** hourly
   ledger/execution path used by simulation and returns an accounting receipt.
4. The service validates the receipt, state continuity, source binding and audit
   uniqueness, then collects one closing checking point.

source_digest is SHA-256 of UTF-8 json.dumps(observation.model_dump(mode="json"),
sort_keys=True, separators=(",", ":")). It is a normalized observation identity,
not a hash of one raw CSV line. Dataset SHA separately verifies raw CSV bytes.

The decision cannot receive the current hour's realized flows or later market
prices. A historical decision cannot use eventual settlement outcomes, delayed
deposits, or completed future intervals. The engine may use its own executed
past state and causal scenario history. Raw pre-window history is not synthetic
portfolio activity and cannot create interest or gains before the requested run.
Current-hour operational rescue after an actual payout is an execution event,
not permission to reforecast with future observations.

This is an information boundary, not a sandbox: a malicious provider can still
read disk independently. Agent 1 must guarantee causal forecasting, training and
scenario transformations internally. No prediction/model evaluation score is
available from this interface.

All scenario transformations and STATIC/REACTIVE/RESERVE_JUGGLER action policies
belong to the shared engine, not the backtester. They must be versioned and
published by Agent 1. Scenario severity/delay distributions, rounding, trade
fills, repo entry at 17:00/maturity at 08:00, early breaks, bond/index marks,
equity marks, duration/volatility, overdraft APR accrual, and liquidation policy
are **not invented here**. A capability declaration alone is not evidence those
behaviors are financially correct.

The service always calls close on a returned run, including failures. The engine
owns transactions, rollback, resource cleanup and persistence/idempotency policy.
If start fails before returning a run, the factory must clean up itself.
No partial comparison is returned after any failure. Partial persisted runs, if
any, must be marked failed/cleaned by the engine, never silently treated complete.

## EngineState accounting projection

Every field is required; no missing quantity defaults to zero:

| Field | Meaning |
| --- | --- |
| checking_cents | Nonnegative Tier 0 closing cash, not borrowing-adjusted profit |
| tier1_value_cents | Tier 1 carrying/market amount, including any booked accrued income |
| tier2_value_cents | Tier 2 marked asset amount, including any booked accrued income |
| tier3_value_cents | Tier 3 marked asset amount |
| borrowing_outstanding_cents | Outstanding borrowed principal, a liability |
| unpaid_borrowing_costs_cents | Incurred financing expense not yet paid, separate liability |
| accrued_interest_cents | Signed unpaid interest already included in tier asset amounts |
| unrealized_market_pnl_cents | Signed unrealized market P&L already included in asset amounts |
| net_asset_value_cents | Sum of four tier asset amounts minus both liability fields |

Accrued income and unrealized P&L are explanatory sub-balances; never add them a
second time to gross assets. Neither equity appreciation nor borrowing is interest.
Financing cost cannot be hidden by capitalizing it into principal in this
projection: separate the original borrowing and accrued expense explicitly.

## HourReceipt: one actual hour, not cumulative metrics

All fields in HourReceipt are mandatory. Deltas are that hour's actual postings.
Stocks are opening/closing EngineState, with the previous close equal to the next
open. timestamp must exactly equal the executed source row. event_ids are stable,
nonblank, unique within a run, and mandatory for every changed state, nonzero
financial posting or counted event. No-op hours may report an empty tuple.
IDs must reference the provider's actual audit entries, not invented row labels.

Signed monetary deltas:

- customer_cash_delta_cents: actual settled customer inflows minus paid customer
  outflows, excluding financing and investments. Failed payouts are not paid
  outflows; settlement delays must affect actual settlement, not rewrite source.
- investment_cash_delta_cents: gross cash from investment sales/maturities minus
  acquisition cash, excluding separately reported interest, all costs and debt.
- financing_cash_delta_cents: borrowed principal minus principal repayments.
- realized_interest_cents: interest actually realized/paid to Tier 0 this hour;
  not equity gains, asset sale proceeds or unrealized interest.
- realized_market_pnl_cents: gross realized market P&L before liquidation friction.

Nonnegative monetary deltas:

- contractual_penalties_cents: e.g. repo early-break cost.
- liquidation_losses_cents: explicit haircuts/slippage, not market price losses.
- transaction_costs_cents: other explicit trading costs, disjoint from the above.
- borrowing_costs_cents: financing expense INCURRED this hour, whether paid or not.
- paid_borrowing_costs_cents: financing expense PAID this hour; never counted again
  as an incurred expense merely because it was paid.

Nonnegative event counts: reserve_breaches, emergency_events, failed_payouts,
sweeps. The provider must define incident counting (not infer counts from balances)
and supply auditable occurrences. Event/cost categories must not overlap or double
count the same expense.

The receipt validates these integer-cent identities:

~~~text
closing cash = opening cash + customer delta + investment cash delta
             + financing cash delta + realized interest
             - contractual penalties - liquidation losses - transaction costs
             - financing expense paid

closing principal = opening principal + financing cash delta
closing unpaid financing expense = opening unpaid expense
                                + expense incurred - expense paid

economic benefit = realized interest + change in accrued interest
                 + gross realized market P&L + change in unrealized market P&L
                 - contractual penalties - liquidation losses - transaction costs
                 - financing expense incurred

closing NAV - opening NAV - customer delta = economic benefit
~~~

When accrued income realizes, report realized interest and reduce the accrued
stock: it is not earned twice. When a marked asset is sold, reduce its unrealized
P&L stock and report gross realized P&L: a previously recognized gain is not earned
twice. Report gross sale proceeds before haircut, with haircut in its own cash
cost leg. Debt draws increase cash AND principal, never NAV income. Paying an
already accrued financing expense reduces cash AND unpaid liability, not NAV twice.

The backtester performs no fill, accrual, market valuation or source-to-cent
rounding. The provider must publish those rules and return already posted cents.
Inconsistent or missing accounting fails, rather than estimating missing metrics.

## Returned metrics per strategy

| Field | Definition |
| --- | --- |
| realized_interest_cents | Sum of actual realized-interest deltas, signed for negative rates |
| average_checking_cents | Arithmetic mean of hourly closing cash, rounded once half-up to cents |
| penalties_cents | Sum of contractual penalties AND liquidation haircuts/slippage |
| borrowing_costs_cents | Sum of financing expense incurred, not both incurred and paid |
| borrowing_outstanding_cents | Final principal stock, NOT the sum of hourly debt balances |
| reserve_breaches / emergency_events / failed_payouts / sweeps | Sums of actual event counts |
| net_benefit_cents | Ending NAV minus initial capital minus net settled customer cash flows |
| history | Exactly steps points: timestamp and checking_cents |

Additional explicit fields prevent misleading aggregate results:
contractual_penalties_cents, liquidation_losses_cents, transaction_costs_cents,
realized_market_pnl_cents, accrued_interest_cents (change since start),
unrealized_market_pnl_cents (change since start), unpaid_borrowing_costs_cents
(closing stock), ending_net_asset_value_cents, customer_cash_delta_cents,
strategy, run_id, and model_evaluation=null.

Net benefit includes unrealized marks/accrual as well as realized income and
incurred expenses; it is not labeled realized trading profit. Liquidation of all
positions or repayment of all debt is NOT assumed at the end. Ending debt and
unpaid financing costs remain visible and deducted from NAV. Average cash includes
cash funded by borrowing; compare it alongside debt, not as proof of solvency.
History labels each **post-step** balance with its source-row timestamp (no
additional initial point). Its source interval is still exactly one hour.

All monetary fields are strict integers in [-9007199254740991, 9007199254740991],
nonnegative where their semantics require it. Booleans, numeric strings and
floating point are rejected, including deserialized/copied nested models.
Gross asset sums and cumulative result amounts must also fit. Overflow fails;
no saturation, float conversion or silently missing costs. Counts are nonnegative
safe integers. Only the average-checking display metric is rounded by this service.
Models are frozen, forbid extra fields and round-trip through JSON.

## Testing and pending integration

Unit tests in tests/backtesting/fakes.py use explicitly scripted journal entries.
They DO NOT calculate strategies, actual source cash flows, repo timing, prices,
scenario economics or APR. Their results are not historical performance claims.

Coverage includes 7/14/30-day counts, equal conditions and fresh runs, deterministic
results, no-lookahead frames and warm-up, all scenario routing, source hash and
all-field integrity, source residual preservation, calendar edges, serialization,
strict money/config validation, signed losses, market/interest accrual reversals,
liquidation cost, borrowed cash versus NAV, financing incurred/paid/unpaid, closing
debt versus cumulative debt, audit deduplication, failures/resource cleanup, and
cumulative safe-integer limits.

Use the existing project Python environment, with no dependency changes:

~~~powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:DATABASE_URL='sqlite:///:memory:'
python -m pytest tests/backtesting -q -p no:cacheprovider --tb=short
python -m pytest tests/backend/test_organizer_data.py tests/integration/test_treasury_pipeline.py -q -p no:cacheprovider --tb=short
python -m pytest -q -p no:cacheprovider --tb=short
~~~

Existing PostgreSQL regression tests separately require
PERSISTENCE_TEST_DATABASE_URL pointing at the documented disposable test server;
an in-memory SQLite URL does not validate PostgreSQL migrations.

tests/backtesting/test_shared_engine_integration.py is explicitly pending/skipped
unless a real dependency is configured. It never falls back to the unit fake.
Agent 1 must first publish:

1. Actual branch and full remotely verifiable 40-character commit SHA.
2. File/module path and zero-argument provider factory (or publish a shared
   interface we can reconcile without duplicating its execution logic).
3. Actual initial-state, one-hour result and audit-receipt schema.
4. Agreed strategy/scenario semantics, causal data boundaries, posting/rounding
   policy and ledger mapping for all receipt categories.
5. Supported run-isolation/reset/idempotency/resource lifecycle.

After verifying that publication, merge/rebase the agreed finished integration
base, reconcile this proposed protocol if necessary, and set:

~~~powershell
$env:BACKTEST_SHARED_ENGINE_BRANCH='<verified published branch>'
$env:BACKTEST_SHARED_ENGINE_SHA='<verified full commit SHA>'
$env:BACKTEST_SHARED_ENGINE_FACTORY='published.module:factory'
python -m pytest tests/backtesting/test_shared_engine_integration.py -q -p no:cacheprovider --tb=short
~~~

The factory may configure its own test database and shared dependencies; this
workstream does not create them. Integration tests require SHARED execution,
matching SHA, all strategies, reproducibility, complete hourly windows and
source integrity across all five scenarios and 7/14/30-day coverage. They exercise
the service/receipt identities, but Agent 1 must also test actual timing, fill,
scenario, forecasting and ledger economics in its engine suite.
No runtime integration SHA or real historical comparison is claimed yet.

## Graphify handoff and file boundaries

Repository Graphify is already configured in graphify-out/ with the organizer
and persistence milestones. Those files and scripts/sync-persistence-graph.py
were inspected; no graph was used as evidence of runtime implementation.

Repository graph regeneration is deferred because this workstream is explicitly
restricted to backend/app/backtesting/, tests/backtesting/ and this document.
It would modify owned files outside that list. No separate Graphify project was
created and no synchronization success is claimed. The integration owner can
run the existing repository-level update after combining workstreams.

Actual relationships to add then:

- BacktestService -> OrganizerDatasetSource -> immutable HourlyObservation.
- BacktestService -> BacktestRequest / ComparisonResult / StrategyMetrics.
- BacktestService -> injectable HourlyEngineFactory / HourlyRun.
- HourlyRun -> HourReceipt -> opening/closing EngineState accounting projection.
- Unit tests -> scripted receipt fixture (test-only).
- Opt-in integration tests -> proposed shared-provider protocol (pending).

Do not draw an implemented edge to a concrete hourly runtime, strategy economics,
database, API endpoint, frontend or Member 1 engine until actual code exists.
