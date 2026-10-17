# Historical backtest service contract

Status: orchestration, persisted receipt/report integration and real PostgreSQL
probes implemented. **Full historical strategy comparisons remain blocked.**
Current runtime checkpoint: **dee0aae3cbd77ed4ad4e6f0961b9594ad53461d2**.
The final independent-checkpoint verification below is authoritative; earlier
082f019/483936c reviews and expectations are retained as historical evidence.
This is a Python service boundary, not a new API, simulator, strategy algorithm,
database model, or replacement for Member 1's canonical portfolio contracts.

## Verified base and ownership

Original base: feat/simulation-backend,
52e58bcfcad766a1444b37a175b48158fd645409; initial backtesting implementation:
35741cea1993fb6ee665a10a572c75b3b44a0abd.

Initial runtime: 082f0190a015298d63583d65a0b216a465b93ce1, based on 4a85674.
Verified follow-up: 483936c7e8d6c37c682886deb2e17503bf6d752c, a descendant of
082f019, merged locally as 94272ddae0738a63811556a96400ce95527996ec. This merge
retains the receipt/report commit 2342501 and handoff commit 19c7326 unchanged.
The exact commits were confirmed in the same Git object database. No GitHub fetch of a
local-only SHA, no develop/main checkout changes, and no push. Runtime code and
shared contracts arrive unchanged through the dependency merge, not owned edits.

Core orchestration uses app.data.organizer.OrganizerDatasetSource and immutable
HourlyObservation, Python 3.10+ and Pydantic 2. The optional runtime/report modules
also use existing SQLAlchemy/PostgreSQL models, the shared hourly callable, and
read-only imports of app.v1_contracts. Those modules transitively depend on
Member 1 through the unchanged executor. No frontend or route implementation is
imported or modified. No new dependency installation is required.
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
- app.backtesting.service: BacktestService.compare, summarize_receipts and exceptions.
- app.backtesting.runtime: execute_persisted_hour, read_hour_receipt and dependency guard.
- app.backtesting.reports: BacktestReportService, projections and deterministic sampling.

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

## Strategy-provider protocol (proposed; complete provider still blocked on 483936c)

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
average_invested_cents (mean of all tier investment asset amounts),
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

The original SEVEN cases in tests/backtesting/test_shared_engine_integration.py
are preserved as pending acceptance criteria. They require a complete causal
strategy provider and never fall back to the unit fake. The local runtime exists,
but its callable is not sufficient to satisfy that protocol. Agent 1's follow-up
must provide:

1. Actual local object-database commit SHA (or fetchable published branch/SHA).
2. Explicit STATIC/REACTIVE/RESERVE_JUGGLER dispatch through the shared engine.
3. Causal forecasting that cannot query current/future realized observations.
4. Complete hourly initial/closing state, P&L, payout and financing receipts.
5. Agreed start-window, isolation/reset/idempotency and resource lifecycle.

The user is coordinating that follow-up on develop. Do not fetch local-only
SHAs from GitHub, relabel identical executions as distinct strategies, change
the strategy capability guard, or substitute an alternate financial executor.
After verifying and integrating the follow-up, reconcile the protocol and set:

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
The verified runtime SHA is recorded above and used by the persisted-path tests.
No complete historical strategy comparison is claimed yet.

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
- runtime.execute_persisted_hour -> services.hourly_engine.execute_hourly_step.
- runtime.read_hour_receipt -> existing persisted accounting records.
- reports.BacktestReportService -> shared receipt aggregation / frontend projections.
- PostgreSQL integration tests -> actual shared executor and migrated test databases.
- Opt-in SEVEN comparison cases -> proposed shared-provider protocol (pending).

Do not draw an implemented full-comparison, strategy-dispatch or API route edge.
Concrete database/runtime/report relationships above now exist; strategy economics
and causal forecasting still belong to Agent 1, with no substitute implemented here.


## Historical baseline runtime audit (082f019; superseded by follow-up review below)

The inspected callable is:

~~~python
execute_hourly_step(
    session: sqlalchemy.orm.Session,
    run_id: UUID,
    expected_step: int | None = None,
) -> dict[str, Any]
~~~

It mutates records and flushes; it does not commit. StepConflictError carries
expected_step/current_step. Its return is a display snapshot, NOT HourReceipt.
It contains run_id, step, wall-clock UTC timestamp, status, checking/vault/reserve
amounts, policy, decision, forecast and four_tier dictionaries. Some displayed
return totals are placeholders; report accounting never trusts those totals.

Persisted evidence inspected and consumed:

| Existing model | Receipt role |
| --- | --- |
| SimulationRun / CashAccount | Run/source/step identity and current Tier 0 balance |
| OrganizerObservation / DatasetSource | Exact source values/provenance and source clock |
| LedgerEntry | Posted cash entries, before/after balances, source hour, audit IDs |
| InvestmentMovement | Investment, repo maturity/redemption, actual interest/haircut postings |
| PortfolioValuation | Opening/closing tier asset and principal/debt amounts |
| TreasuryDecision | Hour identity and expected scenario-adjusted flow amounts |
| LiquidityBreach | Recorded shortfall incidents, not inferred hours below reserve |
| OverdraftLiability / OverdraftMovement | Outstanding debt, borrow/repay linkage and cost evidence |
| BondPosition / EquityPosition / PositionValuation | Required future market-P&L attribution; incomplete for this runtime |

runtime.execute_persisted_hour(session, run_id, expected_step) calls the actual
shared executor inside a savepoint, then builds a strict HourReceipt from records.
A receipt error rolls back that hour, including new debt/breach rows. It never
posts compensating entries or changes runtime financial rules. The caller owns
the outer transaction. StepConflictError propagates unchanged.

runtime.read_hour_receipt(session, run_id, step) is read-only reporting. It
requires an existing complete hour with exactly one opening/closing valuation,
one decision, known cash kinds and linked movement evidence. It verifies actual
settled customer ledger amounts against the decision and reuses all original
cash/NAV/debt/interest identities.

The currently validated subset is cash/repo with no unsupported market positions
or unresolved financing cost. Repo accrued income is the persisted difference
tier1_value minus principal, NOT an independent accrual calculation. Zero market
P&L, transaction cost, failed payout and financing expense are emitted only for
that proven restricted path with complete settled flows and no corresponding
positions/cost evidence. Unknown entries, missing legs, nonzero un-attributed
market amounts, incomplete financial fields or financing receipts fail closed.

An existing mutable debt-cost accumulator cannot establish historical incurred,
paid and unpaid cost flows. The adapter rejects it, rather than treating it as
free cash, assigning it to income, inventing a financing event ID, or revaluing
the portfolio itself. Audit IDs reference actual model primary keys.

### Historical baseline defects for Agent 1 (not all remain on 483936c)

These are diagnoses of unchanged code, not fixes in this workstream:

1. get_hourly_forecasts_from_db queries timestamp >= as_of, then copies current
   and future observed customer flows into forecast points. A real database probe
   demonstrates the future row becomes a prediction.
2. execute_hourly_step has no strategy argument/dispatch and does not consume
   RunSpec.strategy. SharedRuntimeFactory therefore advertises **zero validated
   strategies** and refuses comparison. It is not a placeholder financial engine.
3. First execution uses source_start_timestamp + one hour. source_start_timestamp
   is constrained to an existing observation, so a comparison beginning at the
   very first CSV row cannot be aligned by simply moving the start marker back
   one hour. No fake preceding observation or negative step is inserted.
