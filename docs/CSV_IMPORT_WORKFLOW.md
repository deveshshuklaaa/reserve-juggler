# CSV import and simulation workflow

## Use the integrated local demo

- Frontend: http://127.0.0.1:3018/command-center
- API and interactive contract: http://127.0.0.1:8018/docs
- Port 3017 remains the earlier preview-only app.

1. Choose **Upload CSV**, then select an organizer CSV.
2. Review its row count, dates, first observations and reconciliation warnings locally.
3. Choose **Start CSV simulation**. The original File bytes are now sent to the backend, independently validated and stored under a SHA-256 dataset identity. Reuploading identical bytes reuses the dataset.
4. The app creates a new simulation bound explicitly to that dataset, with $20M opening cash and one step per hourly observation. Step processes one hour. Play defaults to **Fast (24 hours per batch)**; choose **Turbo (168 hours per batch)** to process a week at a time. Every hour still executes and persists individually. Pause takes effect after the in-flight batch. The final batch stops exactly at the end of the dataset. Reset creates a fresh run from the same file; existing runs remain stored.
5. Use Portfolio, Forecasts and Activity to inspect the run. Strategy Arena compares a 7-, 14- or 30-day prefix of the same dataset using independent $20M runs. Only supported windows are offered. A dataset shorter than seven days can simulate normally; comparisons are disabled.
6. Export the snapshot or comparison. Dataset identities and hashes are also returned by the backend snapshot/report contracts.

## File contract

Use the 16-column organizer schema shown in the live dialog and the downloadable template. The three-column cents/UTC template remains a separate local mock replay format, and is explicitly disabled for live execution.

- UTF-8, at most 2 MiB, 2–5,000 populated hourly rows.
- Exact organizer headings; timestamps `YYYY-MM-DD HH:00:00`, strictly increasing and continuous. Source timezone stays UNSPECIFIED.
- Flags `True` / `False`. Repo sweep opens only at 17:00; maturity flag is true only at 08:00, matching the existing engine contract.
- Plain finite decimals, at most 16 integer and 12 fractional digits. Deposits and withdrawals must be exact cents. Each customer flow and total in each direction must fit JavaScript-safe integer cents.
- Existing positive/nonnegative/haircut rules apply. Net-flow differences are diagnostics, not automatic corrections. The executor uses deposits and withdrawals; it does not replace them with supplied net flow.
- Only fully empty trailing records are ignored. Interior blank rows and partially filled records are rejected.
- No source-file edits, timezone assignment, resampling or invented market values.

## API and persistence

`POST /api/v1/datasets`, Content-Type `text/csv`, accepts raw CSV bytes. The streaming endpoint enforces the size bound before buffering further data and validates the complete file before writing. It returns dataset_id, content hash, row count, source dates, validation status and exact reconciliation diagnostics. Errors: 413 size, 415 media type, 422 invalid data. Writes commit atomically; duplicates reuse immutable content identity.

`POST /api/v1/runs/{id}/advance` accepts 1–168 steps. Requests are atomic and require the current expected_step. Overruns are rejected before execution; failures roll back the entire batch. Client batch requests allow up to 120 seconds, and automatic playback issues only one request at a time.

`POST /api/v1/runs` accepts optional `dataset_id` plus the existing configuration. Its duration must fit that dataset's source window. With no dataset_id it selects the bundled organizer explicitly, so an upload cannot become the accidental default source.

Snapshots include source_dataset and duration_steps. Comparisons use the selected run's persisted source, propagate its dataset_id to each child, and return dataset_id/dataset_sha256 in reports. The strict standalone authoritative-data backtest remains the default; the HTTP route explicitly opts into validated persisted uploads. Existing databases already have dataset_sources and organizer_observations; no migration is required.

## Start or rebuild

Use the existing PostgreSQL migration/bootstrap procedure from FINAL_DEMO_HANDOFF.md against a dedicated database. The local integrated demo uses a fresh database named in the external runtime manifest. Set DATABASE_URL to that database before starting the backend:

```powershell
$env:PYTHONPATH = 'backend;.'
$env:OMP_NUM_THREADS = '1'
python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8018
# Separate terminal, frontend directory:
$env:VITE_USE_MOCKS = 'false'
$env:VITE_API_BASE_URL = 'http://127.0.0.1:8018'
npm run build
node node_modules/vite/bin/vite.js preview --host 127.0.0.1 --port 3018 --strictPort
```

Uploaded datasets and runs persist in PostgreSQL. Browser workspace selection is held in memory; after a page reload, uploading the same file reuses its dataset and starts a fresh run. This feature does not add a saved-run browser or change that existing selection behavior.

## Verification

- **Frontend Suite**: 207 tests passed across 12 files (including fastPlayback.test.jsx); live-mode production build passed. Fast playback tests cover day (24h) and week (168h Turbo) batching, exact completion, pause after in-flight batch, and concurrency safeguards.
- **Backend & Backtesting Suites**:
  - test_fast_simulation.py, test_runtime_acceptance.py, test_reports.py: 36 passed in 42.54s.
  - test_checkpoint_verification.py, test_final_demo_contract.py: 23 passed in 32.98s.
  - test_dataset_import.py, test_execution_chronology.py: 29 passed in 26.68s.
  - test_api_versioning.py: 26 passed in 1.44s with exact OpenAPI schema match.
  - test_shared_engine_integration.py (test_actual_shared_engine_comparison[7-SETTLEMENT_DELAY]): passed in 86.29s with full receipt validation and determinism.
- **Full 3,500-Hour CSV Simulation**:
  - Completed all 3,500 hours across 21 advance batches (20x168 + 1x140) in 317.28s (~15.1s average per 168-hour week).
  - Exact match against pre-aggregation baseline prefix verified at step 2,184 (checking: 883,859,284 cents, NAV: 7,318,067,211 cents, repo principal: 6,434,011,550 cents, liabilities: 0).
  - Full report generated and stored in outputs/fast-csv-full-run.json with status COMPLETED and baseline_prefix_matched: true.
- **Performance Optimizations**:
  - paid_financing_costs: Implemented via exact SQL aggregation (select(OverdraftMovement.liability_id, func.coalesce(func.sum(OverdraftMovement.financing_cost_cents), 0)).where(...).group_by(...)), preserving loan isolation and historical cutoff (occurred_at < before) while eliminating per-hour ORM loop overhead.
  - Repaired expected_cash_legs in `read_hour_receipt` to check or any(m.cash_delta_cents != 0 for m in loans) rather than len(loans) > 0, properly accounting for non-cash overdraft interest accruals (FINANCING_COST).
- **Live Demo Verification**:
  - Backend running on http://127.0.0.1:8018 connected to PostgreSQL `reserve_juggler_m2_test_csv_e38b79fa31`.
  - Frontend preview running on http://127.0.0.1:3018 (/command-center).
- Financial results may include negative net benefit and payout failures. No winner is assumed or financial formula changed by this feature.
- Graphify update was attempted; the CLI is unavailable on this machine. The existing graph was preserved.
- No force-push, merge to protected branches, alteration of source CSVs, or mutation of previous demo databases.

## Fast execution implementation

A transaction-scoped forecast history buffer reads four exact source columns and appends only newly published rows. It clears at each request/strategy boundary and on failure. The canonical forecast still validates the entire causal prefix and calculates the same historical uncertainty. There is no truncation, resampling or substitute simulation engine.
