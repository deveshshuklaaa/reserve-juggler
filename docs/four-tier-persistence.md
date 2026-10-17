# Four-tier persistence foundation (Milestone 2)

This milestone stores caller-supplied state. It does not replay observations,
post transfers, execute trades, calculate interest/P&L, or call an engine.
The organizer reader and original CSV are unchanged.

## Authoritative storage

`database/migrations/003_four_tier_persistence.sql` extends the existing
`reserve_juggler_v1` schema. `backend/app/persistence/models.py` maps the new
tables and the three extended tables using metadata separate from the legacy
public-schema ORM. Application startup does not create these tables.

| New table | Stored responsibility |
| --- | --- |
| `dataset_sources` | Dataset identity, byte hash, source path, native interval, validation diagnostics |
| `organizer_observations` | All 16 source columns, keyed by dataset and timestamp |
| `cash_accounts` | One Tier 0 balance per run and its latest ledger reference |
| `repo_positions` | Tier 1 principal, explicit entry/maturity, APY, interest, early redemption and proceeds |
| `bond_positions` | Tier 2 quantity, acquisition/current indices, value, yield/duration, P&L and liquidation costs |
| `equity_positions` | Tier 3 quantity, acquisition/current indices, value, volatility, P&L and slippage |
| `position_valuations` | Instrument-specific valuation/P&L history |
| `investment_movements` | Instrument-specific investment, redemption, maturity, interest, haircut and valuation events |
| `portfolio_valuations` | Four-tier assets, principal, liquidity, restrictions, liabilities and net value |
| `liquidity_breaches` | Explicit shortfall events |
| `overdraft_liabilities` | Borrowed/outstanding/repaid principal, APR, financing cost and breach reference |
| `overdraft_movements` | Borrowing, repayment and financing-cost events with cash-ledger references |

Extended existing tables:

- `simulation_runs`: source type, dataset, inclusive observation range, native
  interval, timezone status, and canonical configuration SHA-256. Historical
  runs need neither an invented random seed nor an invented timezone-aware clock.
- `ledger_entries`: source/run references and a separate naive `event_at`.
- `treasury_decisions`: four allocation targets, reserve, liquidity, expected
  in/out flows, uncertainty and source references. `ALLOCATE` is a storage action,
  not execution logic. Existing explanation/status fields remain.

The public schema, generic vault tables, forecast tables and compatibility data
are not converted or deleted. Migration 002 needed a syntax-only correction:
PostgreSQL requires quoting its `current_time` identifier. The column is not
renamed. That previously invalid SQL could not install the v1 schema as written.

## Precision and time

- Source USD amounts, percentage rates, indices, duration and quantities use
  unbounded PostgreSQL `NUMERIC` and Python `Decimal`. There is no bps conversion,
  fixed-scale rounding, or replacement of supplied `net_flow_usd`.
- Account, trade, cost and valuation money uses `BIGINT` integer cents. Bind
  validation rejects floating-point values, boolean cents and non-finite numbers;
  SQL also rejects non-finite numeric source/market values.
- Organizer timestamps use `TIMESTAMP WITHOUT TIME ZONE` with source/run status
  `UNSPECIFIED`. The code never guesses a timezone. Historical rows leave legacy
  timezone-aware clock fields empty. Synthetic runs declare `UTC`; naive event
  fields for those runs must contain UTC wall-clock values supplied by the caller.
- Repo entry/maturity are distinct fields; 17:00 to next-day 08:00 is representable.
  Automatic schedule execution and interest conventions remain future work.
- Optional calculated values are NULL until supplied, not manufactured zeroes.
  Equity has no guaranteed-interest field.

## Integrity and repository contract

`DatasetRepository.store()` stores a validated immutable reader snapshot,
rejects conflicting metadata/observations, and can safely repeat the same import.
It does not repair source values. `RunRepository` checks the SHA-256 identity of
canonical policy JSON. `RunScopedRepository` requires an explicit owning run and
matching source; all its reads filter by run ID.