4. On a liquidity shock, the runtime persists the shortfall, borrowed principal
   and financing cost, but the customer withdrawal ledger contains only the
   cash-funded portion. The financed payout remainder lacks a complete payout
   leg. The diagnostic shock test verifies records, NOT complete accounting.
5. Financing cost accumulates on OverdraftLiability without hourly FINANCING_COST
   movement/payment evidence; PortfolioValuation subtracts principal only.
   Full borrowing reports therefore cannot reconcile all expenses honestly.
6. Repayment writes OverdraftMovement.kind="REPAY", while the actual PostgreSQL
   constraint accepts BORROW, REPAYMENT, FINANCING_COST. A real two-step shock /
   recovery probe reproduces SQLSTATE 23514.
7. Early redemption accesses RepoPosition.early_break_fee_bps, but the ORM exposes
   early_redemption_haircut_pct. A real sweep-then-shock path reproduces
   AttributeError. No runtime field aliases or monkey patches were added.
8. Runtime market amounts lack sufficient persisted per-position P&L attribution
   for historical receipt reconstruction. The report adapter rejects those runs.

The passing diagnostic tests assert these defects are reproducible. They are not
claims that repayment, early redemption, forecasting or full shock accounting is
correct. Update these diagnoses to positive acceptance assertions when Agent 1's
follow-up actually fixes them.

### Report service and frontend projection

reports.BacktestReportService.compare(BacktestRequest, history_limit=100)
uses the existing injectable orchestration and fails BEFORE any strategy starts
with current SharedRuntimeFactory. Unit tests may explicitly inject the test
backtester; TEST_DOUBLE provenance and null integration SHA remain visible.

reports.BacktestReportService.report_run(session, run_id, history_limit=100)
reads existing persisted execution; it does not advance a run. Missing run raises
KeyError; incomplete evidence raises RuntimeReceiptUnavailable. No executed steps
means metrics/accounting are null and history is empty, not fabricated zero
performance. Untagged runtime runs are not mislabeled as a named strategy.

The richer owned BacktestReport / RunReport extend the existing shared envelope
fields. Public aliases are STATIC -> STATIC_RESERVE and REACTIVE ->
REACTIVE_RESERVE; RESERVE_JUGGLER is unchanged. Legacy FinancialMetrics mappings:

- average_vault_cents <- average_invested_cents (Tier 1/2/3 mean marked asset sum).
  This is a deprecated transport alias, not a generic vault execution model.
- redemption_penalties_cents <- contractual + liquidation costs.
- emergency_borrowing_cost_cents <- incurred borrowing cost.
- unpaid_cents <- actual unpaid customer payouts, NEVER outstanding borrowing.
  Debt and unpaid financing expense remain separate accounting fields.
- Other matching shared metrics retain their existing names and meanings.

HourReceipt and AccountingTotals include explicit unpaid_payouts_cents for this
legacy projection. It is not a cash outflow or an interest expense. Missing paid
customer legs do not justify estimating it: incomplete evidence still fails.
Signed net benefit is preserved. Legacy shared interest/accrual fields disallow
negative values: projection rejects unsupported negative-interest results, never
clamps them. The core receipt/metrics contract remains signed for negative rates;
shared-contract alignment for that case belongs to its owner.

Each result additionally exposes accounting totals with the required new metric
names and separated market/financing/liquidation/debt information,
model_evaluation=null, and sampled history. Totals do not contain another full
history. Sampling selects actual hourly points, includes both endpoints, uses
deterministic integer index spacing, and never interpolates money or timestamps.
history_limit is a strict integer 2..1000. Aggregates use ALL receipts, never the
sample. Source history remains naive; report operation timestamps use actual
timezone-aware metadata, not fabricated UTC for the CSV.

Persisted runs do not record an executor commit. RunReport explicitly says
execution_provenance=NOT_RECORDED_BY_RUNTIME; its runtime_commit_verified_by_reporter
identifies the inspected integration, not proof of which code produced an
arbitrary old database run.

### Endpoint wiring still owned by Agent 1

POST /api/v1/runs/{id}/backtest and GET /api/v1/runs/{id}/report still return 501.
No route, shared Pydantic contract, OpenAPI file or frontend source was edited.

Agent 1 must wire the service with a database session and agree the requested
source window, 7/14/30-day duration, baseline capital, seed, immutable policy and
scenario schedule from the parent run. Never reuse its current mutated ledger.
The existing public request only supplies strategy names, so window/config
translation must be explicit. Shared response contracts currently omit history,
detailed accounting and model_evaluation; exposing those requires the route/
contract owner's coordinated schema update. Using the old response model would
discard the richer fields. Do not advertise the endpoints as implemented.

### Real PostgreSQL test commands

Use the existing repository Python executable. Set BACKTEST_TEST_DATABASE_URL
to the dedicated reserve_juggler_m2_test server database, then:

~~~powershell
$env:PYTHONDONTWRITEBYTECODE='1'
# Configure BACKTEST_TEST_DATABASE_URL with your local test credentials.
python -m pytest tests/backtesting -q -p no:cacheprovider --tb=short
python tests/backtesting/run_postgres_suite.py -q -p no:cacheprovider --tb=line
~~~

The first command exercises owned probes in separate migrated, CSV-loaded
disposable databases. The second also supplies a fresh PostgreSQL application
database to the merged API regression suite and enables existing persistence/
runtime integration tests. Only generated test databases are removed afterward;
no existing shared database is reset. An empty SQLite application DATABASE_URL
cannot run the now-implemented API tests (its versioned schema is absent).

The ten real runtime/receipt probes cover a complete hour, stale-step rejection,
repo entry/maturity/interest, recorded shock consequences, read-only reporting,
sampling, isolation, missing-evidence rejection, atomic rollback, and the
repayment/early-break/future-query diagnoses above. The original seven full
comparison cases remain pending, not converted into fake passes.


## Historical 082f019 handoff packet — preserved diagnostic evidence

Handoff checkpoint: receipt/report commit
2342501dd8321d9aaf402929dfd4ed973082aabe on feat/backtesting-engine.
Inspected runtime: 082f0190a015298d63583d65a0b216a465b93ce1.
Both are local Git objects. No verified Agent 1 messaging destination is available;
the user designated this document as the handoff. No message delivery, remote
publication, route implementation, or completed historical comparison is claimed.

### Exact current response shapes

These are the service models in app.backtesting.reports, verified from their
Pydantic model_fields. They are NOT yet the response schemas of the 501 routes.
JSON uses objects and arrays, even though internal collections are tuples.
The field inventories below are structural descriptions, not fabricated example
financial results.

BacktestReport object fields:

~~~text
run_id: UUID string identifying the comparison
scenario: NORMAL | HIGH_WITHDRAWAL | LOW_DEPOSIT | SETTLEMENT_DELAY | LIQUIDITY_SHOCK
seed: integer
started_at: timezone-aware operation timestamp
ended_at: timezone-aware operation timestamp
results: array of ReportStrategyResult
execution_kind: SHARED | TEST_DOUBLE
engine_integration_sha: full commit SHA string | null
conditions_sha256: string
scenario_settings_json: immutable JSON configuration string
model_evaluation: null
~~~

ReportStrategyResult object fields:

