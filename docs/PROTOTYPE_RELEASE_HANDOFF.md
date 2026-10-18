# Prototype release / RJ-M1-16 handoff

Working diagnostic prototype; NOT historical-comparison certification.
Member 1's RJ-M1-16 and the broader acceptance gates remain required.
No push, merge to main, quantitative-engine or persistence-schema changes.

## Revisions and ownership

Branch: codex/prototype-release-verification.
Application/verification checkpoint: 19a37fe2ed34a449272448ad141678ec80299608.
The final evidence-only commit containing this document is the handoff HEAD;
obtain it with git rev-parse HEAD. It changes no tested application source.
Isolated checkout: D:\Hackathon\projects\reserve-juggler-release-check.

All six requested objects exist locally and are ancestors of integration base
1273e44d8ab85a4f6ab1c2f7b4d91d021474d9c7:

| Component | Exact SHA |
| --- | --- |
| Core runtime | 1d943eeb652775ef0aecb8cf73bd781293722d36 |
| Runtime verification | 926a3407c21ac8c34e6408dfa3f7b1011d5bbdce |
| Backtesting integration | cc75615bfbbd0660bb514b50b111967c92a01210 |
| Frontend integration | f41e7a83d4ae17d81496dfb808ac29d316b81417 |
| Earlier tested integration | bf3ddebfda9294d9103208e7e68f4cede847ba1d |

These are LOCAL, unpushed checkpoints, not in any locally known remote ref.
Do not assume unpublished SHAs can be fetched from GitHub.
The shared checkout and its untracked diagnostics were not our work area.
main remains 2e396f92e5d4d56d196026f24a671aa4c3bebe24;
feat/treasury-intelligence remains 87a82173e100a717155af23738ecc915658c8bf2.

No backend/API/quantitative/persistence/Agent 2 adapter code changed from 1273e44.
The only application edits are in the live frontend response adapter: five-minute
comparison timeout (formerly one minute), actual accounting sweep/debt mapping,
and retained report history. Each defect had a failing test before correction.
Added a reusable REAL-engine evidence harness and explicit PostgreSQL H2 delay
tests. No second simulator or substitute quantitative implementation.

## Actual verification

Complete output and machine-readable evidence: evidence/prototype-release/.

| Check | Actual result |
| --- | --- |
| Fresh PostgreSQL | migrations 001/002/003 applied, 8,760 observations loaded |
| Real Uvicorn HTTP | health 200, create 201, four-tier snapshot/policy/scenario/advance/report 200, seven-day three-strategy backtest 200, all six retained child report/snapshot requests 200 |
| API comparison timing | 2026-10-18 02:38:41–02:41:32 UTC operation clock, approximately 171 seconds |
| Final frontend tests | 71 passed / 5 files, 11.81 seconds |
| Final production build | passed, 2,202 modules, 12.82 seconds, mocks disabled |
| Named H2 + explicit 0/3600-second delay + two no-lookahead checks | 5 passed, 39.72 seconds |
| Purchase/partial-sale receipts, capped payouts, financing NAV | 9 passed, 24.64 seconds |
| Graphify | actual AST updated; PostgreSQL augmentation verified 22 tables |

Backend tests/harness ran on 1273e44 plus the subsequently committed verification
files; backend code remains byte-identical at 19a37fe. Final frontend tests/build
ran on exactly the frontend source committed in 19a37fe.
An initial npm command issued at repository root failed (no package.json) and
was corrected to frontend/. Deliberate pre-fix regressions failed for the
60-second timeout and fabricated zero sweeps; their logs are retained separately.
No full suite or 7/14/30-day scenario matrix was launched.

## Setup, startup and reproduce

The run used the existing Windows Python environment and Docker-hosted
PostgreSQL 16, localhost:5432, postgres/postgres DEVELOPMENT credentials.
Install dependencies if needed from backend/requirements.txt and
treasury_intelligence/requirements.txt. The test bootstrap role needs CREATE
DATABASE and migration/schema access. Do not target shared/production databases.

From the isolated repository root:

~~~powershell
$py = 'D:\Hackathon\projects\reserve-juggler\.venv\Scripts\python.exe'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONPATH = 'backend;.'
$env:BACKTEST_TEST_DATABASE_URL = 'postgresql+psycopg2://postgres:postgres@127.0.0.1:5432/reserve_juggler_m2_test'
& $py -u scripts/prototype_release_verify.py --output evidence/prototype-release --port 8017
~~~

