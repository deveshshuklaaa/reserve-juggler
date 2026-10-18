# Final local demo candidate: RJ-M1-16G-FINAL

Local-only branch `fix/rj-m1-16g-final-demo`, based on backend repair `88f9f45671c2d99279ffbd0ed83d3db1db07730b`, which contains quantitative repair `77f8e1c2732c38e19b2f098757249676a56ba96d`. Approved frontend `5bfee5c1ebe471d7dcba82fe8a85d5acf3f1c6be` was applied without its commit, then narrowly adapted. No merge or remote push.

## Running demo

- Production frontend: http://127.0.0.1:3017/command-center
- FastAPI: http://127.0.0.1:8017/docs ; actual schema `/api/v1/openapi.json`.
- Disposable PostgreSQL container `rj-m1-16g-r-postgres`, host port 55432.
- Retained database: `reserve_juggler_m2_test_final_0336a0fd2d`.
- Source: `C:/Users/Arvind Shekhawat/Downloads/treasury_4tier_dataset.csv`.
- SHA256: `2e7c1d2e5b678e9975250211e7e0017022049c510e1dd90cd7f29e931837b0c5`.
- 8,760 observations, 16 fields, 3 applied migrations, native 3600-second interval, source timezone UNSPECIFIED. CSV never changed.

PowerShell startup from this worktree (use the isolated database above, never the shared default):

```powershell
$env:DATABASE_URL = 'postgresql+psycopg2://postgres:postgres@127.0.0.1:55432/reserve_juggler_m2_test_final_0336a0fd2d
$env:ORGANIZER_DATASET_PATH = 'C:/Users/Arvind Shekhawat/Downloads/treasury_4tier_dataset.csv'
$env:PYTHONPATH = 'backend;.'
$env:OMP_NUM_THREADS = '1'
uv run --with-requirements backend/requirements.txt --with scikit-learn --with 'psycopg[binary]' python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8017
# Separate terminal:
cd frontend
npm ci --no-audit --no-fund
$env:VITE_USE_MOCKS = 'false'
$env:VITE_API_BASE_URL = 'http://127.0.0.1:8017'
npm run build
node node_modules/vite/bin/vite.js preview --host 127.0.0.1 --port 3017 --strictPort
```

The running verification server additionally records requests/responses and observes the original canonical optimizer in an external launcher. It returns its result unchanged; no instrumentation is required to run the committed app. Raw evidence remains outside Git in `../final-live/`.

## API compatibility changes

All real routes use `/api/v1/runs/{id}/...`; health remains `/health`. POST creates and advances runs, PATCH updates policy. The comparison adapter first creates a separate parent with selected scenario/seed, January 1 start selector, $20M capital and `days * 24` steps, then posts strategies/days to that parent's backtest. Live Shock Lab overlays are excluded. A five-minute timeout covers the synchronous comparison. Errors remain errors; there is no mock fallback.

A demonstrated auditability gap required one additive backend option: `BacktestRequest.retain_runs`, default false. Default evaluation still rolls back child runs. True commits the independently executed children and returns `BacktestReport.child_run_ids` keyed by public strategy names. Use a fresh parent per retained comparison; repeating retention on the same parent is not an idempotent replay. Retention and default rollback are tested separately. No executor, portfolio, optimizer, database schema or quantitative module was changed.

The Portfolio tab now reads the existing v1 `four_tier` projection directly. It does not present this projection as the canonical portfolio model. Cash, repo principal, bond/equity market values, reserve, liabilities and NAV come from that response. Engine models remain `treasury_intelligence.portfolio`; proposals remain distinct from execution receipts. The live clock reads `four_tier.timestamp`, not the response-generation timestamp. API recorded times are labelled separately; naive source chart timestamps are not converted to UTC. Real repo debit transactions display as outgoing.

## Tests and browser evidence