~~~text
strategy: STATIC_RESERVE | REACTIVE_RESERVE | RESERVE_JUGGLER
metrics: FrontendFinancialMetrics object
history: array of HistoryPoint
accounting: AccountingTotals object
model_evaluation: null
~~~

RunReport object fields:

~~~text
run_id: UUID string identifying the persisted run
scenario: one of the five supported scenario names
seed: integer
started_at: actual persisted created_at timestamp
ended_at: actual persisted updated_at timestamp when complete | null
metrics: FrontendFinancialMetrics object | null
history: array of HistoryPoint
accounting: AccountingTotals object | null
scenario_settings_json: JSON string containing initial_scenario and schedule
runtime_commit_verified_by_reporter: inspected runtime SHA string
execution_provenance: NOT_RECORDED_BY_RUNTIME
model_evaluation: null
~~~

A ready run with no executed receipts has null metrics/accounting and empty
history. A partially unsupported or unreconciled run raises an error instead
of returning a misleading partial financial summary.

FrontendFinancialMetrics contains exactly:

~~~text
realized_interest_cents, accrued_interest_cents,
average_checking_cents, average_vault_cents,
redemption_penalties_cents, emergency_borrowing_cost_cents,
emergency_events, reserve_breaches, failed_payouts,
unpaid_cents, net_benefit_cents
~~~

AccountingTotals contains exactly:

~~~text
realized_interest_cents, average_checking_cents, average_invested_cents,
penalties_cents, borrowing_costs_cents, borrowing_outstanding_cents,
reserve_breaches, emergency_events, failed_payouts, unpaid_payouts_cents,
sweeps, net_benefit_cents, contractual_penalties_cents,
liquidation_losses_cents, transaction_costs_cents, realized_market_pnl_cents,
accrued_interest_cents, unrealized_market_pnl_cents,
unpaid_borrowing_costs_cents, ending_net_asset_value_cents,
customer_cash_delta_cents, model_evaluation
~~~

HistoryPoint contains exactly timestamp (naive organizer source time) and
checking_cents (integer cents). All monetary JSON values must be JavaScript-safe
integers; net benefit and market P&L remain signed. The legacy interest/accrual
projection restriction discussed above is still unresolved, not silently changed.

### Exact reproduction procedure

Run from an isolated checkout containing the handoff commit, not by switching
the shared develop checkout. Configure the existing project Python environment
with its backend dependencies and access to Docker PostgreSQL.

Confirm the local object/branch relationship first:

~~~powershell
git branch --show-current
git cat-file -e '082f0190a015298d63583d65a0b216a465b93ce1^{commit}'
git cat-file -e '2342501dd8321d9aaf402929dfd4ed973082aabe^{commit}'
git merge-base --is-ancestor 082f0190a015298d63583d65a0b216a465b93ce1 HEAD
git merge-base --is-ancestor 2342501dd8321d9aaf402929dfd4ed973082aabe HEAD
~~~

The branch is feat/backtesting-engine; both ancestry checks should exit zero.
A missing local-only commit is a handoff problem, not a SHA to fetch blindly
from GitHub.

Use a dedicated existing reserve_juggler_m2_test* database with permission to
create/drop disposable databases. The following URL is ONLY the repository's
local Compose-default example, not a production credential or requirement:

~~~powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:BACKTEST_TEST_DATABASE_URL='postgresql+psycopg2://postgres:postgres@127.0.0.1:5432/reserve_juggler_m2_test'
python tests/backtesting/run_postgres_suite.py tests/backtesting/test_runtime_persistence.py -vv -p no:cacheprovider --tb=short
~~~

Substitute your configured local test credentials if they differ. The harness
creates a uniquely named database, applies actual SQL migrations, loads the
byte-identical CSV and sets the application database before pytest starts.
The runtime fixture independently creates its own migrated, CSV-loaded test
database. Both remove only their generated databases afterward. No shared
application database or organizer source is rewritten.

Individual defect probes (same environment and Python executable):

~~~powershell
python tests/backtesting/run_postgres_suite.py tests/backtesting/test_runtime_persistence.py::test_runtime_repayment_postgresql_blocker_is_reproducible -vv -p no:cacheprovider --tb=short
python tests/backtesting/run_postgres_suite.py tests/backtesting/test_runtime_persistence.py::test_runtime_early_repo_break_blocker_is_reproducible -vv -p no:cacheprovider --tb=short
python tests/backtesting/run_postgres_suite.py tests/backtesting/test_runtime_persistence.py::test_actual_forecast_query_uses_future_observations_so_comparisons_stay_blocked -vv -p no:cacheprovider --tb=short
python tests/backtesting/run_postgres_suite.py tests/backtesting/test_runtime_persistence.py::test_real_shock_has_shortfall_borrowing_and_financing_records -vv -p no:cacheprovider --tb=short
python tests/backtesting/run_postgres_suite.py tests/backtesting/test_runtime_persistence.py::test_incomplete_shock_receipt_rolls_back_atomic_execution -vv -p no:cacheprovider --tb=short
~~~

Expected findings on 082f019:

| Probe | Actual path / observed diagnostic |
| --- | --- |
| repayment_postgresql_blocker | Step 1 shock then step 2 NORMAL recovery; PostgreSQL rejects REPAY with SQLSTATE 23514 |
| early_repo_break_blocker | Real sweep through step 17, shock at step 18; AttributeError for early_break_fee_bps |
| actual_forecast_query | Database hour 04:00 realized withdrawals appear in the forecast made at 01:00 |
| real_shock_has_shortfall | Persists the linked breach, loan, BORROW movement and accrued cost; does NOT verify all payout/NAV accounting |
| incomplete_shock_receipt | Strict receipt adapter rejects missing financing receipts and rolls back that entire step |

These tests PASS when the current defect or guard is reproduced. That is
diagnostic evidence, not a successful financial-path acceptance result. Do not
remove the tests to make the next runtime green. Preserve the original evidence
in Git and replace the relevant defect expectation with positive financial
assertions once the corrected behavior is independently demonstrated.

### Fix verification matrix and gate for Agent 1's follow-up

| Area | Required positive acceptance evidence |
| --- | --- |
| Repayment naming | Shared executor emits the schema's canonical repayment kind; shock/recovery commits successfully in PostgreSQL; principal, paid cash and movement references reconcile without duplicate events |
| Early repo redemption | Correct Decimal percentage/fee mapping, explicit haircut and net proceeds, linked cash/position movements, no missing attribute, no lost excess proceeds and no double-counted fee |
| Financed customer payouts | Full settled customer obligation is auditable, including the financed remainder; borrow credit is offset by an explicit funded payout leg; borrowing never becomes income |
| Financing expense and NAV | Hourly incurred/paid/unpaid cost receipts with unique audit references; NAV deducts principal AND unpaid costs; later payment does not expense the same amount twice; source APR is preserved |
| First observation | First step executes the requested first row, including the first CSV timestamp; 168/336/720 selected hours are neither skipped nor padded; final boundaries are exact |
| Market P&L | Persisted per-position marked values, realized/unrealized attribution, liquidation/slippage costs and cost basis reconcile with portfolio values; otherwise precisely declare unsupported cases and continue rejecting them |
| Strategy dispatch | Explicit STATIC, REACTIVE, RESERVE_JUGGLER paths through the SAME executor; isolated equal all-cash starts, source, interval, seed and scenario settings; no previous strategy state reused |
| Causal forecasting | Features/training/query access excludes current/future realized flows and future scenario settlements; regression mutating only future rows cannot alter earlier decisions; do not replace lookahead with fabricated zero forecasts |
| Route wiring | Real database session, explicit parent-run-to-request mapping, correct richer response models/OpenAPI, honest blocked/error handling and /api/v1 paths; no hidden fallback result |