Stop any owned demo server on 8017 before rerunning. The harness starts/stops
ONE Uvicorn child, creates/migrates/loads ONE disposable DB and RETAINS it for
inspection. The HTTP comparison is ephemeral by contract; a second comparison
using the SAME shared service/engine is committed to retain auditable records.

Retained database: reserve_juggler_m2_test_release_d5c756fa6f29.
To start it without repeating comparisons:

~~~powershell
$env:DATABASE_URL = 'postgresql+psycopg2://postgres:postgres@127.0.0.1:5432/reserve_juggler_m2_test_release_d5c756fa6f29'
& $py -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8017
~~~

For a manually created disposable empty demo DB, substitute its name above,
then bootstrap before starting Uvicorn:

~~~powershell
& $py -m app.persistence.migrations
& $py -c "import os; from sqlalchemy import create_engine; from sqlalchemy.orm import Session; from app.data.organizer import OrganizerDatasetSource; from app.persistence.repositories import DatasetRepository; s=Session(create_engine(os.environ['DATABASE_URL'])); DatasetRepository(s).store(OrganizerDatasetSource().load()); s.commit(); s.close()"
~~~

Use explicit postgresql+psycopg2://: plain postgresql:// is normalized by the app
to psycopg3, not declared in backend/requirements.txt. Health alone is insufficient;
this evidence checks actual PostgreSQL ledger and valuation rows, not SQLite.
The Docker application image was NOT VERIFIED. Existing port-8000 server was
left untouched. The prepared disposable demo DB is intentionally retained.

From frontend/:

~~~powershell
$env:VITE_USE_MOCKS = 'false'
$env:VITE_API_BASE_URL = 'http://127.0.0.1:8017'
npm.cmd test -- --reporter=dot
npm.cmd run build
npm.cmd run preview -- --port 3017 --host 127.0.0.1
~~~

The VITE variables apply at BUILD time. DATABASE_URL is the backend setting;
PYTHONPATH makes backend and the repository intelligence package importable.
Existing installed frontend dependencies were reused, without changing packages.

Exact focused commands (repository root, environment above):

~~~powershell
& $py -u tests/backtesting/run_postgres_suite.py tests/backtesting/test_runtime_acceptance.py::test_acceptance_h2_contractual_repo_maturity_at_eight_am_with_delay_invariance tests/backtesting/test_prototype_h2_records.py tests/backtesting/test_runtime_acceptance.py::test_canonical_optimizer_targets_ignore_unavailable_current_and_future_flows tests/backtesting/test_runtime_persistence.py::test_forecast_cutoff_is_invariant_to_current_and_future_source_flows -vv -s -p no:cacheprovider --tb=short
& $py -u tests/backtesting/run_postgres_suite.py tests/backtesting/test_execution_receipt_adapter.py::test_purchase_receipt_preserves_executed_details_and_reconciles tests/backtesting/test_execution_receipt_adapter.py::test_partial_sale_receipt_preserves_fill_and_basis_reconciliation tests/integration/test_payout_execution.py::test_payout_records_only_funded_legs_and_respects_cap tests/integration/test_snapshot_accounting.py::test_snapshot_nav_includes_financing_costs_and_matches_persisted_execution -vv -p no:cacheprovider --tb=short
~~~

## Retained seven-day NORMAL comparison

Window: Jan 1 2026 00:00 to Jan 8 00:00 EXCLUSIVE; 168 hourly steps.
Each strategy: seed 42, initial 2,000,000,000 cents all cash, zero positions/debt,
identical default TreasuryPolicy, NORMAL, NO stress schedule, zero delay,
naive source time UNSPECIFIED.

| Strategy | Persisted run ID |
| --- | --- |
| STATIC | 35a4e245-5df5-5fb2-ab9b-57564e2ea13e |
| REACTIVE | 369a28c1-3431-57d3-9198-ff317ed583bd |
| RESERVE_JUGGLER | e1864340-a26d-58b7-8a80-e574d6f54892 |

Each has 168 decisions and 169 portfolio valuations. Ledger counts 520/515/516;
investment movement counts 6/4/4. These runs are COMMITTED and queryable by
/report, unlike ephemeral HTTP comparison children. Parent HTTP smoke run:
278bf997-bda2-4d77-afd7-38abf223cdb4, live ledger still at step 1.

All amounts are INTEGER CENTS, not dollars.