- A: frozen `test_hourly_forecasting.py`, `test_ml_forecasting.py`, `test_monte_carlo_risk.py` from `../frozen/tests/treasury_intelligence/`: **63 passed**, exit 0. Candidate imports verified. `../final-demo-command.json` records the complete uv/pytest command and test hashes; XML/log adjacent.
- B: `python ../run_final_checks.py final ...` selected chronology, payout, financing, ledger/NAV, execution adapter and causality tests: **30 passed**, exit 0, 48.31 seconds. Exact selection/command/environment in `../backend-final-command.json`. Includes 0/3600-second publication delays, +500M unpublished withdrawals, 08:00 exact-once maturity and actual canonical optimizer invocation.
- C: `python ../run_final_checks.py api tests/backtesting/test_final_demo_contract.py tests/backtesting/test_reports.py`: **18 passed**, exit 0, 7.08 seconds. Command manifest `../backend-api-command.json`. New route/savepoint tests explicitly stub the expensive comparison calculation, not financial runtime acceptance; the browser comparison uses the real engine.
- D: `cd frontend; npm test -- --reporter=dot`: **198 passed**, exit 0 (194 existing + 4 new integration tests).
- E: production build with the environment above: **PASS**, exit 0; Vite 6.4.4.
- F: actual production browser created a run, advanced 00:00 to 01:00, inspected four-tier balances/history, scheduled HIGH_WITHDRAWAL at step 2 and advanced. Persisted/HTTP checking matched $19,807,204.09 after step 1 and $18,142,677.09 after step 2. The UI then executed exactly one fresh three-strategy NORMAL comparison. HTTP responses and persisted database states matched. No mock-backed screenshots or synthetic metrics.

Two pre-existing pytest warnings name unavailable asyncio plugin configuration; these synchronous tests pass. No full unrelated matrix was run.

## Fresh measured comparison

Parent `877c2c5e-ffc9-4056-a613-3d467e0b2849`, seed 42, identical January 1 00:00 through January 7 23:00 source hours, 168 steps, $20M each, NORMAL, independent persisted state. All 504 real hourly receipts and 507 portfolio valuations were reconciled against reports. All financial outputs below are measured, including losses and unpaid obligations.

| Strategy | Persisted child run | Ending NAV | Net benefit | Unpaid payouts | Closing reserve deficits |
|---|---|---:|---:|---:|---:|
| STATIC_RESERVE | `394dcec4-1c28-55da-8b69-be249be7df79` | $2,871,105.36 | $-1,083,871.86 | $9,990,507.90 | 86 |
| REACTIVE_RESERVE | `d7a225b8-4f5a-5bf6-8704-8cb2994f926b` | $2,906,920.54 | $-254,645.63 | $9,197,096.85 | 136 |
| RESERVE_JUGGLER | `5e82b42b-d944-5875-92d3-28cb16ab130d` | $2,906,915.76 | $-297,129.58 | $9,239,576.02 | 50 |

Each strategy has 3 failed payout intervals and 32 recorded emergency-liquidity breach events. These are different from the closing reserve deficit counts above. The frontend now labels the legacy counter accordingly. Every original withdrawal reconciles to paid plus unpaid; overdraft principal is not income. Full deposits/withdrawals, fees, income, borrowing, market P&L, sweeps and ledger counts are in `FINAL_DEMO_EVIDENCE.json`. Ending debt and unpaid financing are zero for these runs; unpaid customer payouts remain explicitly recorded and are not automatically retried.

## Natural optimizer-to-ledger trace

Request `opt-5e82b42b-d944-5875-92d3-28cb16ab130d-20260101170000` uses opening cash 13,245,535,717 cents, reserve 1,025,916,986 cents and published observation 16:00. Proposed and actually filled repo: **12,219,618,731 cents** at 17:00 (previous defective fill 12,068,593,454). Decision `40e63857-5df0-4522-af27-5ca54660ae07`; order `f4863879-11fa-515e-9581-389664e2889d`; cash ledger `4eeade6c-03c9-4615-ac0c-6cba6afc9af6`; repo position `0c23faa9-3c1c-49f8-bec3-0cc0e4f8208d`. It matures once at January 2 08:00, principal plus 901,574 cents interest. The full proposal, executed receipt, ledger movement, position, maturity and closing NAV are preserved in the JSON evidence.

## Limits and sign-off

READY FOR DEMO with disclosed limitations, not blanket production/financial approval. The measured NORMAL comparison includes genuine payout failures and negative financial benefit; Reserve Juggler is not falsely declared the winner. Live `/history` currently returns only a current snapshot; comparison reports contain sampled actual hourly history. Canonical optimizer detail and calibrated model/Monte Carlo evaluation are not exposed by the live public projection; unavailable panels remain labelled. Legacy top-level timestamps are response metadata, not organizer source provenance. The API does not expose a retained comparison retrieval endpoint; preserve/export the returned comparison or inspect each retained child's `/report`. Broader scenario acceptance, policy tuning, and full release sign-off remain Member 1's responsibility.

Graphify CLI is unavailable on this machine; no graph was fabricated or unrelated generated artifacts changed. Main, the published prototype, frozen branch, quantitative worktree, backend repair worktree and Antigravity checkout were preserved. No remote push or merge was performed.