For route integration, Agent 1 owns backend/app/routers/runs.py, the shared
Pydantic transport contract and contracts/openapi.yaml. This workstream supplies
BacktestReportService.compare and report_run, not independent route edits.
The original body only contains public strategy aliases; resolve the duration/
source window and policy/scenario schedule explicitly with the parent run.
Do not inherit its current mutated balances as a new strategy's initial state.

Use BacktestReport / RunReport or coordinated equivalent shared response schemas,
including nested history/accounting/model_evaluation; retain signed net benefit
and safe integers. Agree request filtering/order semantics rather than silently
mapping different strategies to identical executions. Do not attach UTC to CSV
timestamps. Continue reporting unavailable model evaluation as null.

The current SharedRuntimeFactory advertises no validated strategies. Its guard
must stay until the relevant corrected commit, dispatch and causal tests are
verified. Full backtest routing cannot claim success merely because a report
projection or one hourly transaction works.

When the user supplies the corrected full SHA and test evidence:

1. Confirm the object exists locally or on an explicitly published branch; check
   its ancestry against 082f019, and check this branch still retains 2342501.
   Inspect divergence rather than assuming a short SHA/base is authoritative.
2. Inspect the actual runtime/model/result changes and required schema migrations.
   Integrate only through the agreed isolated-branch workflow, never main.
3. Reconcile receipt mappings without synthesizing missing financial postings.
   Run the targeted real PostgreSQL probes as positive acceptance tests.
4. Run the complete suite with the PostgreSQL harness. The preceding checkpoint
   reported 733 passed / 9 skipped: seven pending full-comparison cases plus two
   optional external-dataset tests. This is a checkpoint, not a promise for a
   different runtime commit.
5. Only after dispatch, accounting and no-lookahead checks pass, configure the
   actual shared-provider factory/SHA and run the original seven comparison
   acceptance cases described above. No deterministic fake in those tests.
6. Coordinate route response/schema and endpoint tests with Agent 1. A passing
   service suite does not remove the routes' current 501 status.
7. Review ownership/diff/status, commit locally, and request permission before
   any push or main integration. Graphify's repository-level synchronization
   remains an explicitly deferred integration-owner action under path ownership.

Full historical strategy comparisons remain BLOCKED until these runtime fixes
are implemented, integrated and verified. The ten runtime probes remain
diagnostic evidence, not proof that the affected financial paths are correct.


## Current follow-up verification — 483936c (authoritative current assessment)

Verified exact local Git object: 483936c7e8d6c37c682886deb2e17503bf6d752c.
Integration merge: 94272ddae0738a63811556a96400ce95527996ec on feat/backtesting-engine.
The follow-up descends from 082f019. Receipt/report and documentation commits
2342501 and 19c7326 remain ancestors of this branch. No main/develop checkout
changes, remote fetch, force-push or push were made.

The changed shared callable is now:

~~~python
execute_hourly_step(session, run_id, expected_step=None, strategy=None) -> dict[str, Any]
~~~

It accepts canonical strategy names and legacy STATIC_RESERVE/REACTIVE_RESERVE
aliases, or reads policy_json.strategy. The display snapshot return type and
persisted receipt model family have not been replaced. The backtesting guard
advertises no fully validated comparison strategies despite actual dispatch
branches now existing. This is intentional: dispatch alone is not full financial
or allocator integration.

### What verification actually established

| Concern | Result on 483936c |
| --- | --- |
| Strategy dispatch | Present: STATIC uses a fixed reserve, REACTIVE uses prior observed withdrawals, RESERVE_JUGGLER invokes forecasting and the risk helper. Real runs with equal cash, seed, policy and separate ledger IDs were exercised. |
| Forecast query cutoff | Fixed for tested cash-flow forecasts: history is restricted to timestamps <= decision time minus one hour. Mutating the current and next six observations in a rollback-isolated test DB leaves the earlier forecast unchanged. |
| Future calibration | Agent 1's real regression rejects calibration after the cutoff. This is not proof of every possible end-to-end causal path or fitted-model provenance. |
| Repayment enum | Fixed: PostgreSQL accepts REPAYMENT; linked repayment cash and outstanding/repaid principal reconcile in the tested recovery hour. |
| Repo fee field | Fixed narrowly: early redemption executes without AttributeError and records the fee from early_redemption_haircut_pct. Complete redemption cash behavior is NOT correct yet. |
| Repo surplus proceeds | Still broken: a shock requiring only one quarter of the actual repo principal redeems the whole repo; proceeds exceeding the customer shortfall are not credited to checking. |
| Financed payouts | Still incomplete: the recorded customer withdrawal is smaller than the decision's actual requested amount by exactly the borrowed amount. |
| Financing expense / NAV | Still incomplete: positive cost accumulates on the liability, no hourly FINANCING_COST movement is recorded, and valuation liabilities/NAV omit that cost. |
| First CSV row | Still skipped: initial step 0 executes source_start_timestamp + one hour. The existing observation FK prevents simply inserting an artificial earlier start marker. |
| Bond/equity path | Unsupported earlier than P&L attribution: real open-position fixtures fail Member 1 PortfolioState validation with “current position marks must match the supplied market price observation”; no next-hour/position valuation is produced. |
| Market-P&L attribution | Not fixed: no new per-position P&L posting path or liquidation accounting was introduced. The adapter still refuses unsupported market amounts/positions. |
| Versioned routes | POST /api/v1/runs/{id}/backtest and GET /api/v1/runs/{id}/report still return HTTP 501 / NOT_IMPLEMENTED, verified by actual TestClient requests. |
| Canonical optimizer | NOT invoked by the real RESERVE_JUGGLER path, including its 17:00 sweep; see call trace below. |

The market-position hydration adapter supplies current price/value but omits
market_observation_timestamp in the canonical position construction. That violates
the canonical price-observation identity at treasury_intelligence/portfolio.py.
It also copies the position's stored yield/volatility rather than consistently
mapping current risk observations. No Member 1 validation was bypassed or relaxed;
the runtime remains responsible for supplying compatible canonical inputs.
Tests establish the actual validation failure, not a successful bond/equity run.

The forecast adapter defaults to hourly-seasonal-naive-v1, while the runtime
snapshot still labels the RESERVE_JUGGLER forecast evaluated-gb-v1. Do not treat
that display label as evidence of an evaluated ML forecast or fabricate an
evaluation score; model_evaluation remains null.

### Canonical optimizer verification

Static inspection finds no invocation/import of recommend_four_tier_allocation
in the shared hourly engine. The services treasury adapter mentions it in its
module documentation but does not call it.

test_reserve_juggler_still_omits_canonical_allocation_optimizer profiles actual
Python calls by exact function code identity, without patching the executor,
forecasting, risk helper or optimizer. Across 17 actual persisted hourly steps
through the 17:00 sweep:

- calculate_four_tier_liquidity_risk: 17 calls.
- recommend_four_tier_allocation: 0 calls.

RESERVE_JUGGLER therefore currently performs a risk-derived reserve/repo sweep,
not Member 1's canonical multi-tier allocation recommendation. Agent 1 must wire
the actual optimizer request/result contract and audit executed orders; the
backtester will not substitute another optimizer or relabel risk-only execution
as the complete strategy.

