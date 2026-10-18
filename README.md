# Reserve Juggler — The Idle Cash Problem

[![CI](https://github.com/deveshshuklaaa/reserve-juggler/actions/workflows/ci.yml/badge.svg)](https://github.com/deveshshuklaaa/reserve-juggler/actions/workflows/ci.yml)

A HackForge 2026 treasury simulation prototype for balancing customer liquidity needs against investment returns. Reserve Juggler replays hourly cash flows, forecasts liquidity requirements, recommends allocations, and records execution through a shared PostgreSQL-backed accounting engine.

The integrated application includes a React dashboard, FastAPI backend, four-tier portfolio, CSV import, stress scenarios and historical strategy comparisons. It simulates money movement; it does not connect to customer accounts or banking rails.

## Four-tier treasury model

| Tier | Instrument | Liquidity and valuation |
| --- | --- | --- |
| 0 | Cash buffer | Immediately available; 0% APY. |
| 1 | Overnight repo | Dataset APY; 17:00 entry and contractual 08:00 next-morning maturity; 0.5% early-break cost. |
| 2 | 2Y sovereign bonds | Dataset price-index valuation, yield and modified duration; 2% liquidation haircut. |
| 3 | Growth equities | Dataset market-index valuation and volatility; 15% emergency liquidation slippage. Returns are not guaranteed interest. |

Emergency overdraft is a separate liability with dataset-driven financing costs, not investment income. Cash availability, investment value, fees, market P&L, debt and net asset value are distinct accounting quantities.

## Data and decision timing

- The bundled authoritative source is [treasury_4tier_dataset.csv](treasury_4tier_dataset.csv): **8,760 hourly observations and 16 columns**.
- Source financial values use precision-preserving Decimal representations. Execution and report monetary amounts use integer cents.
- Supplied `net_flow_usd` is preserved. Reconciliation differences are reported, not silently corrected; customer execution uses deposits and withdrawals.
- There is no fabricated 15-minute historical data. One simulation step processes one source hour.
- Source timestamps remain naive with `time_basis=UNSPECIFIED`; do not interpret them as UTC.
- At decision time `T`, an observation timestamped `t` is eligible only if `t + 1 hour + publication_delay <= T`. Publication delay defaults to zero and is configurable.
- Repo clock events remain at 17:00 and 08:00. Delayed rates use the last eligible APY for each earning hour, without automatic retrospective interest true-ups.

The runtime integrates the canonical `recommend_four_tier_allocation()` boundary. Recommendations are separate from actual ledger-backed fills and may be constrained by liquidity and policy.

## Architecture

```text
Bundled organizer CSV / validated upload
                  ↓
Persisted dataset + hourly observations
                  ↓
Publication-eligible history → Forecast / risk / allocation
                  ↓
Shared hourly execution engine
                  ↓
Cash + repo + bonds + equities + overdraft
                  ↓
Receipts / ledger / valuations → API → Dashboard and reports
```

Historical comparisons run `STATIC`, `REACTIVE` and `RESERVE_JUGGLER` with independent state and matching source windows, initial capital, scenario, seed and policy. Supported windows are **7, 14 and 30 days** (168, 336 and 720 hourly steps).

Scenarios: `NORMAL`, `HIGH_WITHDRAWAL`, `LOW_DEPOSIT`, `SETTLEMENT_DELAY` and `LIQUIDITY_SHOCK`. Scenario overlays do not modify the source CSV.

## Quick start — real backend

Requirements: Python 3.10+, Node.js 20+, Docker Compose and a running Docker Linux engine. The commands below use PowerShell from the repository root.

### 1. Start PostgreSQL and install backend dependencies

```powershell
Copy-Item .env.example .env
docker compose up -d db
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend/requirements.txt
$env:PYTHONPATH = 'backend;.'
```

Copy environment templates only on first setup; preserve any existing local configuration. Wait for PostgreSQL to be ready before continuing. The default development connection in `.env` is:

```text
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/reserve_juggler
ORGANIZER_DATASET_PATH=treasury_4tier_dataset.csv
```

Change these for your environment. Use a dedicated database for tests and verification; never point test fixtures at a database containing runs you need to keep. Do not commit `.env` files or credentials.

### 2. Apply migrations and register the bundled dataset

```powershell
python -m app.persistence.migrations
python -c "from sqlalchemy.orm import Session; from app.database import engine; from app.persistence.repositories import DatasetRepository; from app.data.organizer import OrganizerDatasetSource; s=Session(engine); DatasetRepository(s).store(OrganizerDatasetSource().load()); s.commit(); s.close()"
```

Run migrations explicitly; application startup is not a replacement for the SQL migration process. The dataset loader reads the bundled CSV without rewriting it.

### 3. Start FastAPI

```powershell
python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

Optional fitted-ML forecasting requires `scikit-learn`, installed separately with `python -m pip install scikit-learn`. The default live runtime uses the seasonal forecast. Fitted models must have publication-eligible training **and calibration** provenance; older artifacts without that provenance need refitting. Only load trusted model artifacts.

### 4. Start the frontend in another terminal

```powershell
Set-Location frontend
Copy-Item .env.example .env.local
npm ci
npm run dev -- --host 127.0.0.1 --port 3000
```

The frontend template uses:

```text
VITE_USE_MOCKS=false
VITE_API_BASE_URL=http://localhost:8000
```

- Dashboard: [http://localhost:3000/command-center](http://localhost:3000/command-center)
- Health: [http://localhost:8000/health](http://localhost:8000/health)
- Interactive API docs: [http://localhost:8000/docs](http://localhost:8000/docs)
- Runtime OpenAPI: [http://localhost:8000/api/v1/openapi.json](http://localhost:8000/api/v1/openapi.json)

Use Docker for PostgreSQL and the host-run services above for this prototype. The existing backend Dockerfile does not package the current quantitative modules, migrations or organizer CSV; full-stack `docker compose up --build` is not the documented end-to-end setup.

## Demo workflow and CSV imports

1. Create a simulation using the bundled dataset, or choose **Upload CSV** to preview a compatible file.
2. Choose **Start CSV simulation** to upload its original bytes, validate them on the server, persist the dataset and create a run bound to its identity.
3. Step one hour or use playback: **Fast** batches 24 hours; **Turbo** batches 168. Every hour still executes individually. Pause takes effect after the in-flight batch.
4. Inspect Portfolio, Forecasts and Activity; export the snapshot or comparison.
5. Use Strategy Arena for a supported 7-, 14- or 30-day comparison. Shorter datasets can simulate but cannot run a seven-day comparison.

**Upload limits:** UTF-8, at most **2 MiB**, **2–5,000** populated hourly rows, exact organizer headings, continuous hourly timestamps and exact-cent customer flows. Fully empty trailing records are ignored. The full 8,760-row bundled source is loaded through the backend loader, not the bounded upload endpoint. The separate three-column mock CSV format is not accepted for live execution.

Identical uploaded bytes reuse their SHA-256 dataset identity. Runs remain in PostgreSQL, but browser workspace selection is in memory; reloading and reuploading starts a fresh run rather than restoring the previous selection.

See [CSV workflow and validation](docs/CSV_IMPORT_WORKFLOW.md) for details.

## API overview

New application routes use **`/api/v1`**; health remains `/health`. Legacy compatibility routes are not the authoritative historical API.

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/v1/datasets` | Import raw `text/csv` bytes and return dataset identity/validation. |
| POST | `/api/v1/runs` | Create a run; optional `dataset_id` selects an uploaded dataset. |
| GET | `/api/v1/runs/{id}/snapshot` | Current state, four-tier projection and source metadata. |
| POST | `/api/v1/runs/{id}/advance` | Execute 1–168 hours atomically with `expected_step`. |
| POST | `/api/v1/runs/{id}/scenario` | Apply a scenario overlay. |
| PATCH | `/api/v1/runs/{id}/policy` | Update run policy. |
| GET | `/api/v1/runs/{id}/forecast` | Forecast projection. |
| GET | `/api/v1/runs/{id}/decisions` | Decision records. |
| GET | `/api/v1/runs/{id}/transactions` | Transaction records. |
| POST | `/api/v1/runs/{id}/backtest` | Compare a requested strategy subset over a supported window. |
| GET | `/api/v1/runs/{id}/report` | Execution-based metrics and accounting details. |

Backtests accept only integer `days` of 7, 14 or 30. If omitted, the parent must have exactly 168, 336 or 720 steps; unsupported implicit durations return 422. Public strategy labels are `STATIC_RESERVE`, `REACTIVE_RESERVE` and `RESERVE_JUGGLER`; requests also normalize `STATIC` and `REACTIVE` aliases.

Comparisons default to ephemeral child runs. `retain_runs: true` persists children and returns `child_run_ids`; use a fresh parent for each retained comparison. Repeating retention on the same parent is not an idempotent replay. Unavailable model evaluation is `null`, not a fabricated score.

See the [OpenAPI contract](contracts/openapi.yaml), [engine contract](docs/member1/ENGINE_CONTRACT.md) and [backtest service contract](docs/BACKTEST_SERVICE_CONTRACT.md) for exact structures.

## Repository guide

| Path | Responsibility |
| --- | --- |
| `backend/app/data/` | Immutable organizer reader and diagnostics. |
| `backend/app/persistence/` | ORM models, repositories and migration runner. |
| `backend/app/services/` | Shared hourly execution, accounting, market execution, dataset import and engine adapter. |
| `backend/app/backtesting/` | Isolated strategy orchestration, receipt reading and reports. |
| `backend/app/routers/` | FastAPI endpoints. |
| `treasury_intelligence/` | Canonical quantitative contracts, forecasting, risk and optimizer. |
| `frontend/` | React 19 + Vite dashboard and API client. |
| `database/migrations/` | SQL schema migrations. |
| `contracts/` | Checked-in OpenAPI specification. |
| `tests/` | Backend, quantitative, persistence, backtesting and integration tests. |
| `simulation/`, `forecasting/` | Legacy synthetic/compatibility components. |
| `graphify-out/` | Derived project knowledge graph; source, tests and contracts remain authoritative. |

## Development checks

From an activated backend environment at the repository root:

```powershell
$env:PYTHONPATH = 'backend;.'
python -m pytest tests/treasury_intelligence tests/backend tests/backtesting -v
# Full Python suite, with dedicated PostgreSQL test databases configured:
python -m pytest tests -v
```

PostgreSQL fixtures use suite-specific settings such as `PERSISTENCE_TEST_DATABASE_URL` and `BACKTEST_TEST_DATABASE_URL`; consult the relevant fixtures before running them. Missing optional dependencies or integration settings can skip tests, so a passing count alone is not full financial acceptance.

Frontend checks, from `frontend/`:

```powershell
npm test
npm run build
```

## Prototype status and limitations

- Historical comparisons and strategy rankings remain **provisional pending RJ-M1-16 sign-off**. Do not claim certified superiority or guaranteed returns.
- Negative net benefit, reserve deficits, borrowing and unpaid payouts are valid outcomes and must remain visible. Overdraft draws are not income; unpaid customer obligations are not successful payouts or automatically retried.
- Default tier limits do not naturally exercise bond/equity purchases. A working repo-based demo does not establish multi-asset strategy superiority.
- Live `/history` currently returns a current snapshot, not a complete historical series; comparison reports contain sampled executed checking history.
- The live projection does not expose all optimizer/calibrated-model/Monte Carlo detail. Unavailable evaluation must remain explicitly unavailable.
- There is no retained-comparison retrieval endpoint; export the returned comparison or inspect retained child reports.
- Evidence documents describe the revisions and environments in which their checks ran; their historical results are not a fresh certification of every later merge.

Further reading: [submission setup and hotfix caveats](docs/SUBMISSION_HOTFIX.md), [organizer data rules](docs/organizer-data.md), [prototype handoff](docs/PROTOTYPE_RELEASE_HANDOFF.md), [recorded demo evidence](docs/FINAL_DEMO_HANDOFF.md) and [contribution workflow](CONTRIBUTING.md).