| Metric | STATIC | REACTIVE | RESERVE_JUGGLER |
| --- | ---: | ---: | ---: |
| realized_interest_cents | 0 | 1141311 | 890431 |
| average_checking_cents | 2792842025 | 1626240014 | 1640600692 |
| penalties_cents | 100612504 | 0 | 24436237 |
| borrowing_costs_cents | 3043472 | 3032614 | 3035325 |
| borrowing_outstanding_cents | 0 | 0 | 0 |
| unpaid_borrowing_costs_cents | 0 | 0 | 0 |
| reserve_breaches | 32 | 32 | 32 |
| emergency_events | 32 | 32 | 32 |
| failed_payouts | 3 | 3 | 3 |
| unpaid_payouts_cents | 995156866 | 896138999 | 920826116 |
| sweeps | 3 | 2 | 2 |
| net_benefit_cents | -103655976 | -1891303 | -26581131 |
| ending_net_asset_value_cents | 287947822 | 290694628 | 290691917 |

No market acquisitions occurred: observed market P&L, transaction fees,
market-liquidation losses are zero, not unavailable-model substitutions.
Ending repo accrual is zero; model_evaluation is null. Full histories contain
168 actual closing points; public reports sample 100 actual points, no interpolation.
Failed payouts count intervals with ANY unpaid remainder, including partial
funding. Unpaid instructions are neither successful payouts nor invented loans
and are not silently retried.

Verified: source deposits = deposit ledgers; requested withdrawals = paid
payout ledgers + unpaid receipts; NAV = gross assets - liabilities; cash account
matches last valuation; net benefit = NAV - initial capital - settled external
cash flow. Shared receipt validation checks hourly continuity and financing.
See persisted-audit.json, report-*.json, snapshot-*.json, payout-trace-*.json.

## Real canonical optimizer-to-execution evidence

canonical-evidence.json records 168 calls to the ACTUAL
treasury_intelligence.optimizer.recommend_four_tier_allocation implementation.
The recording wrapper CALLS the original function, without substituting orders.

Request: opt-e1864340-a26d-58b7-8a80-e574d6f54892-20260101170000.
At Jan 1 17:00, inputs use 16:00 published prices, time_basis UNSPECIFIED.
Order 1534dc85-00ef-5515-b17c-5f1929c92fb4 recommends INVEST_REPO
12,219,618,731 cents with reserve 1,025,916,986.
Canonical response remains recommendation_only / NOT_EXECUTED.
A DISTINCT persisted SWEEP receipt with that order ID records actual fill
12,068,593,454 cents, capped by post-payout available cash.

Step-18 cash:
13,245,535,717 opening + 1,314,330,697 deposit - 1,465,355,974 paid withdrawals
- 12,068,593,454 sweep = 1,025,916,986 checking.
Repo principal 12,068,593,454 + accrual 59,351 + checking = NAV 13,094,569,791.
That step has zero debt, fees and market P&L.
TreasuryDecision receipt, RepoPosition, InvestmentMovement, sweep LedgerEntry
and four-tier snapshot are captured; recommendations were not rewritten to
pretend full fills.

The four separate bond/equity receipt tests inject controlled order fixtures but
use the REAL PostgreSQL accounting engine and Agent 2 reader. They verify
purchase/partial-sale quantities, basis, fees and P&L, NOT natural selection of
market trades by the canonical optimizer in this window. No measured trade was forced.

## Earlier 127 failures / ~$737m investigation

First 168 original rows, exact Decimal USD times 100 ONCE:
deposits 176,756,139,579 cents ($1,767,561,395.79);
NORMAL requested withdrawals 179,359,692,647 ($1,793,596,926.47).
Derived difference -2,603,553,068 cents; preserved supplied net_flow sum is
-26,035,530.63 USD (five-cent source reconciliation difference, not repaired).
First row deposits 6,660,184.94 -> 666,018,494 cents; withdrawals
6,852,980.85 -> 685,298,085 cents.

Each payout-trace file pairs source USD with actual requested/executed/unpaid
cents and status for every hour. Requested demand equals original source demand;
there is no double cent conversion or duplicate payout aggregation in this window.