### Preserved evidence and updated regression expectations

The first post-merge run used the previous tests unchanged against real
PostgreSQL: 3 failed, 166 passed, 7 pending/skipped across the selected backtesting,
runtime, strategy/causality and API suites. The three failures were obsolete
assertions that the old enum/attribute/leak defects still occurred. They were
recorded before any test expectations changed.

Original 082f019 failing-path probes remain recoverable from commit 2342501.
Their resolved expectations were replaced with positive checks only after the
real corrected paths were exercised. Remaining broken paths are still explicit
diagnostic tests, not xfailed, deleted, or asserted as financially correct.

Final integrated PostgreSQL-backed suite: 748 passed, 9 skipped. The skips are
the original seven pending full-comparison cases and two unavailable external
Downloads datasets. The owned real-runtime probe module has 18 passing cases;
diagnostic passes still signify reproduced defects, not financial correctness.

Current reproduction commands (use these instead of historical node IDs above):

~~~powershell
$env:PYTHONDONTWRITEBYTECODE='1'
# Set BACKTEST_TEST_DATABASE_URL to the dedicated local test database URL.
python tests/backtesting/run_postgres_suite.py tests/backtesting/test_runtime_persistence.py -vv -p no:cacheprovider --tb=short
python tests/backtesting/run_postgres_suite.py tests/backtesting tests/integration/test_runs_runtime.py tests/integration/test_strategy_dispatch_and_causality.py tests/backend/test_api_versioning.py -q -p no:cacheprovider --tb=line -rs
python tests/backtesting/run_postgres_suite.py -q -p no:cacheprovider --tb=line -rs
~~~

To reproduce the optimizer integration gap alone:

~~~powershell
python tests/backtesting/run_postgres_suite.py tests/backtesting/test_runtime_persistence.py::test_reserve_juggler_still_omits_canonical_allocation_optimizer -vv -p no:cacheprovider --tb=short
~~~

Other current exact node IDs in tests/backtesting/test_runtime_persistence.py:

- test_runtime_repayment_uses_schema_kind_and_preserves_principal_identity
- test_runtime_repo_fee_field_mapping_no_longer_raises_attribute_error
- test_forecast_cutoff_is_invariant_to_current_and_future_source_flows
- test_repo_redemption_still_loses_proceeds_beyond_customer_shortfall
- test_shock_still_has_incomplete_payout_and_financing_nav_receipts
- test_open_market_positions_still_fail_canonical_hydration (BOND/EQUITY cases)
- test_backtest_and_report_routes_still_return_501 (POST/GET cases)

The selected fixture shock is derived only to hit the partial-redemption branch;
the test does not implement its own execution/valuation model. Future-row
mutations and seeded market positions exist only inside isolated disposable
PostgreSQL transactions. The original CSV remains byte-identical.

### Current readiness gate and ownership

**NOT READY for historical strategy comparisons.** The seven full-comparison
acceptance cases remain pending. Strategy/cash-flow forecast improvements do not
waive the outstanding requirements for financed payouts, financing-cost receipts
and NAV, complete repo proceeds, first-row alignment, market compatibility/P&L,
actual canonical optimizer use, and route/response integration.

The prior response field inventories and safe-cent/report mappings remain
unchanged. The owned adapter's inspected runtime SHA is updated to 483936c; it
does not claim arbitrary persisted runs record their own executor commit.
BacktestReportService still fails closed for full comparisons. The service does
not inject a replacement engine, forecast, optimizer or balancing ledger entry.

Only backend/app/backtesting/, tests/backtesting/ and this document are edited by
this workstream. Agent 1's shared engine, adapters, models/migrations, router,
public contracts/OpenAPI and frontend are inherited unchanged from the verified
follow-up. Graphify updates in that commit are inherited; owned graph regeneration
is still deferred under the existing path restriction. No push or main integration
is authorized by this verification.


## Focused Agent 1 release-blocker handoff after verification 8c49078

Current verified runtime remains 483936c7e8d6c37c682886deb2e17503bf6d752c.
Verification evidence is committed as 8c49078e3718083ed56314860ae597565e05fe55,
after integration merge 94272ddae0738a63811556a96400ce95527996ec.
The branch is feat/backtesting-engine. This handoff requests corrections; it
does not authorize this workstream to modify the shared executor or API files.

Acceptance here has two separate meanings: Agent 1 explicitly accepting ownership
of a requested fix, and an implemented fix passing positive financial acceptance
tests. Neither follows from the user acknowledging an audit or from a passing
diagnostic probe. No direct Agent 1 messaging destination has been verified;
this document remains the handoff, not evidence of a delivered chat message.

### Requested-fix acknowledgement register

| Handoff item | Requested owner | Explicit owner acceptance | Corrected runtime SHA / positive verification |
| --- | --- | --- | --- |
| H1 Canonical optimizer-to-execution integration | Agent 1, with Member 1 contract review | Not confirmed | Not supplied / not verified |
| H2 Financed payouts, financing receipts and NAV | Agent 1 | Not confirmed | Not supplied / not verified |
| H3 Complete early-redemption proceeds | Agent 1 | Not confirmed | Not supplied / not verified |
| H4 First-observation timing and exact replay interval | Agent 1 | Not confirmed | Not supplied / not verified |
| H5 Canonical market-position hydration and market-P&L attribution | Agent 1, with Member 1 contract review | Not confirmed | Not supplied / not verified |
| H6 Backtest/report route and response integration | Agent 1, coordinated with backtesting owner | Not confirmed | Not supplied / not verified |

Update a row only with an explicit acknowledgement or an identified commit and
actual test evidence. Do not mark these fixes accepted, implemented or verified
based on a branch name, runtime summary or an unrelated passing suite. The enum,
fee-field and forecast-query improvements already verified on 483936c do not
close H1-H6.

### Explicit positive acceptance tests required before closing each item

The following are REQUIRED TEST SCENARIOS, not claims that new positive tests
already exist or pass. Existing diagnostic node IDs below reproduce the current
failures; their expectations must be upgraded once the corrected real path is
exercised. Do not replace financial execution with a fake or mock optimizer
result merely to satisfy these gates.

**H1 — Actual canonical allocation call and order execution**

Starting evidence: test_reserve_juggler_still_omits_canonical_allocation_optimizer
records 17 risk-helper calls and zero optimizer calls through the 17:00 sweep.

Required positive tests:

1. Trace actual shared RESERVE_JUGGLER decision execution and demonstrate a call
   to Member 1's canonical recommend_four_tier_allocation(), using its agreed
   canonical request/result contracts. Review those inputs with Member 1:
   real current portfolio, causal information and actual policy/assumptions,
   not invented allocation targets or a second portfolio definition.
2. For an eligible nonempty recommendation, demonstrate the returned order is
   consumed by the SAME hourly executor and linked to its executed movement,
   cash ledger, position change and decision explanation. Also cover legitimate
   HOLD/rejected recommendations with explicit execution status/rationale.
   Merely invoking the optimizer and discarding the result is not sufficient.
3. Verify STATIC and REACTIVE retain their explicit baseline paths and isolated
   equal source/capital/seed/scenario/policy conditions. Compare IDs and actual
   persisted balances, not just returned strategy labels.
4. Mutate only unavailable current/future source information in an isolated test
   DB and show the earlier forecast AND optimizer recommendation are unchanged.
   Include rejection of future-dated model/calibration inputs. The existing
   cash-flow forecast invariance test must remain passing.

