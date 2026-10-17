# Historical backtest service contract

Status: orchestration, persisted receipt/report integration and real PostgreSQL
probes implemented. **Full historical strategy comparisons remain blocked.**
This is a Python service boundary, not a new API, simulator, strategy algorithm,
database model, or replacement for Member 1's canonical portfolio contracts.

## Verified base and ownership

Original base: feat/simulation-backend,
52e58bcfcad766a1444b37a175b48158fd645409; initial backtesting implementation:
35741cea1993fb6ee665a10a572c75b3b44a0abd.

Verified local runtime: 082f0190a015298d63583d65a0b216a465b93ce1, based on 4a85674.
Both commits were confirmed in the same Git object database before merging the
runtime into the isolated feat/backtesting-engine branch. No GitHub fetch of a
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

## Strategy-provider protocol (proposed, not supplied by runtime 082f019)

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


## Verified persisted-runtime adapter and report handoff (082f019)

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

### Additional confirmed runtime blockers for Agent 1

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


## Agent 1 handoff packet — documentation delivery, comparisons blocked

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