READ-ONLY inspection of the previous reserve_juggler_prototype_test database
found NORMAL parent runs with HIGH_WITHDRAWAL scheduled from step 24:
f479f9ac-d014-4566-bc79-b571dafa0c15,
97a686a0-7588-41bd-90c1-908313a3a653,
dfac5a9c-d04e-4ca1-bdc0-f52322cf97e8,
4437f466-2c36-4a01-9ad4-d4d1f7a3d060.
See prior-schedules.txt. Runtime defaults this scenario to multiplier 1.5;
their legacy stress_factor field does not alter that default. /backtest carries
the parent's schedule and reports the INITIAL scenario label. Thus the NORMAL
label alone does not establish an unstressed workload.

Summing demand with that multiplier from step 24 gives 257,485,838,178 cents.
Subtract deposits, $20m initial cash and $50m principal cap: 73,729,698,599 cents
($737,296,985.99) funding gap BEFORE fees/timing. This explains the magnitude as
scheduled stress rather than demonstrating a unit-scaling defect. This is a
source-demand SUM, not an alternate financial simulator.

Original ephemeral child receipts/output tying exactly 127 failures to one
parent were not recovered: EXACT OLD 127 COUNT IS NOT VERIFIED. Do not claim
uniquely reconstructed old results. Fresh explicit NORMAL yields three unpaid
intervals per strategy, with actual unpaid amounts retained above.

## Availability and contractual H2

Rule: source t + 1 hour + configured publication delay <= decision T.
Naive source timestamps stay UNSPECIFIED. Top-level snapshot UTC timestamp is
SERVER OPERATION time, not organizer-source timezone provenance.

The named H2 test passes but does not itself configure positive delay. The new
focused cases explicitly use 0 and 3600 seconds, distinct rates, maturity,
cash/NAV reconciliation and extreme unavailable 08:00 quotes. Rollback-only
database fixtures modify rates/flows, NEVER the organizer CSV.

Both cases: entry Jan 1 17:00; contractual maturity, movement and cash credit
Jan 2 08:00. Closing valuation at 09:00 is the close of [08:00,09:00), NOT late
maturity. Interest settles once; no retroactive true-up at 09:00 or 10:00.
08:00 decisions see 07:00 data with zero delay / 06:00 data with one-hour delay.
Fixture principal 99,999,000,000 cents:
zero-delay interest 3,424,623 / settlement 100,002,424,623;
one-hour-delay interest 3,253,392 / settlement 100,002,253,392.
These are CONTROLLED TEST figures, not organizer backtest returns.
Current/future flow mutation tests also preserve earlier forecast and optimizer
targets. Broad causal/model certification is not implied.

Unchanged organizer SHA-256:
2e7c1d2e5b678e9975250211e7e0017022049c510e1dd90cd7f29e931837b0c5.

## Limitations / Member 1 acceptance gates

- RJ-M1-16 and seven gated shared-engine acceptance cases remain pending.
  Broad historical comparisons are NOT certified/unblocked.
- Full suite, 14/30-day matrix, production deployment and Docker application
  image: NOT VERIFIED in this focused cycle.
- Run reports truthfully say execution SHA is NOT_RECORDED_BY_RUNTIME; the
  external evidence and provider pin identify code, not fabricated provenance.
- HTTP comparison children intentionally roll back. Independent durable records
  were explicitly committed through the existing shared service.
- Current frontend sanitizer sends only strategy IDs. Dropdown seed/scenario/days
  are not generally authoritative; backend uses parent conditions/schedules and
  duration fallback. Only seven-day NORMAL with matching parent conditions is
  verified. Do not demo arbitrary dropdown changes as supported.
- Promotional copy, mock descriptions, “15-minute steps,” generic vault wording
  and global UTC labels are NOT organizer provenance or financial guarantees.
  Backend source remains naive/UNSPECIFIED. Four-tier-specific frontend helper
  methods still declare pending mappings; actual four-tier /snapshot was verified.
- Gross inflow/paid-outflow exports are absent from legacy metrics. Use source
  and persisted ledger evidence, not client zero fallbacks, as facts.
- Synchronous comparisons take minutes and have no job/cancellation API.
  Five-minute timeout is prototype accommodation, not a general latency guarantee.
- No natural bond/equity fill was observed in this NORMAL window; market posting
  checks used controlled recommendation fixtures, not performance claims.
- Graphify warns missing tree_sitter_sql and partially extracted existing
  RJQuantumPrism.jsx. Actual SQL relationships were restored from 22 PG tables.
- Companion browser note records final built-client checks and any NOT VERIFIED
  items. Nothing here certifies unrun checks or claims positive strategy returns.