**H2 — Financed customer payouts, financing costs and net asset value**

Starting evidence: test_shock_still_has_incomplete_payout_and_financing_nav_receipts
and test_incomplete_shock_receipt_rolls_back_atomic_execution.

Required positive tests:

1. Execute a real liquidity shock that needs borrowing. Every settled customer
   payment, including the financed remainder, must have complete auditable cash
   legs. Reconcile requested amount to actual paid plus explicitly recorded
   unpaid/failed amount. A loan draw is financing, never income or a payout
   success signal by itself.
2. Reconstruct opening/closing checking from customer, investment, funding,
   interest and disjoint cost postings. Reconcile each principal movement to
   the liability and require unique audit/idempotency references.
3. Incur financing expense at the source APR, leave it unpaid, then pay it later.
   Require hourly incurred/paid/unpaid cost evidence, not only the current
   cumulative liability field. Paying an already expensed cost must not expense
   it again. Include repayment with more than one outstanding loan and ensure
   per-loan cash/event references do not collide.
4. Require NAV = Tier 0 + Tier 1 + Tier 2 + Tier 3 asset amounts minus outstanding
   principal minus unpaid financing costs. Reconcile change in NAV excluding
   external customer flows to interest/accrual changes, market P&L and all costs.
   Debt-funded cash must never inflate net benefit.
5. Execute through execute_persisted_hour and reconstruct through report_run;
   both must agree with the real persisted receipts. Inject a receipt inconsistency
   and retain the existing atomic rollback/conflict protections. Do not remove
   the current strict error merely to let incomplete records pass.

**H3 — Preserve all repo redemption proceeds**

Starting evidence: test_repo_redemption_still_loses_proceeds_beyond_customer_shortfall;
the fee-field mapping test alone does not establish correctness.

Required positive tests:

1. Reuse the real sweep and partial-shortfall fixture. After redemption, the
   proceeds not consumed by the customer payment must remain in Tier 0, or the
   unsold principal must remain in a correctly represented partial position.
   Prove that no principal disappears.
2. Reconcile gross principal, any realized interest, the source-supplied
   early-redemption haircut and net proceeds to movement/ledger records. Record
   a cost exactly once; never disguise it as negative interest or market loss.
3. Cover sufficient proceeds, exact coverage and insufficient proceeds, including
   multiple repo positions. Do not break extra positions after the shortfall is
   satisfied. Borrow only the residual deficit when applicable.
4. Confirm a redeemed position cannot mature or credit proceeds again. Preserve
   the real 17:00 sweep / next-day 08:00 maturity regression and receipt/report
   accounting identities. The shared runtime owns rounding/fill behavior;
   the backtester must not calculate replacement proceeds.

**H4 — First organizer row and causal replay timing**

Starting evidence: the complete-hour probe currently executes January 1 01:00
from a January 1 00:00 source start; runtime computes start + target_step hours.

Required positive tests:

1. Execute the first requested organizer observation, including the dataset's
   very first row, exactly once. Do not fabricate an earlier observation, alter
   the immutable CSV, insert a negative persisted step, or weaken source FKs
   merely to work around the offset.
2. Execute exactly 168, 336 and 720 hourly source rows for 7/14/30-day windows;
   prove the first and last included rows and exclusive end. Include month/year
   boundaries, the last complete supported window and incomplete-window errors.
3. Preserve naive source timestamps and native hourly resolution; do not invent
   UTC or resample to 15-minute rows. Warm-up history must not create pre-window
   portfolio activity, balances, income or liability.
4. Keep customer/market information unavailable until its agreed observation
   boundary. Verify the corrected first-row handling together with no-lookahead
   features, optimizer decisions and model/artifact cutoffs, not only row counts.
   Preserve source net_flow and the original one-cent reconciliation differences.

**H5 — Market hydration and honest market-return attribution**

Starting evidence: test_open_market_positions_still_fail_canonical_hydration
for BOTH BOND and EQUITY.

Required positive tests:

1. Seed an explicit real bond/equity position fixture and exercise the unchanged
   shared financial path. Canonical hydration must validate without relaxing
   Member 1 contracts: position mark timestamps/prices must match their supplied
   market observation, and duration/yield/volatility must match applicable inputs.
   Preserve Decimal precision and position/run/source identity.
2. Across at least two source marks, persist auditable position/portfolio values
   and signed unrealized P&L. On a real sale/liquidation, persist cost basis,
   gross realized P&L, released unrealized P&L, haircut/slippage and net cash.
   A previously marked gain must not be earned twice when realized.
3. Reconcile position movements and market attribution to the report's NAV/net
   benefit. Equity market gains are NOT guaranteed interest; haircut/slippage
   is separate from market price loss and financing expense.
4. If a case is deliberately unsupported, publish the precise unsupported
   instruments/operations and fail it explicitly. Do not output placeholder
   zero P&L or claim a complete four-tier comparison. Any narrowed evaluation
   scope requires an explicit agreement; it is not automatically release-ready.

**H6 — Versioned endpoint wiring and response contracts**

Starting evidence: test_backtest_and_report_routes_still_return_501 for POST/GET.
Shared route, public Pydantic and OpenAPI changes remain Agent 1's ownership.

Required positive tests:

1. Exercise actual /api/v1/runs/{id}/backtest and /report HTTP requests against
   migrated PostgreSQL, with the REAL backtesting/report services and executor.
   Valid supported requests must return the agreed successful schema, rather
   than unconditional 501, a fabricated comparison or silently dropped fields.
2. Verify explicit parent-run mapping for initial capital, source/window,
   7/14/30-day duration, seed, immutable policy and scenario schedule. Never use
   the parent's current mutated ledger as the next strategy's starting state.
   Agree handling of requested strategy aliases/order/subsets with the service.
3. Validate nested sampled history, separated accounting totals and
   model_evaluation:null against the agreed public Pydantic/OpenAPI contract.
   Assert JavaScript-safe integer cents, signed net benefit, actual payout
   unpaid amounts distinct from debt, causal source timestamps and provenance.
   Prove sampling uses actual points while metrics use every executed receipt.
4. Test unknown IDs, invalid parameters, step conflicts and unsupported/incomplete
   financial state using the agreed error contract. A ready run with no executed
   receipts must preserve honest unavailable metrics; incomplete accounting must
   not become a successful partial report.
5. Check route/schema parity and serialization/deserialization with the frontend
   contract. These service-level checks do not authorize frontend edits here.

### Verification sequence and Member 1 coordination

Once a corrected commit and Agent 1's acknowledgement arrive, record the FULL
runtime SHA, its base/ancestry, changed receipt/model contracts, migration status
and actual commands/results per H1-H6. Verify the object locally or use a
controlled transfer; never fetch a local-only SHA from GitHub by assumption.
Preserve 8c49078 and its predecessors; do not reset, rewrite or merge main.

Use the PostgreSQL harness commands in the current follow-up review to run
targeted probes, backtesting/runtime/API regressions and the complete suite.
Only after the positive optimizer-to-order, accounting, observation-timing and
API checks pass may the seven pending full-comparison acceptance cases run
against the actual provider. Diagnostic passes remain evidence of defects.

