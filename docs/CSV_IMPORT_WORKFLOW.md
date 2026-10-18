# CSV import and simulation workflow

## Use the integrated local demo

- Frontend: http://127.0.0.1:3018/command-center
- API and interactive contract: http://127.0.0.1:8018/docs
- Port 3017 remains the earlier preview-only app.

1. Choose **Upload CSV**, then select an organizer CSV.
2. Review its row count, dates, first observations and reconciliation warnings locally.
3. Choose **Start CSV simulation**. The original File bytes are now sent to the backend, independently validated and stored under a SHA-256 dataset identity. Reuploading identical bytes reuses the dataset.
4. The app creates a new simulation bound explicitly to that dataset, with $20M opening cash and one step per hourly observation. Step or Play executes the shared backend engine. Reset creates a fresh run from the same file; existing runs remain stored.
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

- 204 frontend tests across 11 files passed; live-mode production build passed.
- 192 backend regression checks passed, covering imports, original source validation, reports, shared runtime, accounting and chronology. Final import checks also passed after adding the typed response; 26 API compatibility checks passed after refreshing the published OpenAPI contract.
- Actual browser demo stored the 3,500-row file, created a run, advanced to step 12 and completed the three-strategy seven-day comparison. A read-only database audit reconciled 504 source-hour receipts, including paid plus unpaid withdrawals. All three children used the uploaded dataset and preserved source diagnostics.
- Financial results may include negative net benefit and payout failures. No winner is assumed or financial formula changed by this feature.
- Graphify update was attempted; the CLI is unavailable on this machine. The existing graph was preserved.
- No push, merge, protected-branch edit, original CSV edit or old demo database modification.