Composite foreign keys enforce run/source, run/dataset, run/position,
run/ledger and run/liability ownership. Historical records reference actual
dataset observations. Unique per-run reference IDs reject duplicate financial
events. Position-linked records require exactly one matching tier-specific
position. Cash-changing investment/overdraft movements require a ledger entry.
Overdraft principal satisfies borrowed = outstanding + repaid. Portfolio total
equals the four asset values; net value equals total minus liabilities.

Repositories flush but never commit. The future caller must wrap related cash,
ledger, movement and liability changes in one database transaction. A repeated
movement reference raises an integrity error rather than executing it twice;
callers must roll back on errors. There is intentionally no automatic financial
posting, cross-record balance reconciliation, valuation, or strategy inside
repositories. Current position/account fields are state; movement/valuation
tables provide event history. Future execution must update them together.

Legacy records can retain NULL source type; new repository writes cannot. This
preserves existing rows without falsely assigning provenance to them. Direct SQL
is not an execution API and can bypass application-level validations.

## Applying and verifying migrations

Install `backend/requirements.txt`, configure `DATABASE_URL` to PostgreSQL, and
run from the repository root (PowerShell):

```powershell
$env:PYTHONPATH='backend'
python -m app.persistence.migrations
```

The runner rejects SQLite, applies ordered SQL in one transaction under a
PostgreSQL advisory lock, records normalized SQL SHA-256 in
`public.reserve_juggler_migrations`, and refuses changes to already recorded
migrations. Repeated application is a no-op. Existing installations without this
tracking table must review their schema before adopting the runner; file presence
alone does not prove deployment. The Compose nested migration-directory mounts
are not treated as evidence that initialization has run. No automatic deployment
or API startup behavior is changed here.

PostgreSQL integration tests require `PERSISTENCE_TEST_DATABASE_URL` pointing to
a disposable server/database named `reserve_juggler_m2_test*`, with permission to
create databases. Tests create uniquely named child databases and remove only
those children. They verify clean 001/002/003 application, no-op reapplication,
002 upgrade preserving legacy data, schema/constraints, exact source round trips,
run isolation, auditability, idempotency, liability/portfolio identities and
caller-owned rollback. Without that variable, integration cases explicitly skip.

```powershell
$env:DATABASE_URL='sqlite:///:memory:' # isolate existing legacy app tests
# Set PERSISTENCE_TEST_DATABASE_URL to your disposable PostgreSQL test server.
python -m pytest tests/backend/test_persistence.py -q
python -m pytest -q
```

No destructive down migration is provided: after financial records exist,
dropping the new tables/columns would lose provenance and financial history.
Back up before deployment; restoring a reviewed backup is the rollback procedure.
Fresh test databases are disposable. Existing tables/data are retained on upgrade.

## Deliberate boundaries / remaining contracts

No replay, trading, synthetic resampling, forecasting, Member 1 integration,
backtesting, metrics, API, OpenAPI or frontend behavior changes are included.
The existing public API still describes the earlier 15-minute generic-vault
contract; exposing four-tier historical state requires a separately agreed API
milestone. No Member 1 allocation mathematics or new engine signature is assumed.
Execution policy must later define accrual/rounding, liquidation/cost posting,
allocation semantics and movement-to-ledger reconciliation before executing them.

Graphify is refreshed from actual code and augmented with live PostgreSQL
table/foreign-key relationships because the optional SQL parser is unavailable.
The schema augmentation is reproducible and read-only toward the database:

```powershell
graphify update . --no-cluster
# PERSISTENCE_TEST_DATABASE_URL must identify a fully migrated PostgreSQL database.
python scripts/sync-persistence-graph.py
graphify cluster-only . --no-label
```

This preserves the verified CSV/provenance annotations. Historical replay remains
explicitly planned, not implemented. The script does not migrate databases or
change application behavior.