The user will coordinate end-to-end validation with Member 1, including
**RJ-M1-16**. No tracked RJ-M1-16 specification was located in this checkout;
its task-specific requirements, owner sign-off and evidence must be supplied by
Member 1/user. Do not infer that it is implemented, accepted or passed, and do
not invent its scope from its identifier. H1-H6 are this handoff's release gates,
not a replacement specification for RJ-M1-16.

Current closeout: no new corrected runtime SHA supplied; no H1-H6 owner acceptance
confirmed; historical strategy comparisons remain BLOCKED. This document is the
focused Agent 1 handoff until a verified messaging destination is available.


## Independent checkpoint verification — dee0aae (2026-10-18)

This section supersedes the older closeouts above. **Historical comparisons
remain BLOCKED.** A successful diagnostic HTTP request is not financial release
approval. No Agent 1 acceptance of the remaining defects is recorded.

### Exact local integration and receipts

Verified locally, without fetching an unpublished SHA:

- Runtime checkpoint: dee0aae3cbd77ed4ad4e6f0961b9594ad53461d2.
- Its parent: 9c1b3b6d345093a2a6ed6345db64f0bc331b2194, our existing handoff commit.
- Local no-fast-forward integration: 798085c14351345c4941269a65cd17684fe4ad11.
- Branch/worktree: feat/backtesting-engine in the existing isolated backtesting
  worktree. The shared develop checkout and main were not switched or edited.
- Existing 35741cea, 2342501, 19c7326, 8c49078 and 9c1b3b6 remain ancestors.
- Agent 1's checkpoint included edits to the owned runtime bridge and runtime
  probe file; these were inspected and inherited, not overwritten.
- No push or main merge is authorized or performed.

The actual callable is execute_hourly_step(session, run_id,
expected_step=None, strategy=None), returning a snapshot dict, NOT an accounting
receipt. StepConflictError remains the shared concurrency exception.

The receipt reader derives evidence from actual persisted SimulationRun,
OrganizerObservation, CashAccount, LedgerEntry, InvestmentMovement,
OverdraftMovement, LiquidityBreach, TreasuryDecision, PortfolioValuation and
PositionValuation. Positions/liabilities are RepoPosition, BondPosition,
EquityPosition and OverdraftLiability. No replacement simulator was added.

Source timestamp for step k (one-based) is start + (k-1) hours; the closing
portfolio valuation is at start + k hours. Read/aggregate historical debt from
dated movements, not the present mutable liability balance. FINANCING_COST
movements have zero cash delta and an explicit financing_cost_cents amount.
Repayment kind is REPAYMENT. Borrowing principal and unpaid expense remain
separate stocks; neither is interest income.

### What the checkpoint actually fixes, and what remains

| Gate | Independently verified progress | Remaining release requirement |
| --- | --- | --- |
| H1 | All three dispatches execute; real canonical recommend_four_tier_allocation is called 18 times through 17:00. A returned INVEST_REPO order is linked by order_id to an executed decision and reconciled to real investment movement/cash ledger. Forecast helper excludes current/future cash flows. | REACTIVE without prior history reads the unpublished current withdrawal. Canonical input phase/portfolio freshness needs agreement: portfolio is hydrated before payouts, maturity and repayment, but optimizer is called afterwards. Unsupported non-repo recommendations are not explicitly executed/rejected. |
| H2 | Complete financed payout legs, BORROW/REPAYMENT cash/principal identities, hourly financing-cost movements and persisted closing NAV deduction pass real shock/receipt tests. | Canonical hydration excludes fully principal-repaid loans even when fees remain unpaid. Paying financing costs later is not implemented: reader has paid_borrowing_costs_cents=0 and runtime posts no expense payment. Verify fee settlement without double expense, multiple loans and optimizer inputs. |
| H3 | 0.5% fee-field mapping, full early-redemption proceeds including cash beyond immediate shortfall, and actual 17:00/08:00 sweep/maturity receipts pass. | Repo closing accrual is recomputed as ONE hour rather than accumulated earnings. Agree floating-APY accrual/fill policy and verify multi-position, exact/insufficient coverage and no duplicate maturity credits. |
| H4 | First row 2026-01-01 00:00 is processed, followed exactly once by 01:00; receipt states chain and audit IDs are disjoint. The requested successful route test executes a real 168-hour three-dispatch diagnostic. | Full 336/720-hour and final-window acceptance cases remain pending, not verified financial comparisons. Shared CreateRunRequest requires UTC and the inherited bridge temporarily attaches UTC to unspecified organizer wall time before run service strips it: source-aware creation is still needed; no source timezone is thereby established. |
| H5 | BOTH funded bond/equity opening fixtures hydrate; two actual hourly marks, signed unrealized P&L, persisted position valuations, NAV and report net benefit reconcile. Bond loss and equity gain remain market P&L, not interest. | No bond/equity buy/sell or emergency liquidation execution is present in this hourly path. PositionValuation.realized_pnl_cents is always written zero; reader rejects non-tier-1 investment movements and cannot claim real liquidation/slippage attribution. Require real fills or explicitly agreed narrower scope. |
| H6 | Requested POST /api/v1/runs/{id}/backtest and GET /report success probes both pass (not 501). Frozen OpenAPI parity is separately covered by the branch suite. | Public GET response filters out owned accounting/history/model_evaluation/scenario/provenance fields. POST ignores strategy subsets and drops top-level provenance; nested extras happen to serialize with a warning, not a declared authoritative schema. Duration, scenario, transaction and rerun contracts need route-owner completion. |

The public routes remain Agent 1's ownership. No core services, routers,
v1_contracts, OpenAPI, persistence, migrations, Member 1 code or frontend were
edited during this independent verification.

### Preserved unmasked failure evidence

The new tests/backtesting/test_checkpoint_verification.py initially ran against
the unchanged checkpoint core and inherited adapter: **4 passed, 6 failed**
in 51.41 seconds. The six failures were:

1. REACTIVE first-row reserve changed from 710298085 to 810298085 cents after
   changing ONLY unpublished current withdrawals in a rolled-back test database.
2. After full principal repayment, real closing receipts retained 528 cents
   unpaid financing expense, but canonical hydrated liabilities became ZERO.
3. Held repo accrual fell from 492724 to 492038 cents between the 18:00/19:00
   observations: valuation contains one-hour accrual instead of cumulative accrual.
4. Executed GET /report returned only run_id/scenario/seed/started_at/ended_at/
   metrics. It lost accounting, history, model_evaluation, scenario_settings_json
   and execution_provenance.
5. POST requesting only STATIC_RESERVE returned all three strategies and omitted
   checkpoint provenance. Its nested history/accounting/model_evaluation were
   present in this observed response, despite the legacy declared response model;
   do not claim these particular nested fields were experimentally lost.
6. The configured backtesting factory silently discarded a supplied step-2
   LIQUIDITY_SHOCK schedule. This OWNED adapter defect is fixed below.

Five remaining core/route failures are now strict xfail(raises=AssertionError)
regressions, NOT passes or accepted limitations. An unexpected fix becomes
XPASS(strict), which fails the suite until reviewed. --runxfail exposes their
original failing assertions. Unexpected exceptions are not hidden by those marks.

### Owned integration changes

Only app/backtesting/runtime.py, owned tests, and this document change locally:

- Correct inspector/provider RUNTIME_SHA and engine_version to dee0aae. A stored
  arbitrary run still has execution_provenance=NOT_RECORDED_BY_RUNTIME; the
  reporter's known code SHA is not invented per-run execution provenance.
- Preserve scenario schedules by validating and passing each sorted event to
  the shared apply_simulation_scenario service. No scenario arithmetic is added.
  Exact duplicate initial settings are one event; conflicting/duplicate steps,
  missing explicit steps and events outside the run are rejected.
- Atomically validate each adapter execution receipt in the same PostgreSQL
  savepoint as the actual shared engine call. On rejection, the hour's ledger,
  decision and step mutations roll back; outer caller transaction remains owned
  by its caller.
- Reject bad source digest/time/token/closed-run executions before posting.
  Verify actual receipt digest/time within that savepoint.
- Reject an existing deterministic run ID clearly, without overwriting/reusing a
  previous strategy ledger or poisoning the SQLAlchemy session. Fresh comparison
  IDs create isolated runs. Replaying the SAME comparison ID against retained
  rows remains unsupported: no destructive reset or invented result cache.
- Validate created run dataset/start/hourly interval against requested conditions.
  Close factory-owned sessions if initialization fails.
- Retain explicit blocking_reasons for configured diagnostic providers.
  Dispatch capabilities describe executable paths, NOT H1-H6 financial approval.
  Default unconfigured provider remains fail-closed.

Provided sessions retain successful run rows and own commit/rollback.
Factory-created sessions close without commit (thus roll back uncommitted work).
The HTTP owner must define durable result versus ephemeral evaluation behavior.

Remaining static route findings to coordinate (not silently fixed):

- POST does not commit and get_db closes without commit; successful new strategy
  rows are not durably saved under the ordinary request lifecycle. Transaction/
  idempotency behavior needs explicit route acceptance.
- Parent duration outside exact 168/336/720 is silently rounded/defaulted to a
  supported day count; reject unsupported/incomplete windows instead.
- Parent policy's actual scenarios list is now forwarded by the owned adapter,
  but route reads constant parameters only from legacy scenario_parameters.
  Conflicting initial/scheduled settings must be mapped explicitly, not guessed.
- Requested strategy aliases/subsets/order are accepted publicly but ignored.
- Shared public/openapi schemas still omit the richer owned response fields.
- Unsupported configured policy fields (for example reserve_fraction in the
  original opt-in fixture) are rejected by shared TreasuryPolicy. Agree a real
  shared policy contract; do not silently substitute defaults.

### Reproduce sequentially on PostgreSQL

Use the repository's existing Python environment. From the isolated worktree,
set BACKTEST_TEST_DATABASE_URL to the disposable reserve_juggler_m2_test*
PostgreSQL database URL, PYTHONDONTWRITEBYTECODE=1, PYTHONUNBUFFERED=1. Each harness
run creates, migrates, seeds and drops only its own uniquely named database.
Never run these concurrently against shared run state.

Common invocation:

~~~powershell
$python = 'D:\Hackathon\projects\reserve-juggler\.venv\Scripts\python.exe'
& $python -u tests/backtesting/run_postgres_suite.py <arguments>
~~~

Actual argument sets, in execution order:

1. tests/backtesting/test_runtime_persistence.py::test_backtest_and_report_routes_succeed -vv -s -p no:cacheprovider --tb=long
   First test: **2 passed, 1 warning, 52.71 seconds**; exit 0, no hang.
2. tests/backtesting tests/integration/test_runs_runtime.py tests/integration/test_four_tier_runtime.py tests/integration/test_strategy_dispatch_and_causality.py tests/backend/test_persistence.py -v -p no:cacheprovider --tb=short
   Baseline checkpoint regressions: **190 passed, 7 skipped, 1 warning,
   90.23 seconds**, exit 0.
3. tests/backtesting/test_checkpoint_verification.py -vv -s -p no:cacheprovider --tb=long
   Initial unmasked independent gates: **4 passed, 6 failed, 1 warning,
   51.41 seconds**, exit 1. This predates the owned scenario fix and xfail marks.
4. tests/backtesting/test_checkpoint_verification.py -k "not public_backtest" -vv -p no:cacheprovider --tb=short -rxX
   First owned adapter checks: **11 passed, 1 deselected, 4 xfailed,
   8.19 seconds**, exit 0.
5. tests -q -p no:cacheprovider --tb=short -rxX
   Complete integrated PostgreSQL suite: see verification closeout below.

To reproduce unresolved defects without expected-failure masking:

~~~powershell
& $python -u tests/backtesting/run_postgres_suite.py tests/backtesting/test_checkpoint_verification.py --runxfail -vv -s -p no:cacheprovider --tb=long
~~~

Full stdout/stderr logs are retained locally in:
C:\Users\DEVESH SHUKLA\AppData\Local\Temp\reserve-juggler-dee0aae-verification-bb9ff202170d45abb501cecaa51f6d2c
(files 01-route-success-complete.log through 06-final-owned-adapter-checks.log).
The source CSV hash remains:
2e7c1d2e5b678e9975250211e7e0017022049c510e1dd90cd7f29e931837b0c5.

Seven full-comparison cases remain explicit skips until release approval:
7/14/30 NORMAL and seven-day HIGH_WITHDRAWAL, LOW_DEPOSIT, SETTLEMENT_DELAY,
LIQUIDITY_SHOCK. They must eventually use a verified real provider and actual
supported policy, establish deterministic rerun lifecycle and pass ALL original
receipt identities without xfails. No RJ-M1-16 acceptance is inferred.

Graphify exists at repository level and checkpoint updates were inherited.
Owned graph regeneration remains deferred because graphify-out and sync scripts
are outside this workstream's permitted edit paths. No second graph project and
no unsupported synchronization-success claim. Integration owner must synchronize
after accepting fixes. This does not delay diagnostic tests or the local commit.

No verified Agent 1 messaging destination is available. This section remains the
handoff; core fixes are neither claimed accepted nor assigned a new runtime SHA.

### Verification closeout

Complete integrated suite (command 5): **761 passed, 9 skipped, 5 xfailed,
2 failed, 2 warnings in 161.04 seconds; exit 1**. No hang and no concurrent
duplicate test runs. PostgreSQL migrations/source seeding/receipt paths were real.

Final owned check (command 6, same arguments as command 4 after adding schedule
validation/deduplication cases): **15 passed, 1 deselected, 4 xfailed in 8.30
seconds; exit 0**. The deselected costly POST subset probe was already exercised
and remained the fifth expected failure in the complete run.

Both ordinary failures are existing parameterizations of
tests/backend/test_api_versioning.py::test_backtest_routes_return_honest_unimplemented_error:
they still assert 501 for unknown runs while the checkpoint returns 404.
Their update belongs to the API/runtime owner, not this workstream.
Do not describe the complete suite as green.

The five strict expected failures remain release blockers, not verified financial
paths. Nine skips include all seven full-comparison acceptance cases.
All 15 non-xfailed new checkpoint/owned adapter checks pass within the complete run;
the five xfails can be reproduced with --runxfail. Existing Member 1, pipeline,
runtime/dispatch and PostgreSQL persistence tests otherwise pass. OpenAPI equality
passes for the OLD declared contract, not the required richer response shape.

Release conclusion: **DO NOT UNBLOCK historical strategy comparisons**. Agent 1
must address the core/route defects, fee settlement and market trade coverage,
source-time boundary, repeat-comparison lifecycle and stale API tests.
Verify a new exact checkpoint, rerun strict gates without xfail masking, then
obtain Member 1/user approval before historical-comparison or RJ-M1-16 acceptance.
