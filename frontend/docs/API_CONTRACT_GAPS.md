# API contract gaps and frontend target

Status: **mock implementation working; real integration pending**. The assignment supplies an expanded target, while the checked-in `contracts/openapi.yaml` and existing FastAPI routes expose the older API. Neither backend nor shared contract was edited.

## Route comparison

| Target operation | Proposed route | Existing implementation |
|---|---|---|
| Health | GET /health | Same route |
| Create run | POST /api/v1/runs | POST /api/simulation/start; different request/response semantics |
| Snapshot | GET /api/v1/runs/{id}/snapshot | GET /api/treasury/state; global, not run-scoped |
| Advance | POST /api/v1/runs/{id}/advance | Absent |
| Scenario | POST /api/v1/runs/{id}/scenario | POST /api/simulation/scenario; currently only echoes configuration |
| Policy | PATCH /api/v1/runs/{id}/policy | Absent |
| Chart history | GET /api/v1/runs/{id}/history | Absent |
| Forecast | GET /api/v1/runs/{id}/forecast | GET /api/forecast/current; aggregate, not time series |
| Decisions | GET /api/v1/runs/{id}/decisions | GET /api/decisions/latest and /history; global |
| Transactions | GET /api/v1/runs/{id}/transactions | GET /api/transactions/recent; global |
| Backtest | POST /api/v1/runs/{id}/backtest | Absent |
| Report | GET /api/v1/runs/{id}/report | GET /api/metrics and /api/simulation/{id}/results; different schemas |

Old liquidity endpoint: GET /api/liquidity/current. Old OpenAPI mentions a reserved `/ws/treasury`; FastAPI does not implement it. The new frontend uses REST, not an assumed WebSocket service.

## Representation gaps

Old money fields (`amount`, `checking_balance`, `vault_balance`, forecast values, yield) are floating-point dollars. Target fields are integer cents with `_cents` suffixes. Old `current_apy` is a decimal fraction; new vault rates are basis points. Do not scale unrelated counts, ratios or durations.

Old scenarios are `baseline`, `payroll_spike`, `deposit_run`, `high_volatility`. Target enums are exactly `NORMAL`, `HIGH_WITHDRAWAL`, `LOW_DEPOSIT`, `SETTLEMENT_DELAY`, `LIQUIDITY_SHOCK`. These are not simple rename equivalents: the old payroll spike represents deposit inflows.

Target state is run-scoped and includes step/time, split locked/redeemable principal, policy, execution confirmation and structured explanation. Old state lacks vault maturity/penalties, explicit transaction direction, executed status and run versioning. Its Python timestamps are naive UTC values and do not guarantee the explicit timezone suffix required by the target.

The old simulation-start handler creates a database record without executing the simulation pipeline; duration is not used. Metrics are hardcoded and treasury endpoints can return baseline fallbacks. A successful old API response does not establish expanded capability support.

## Provisional payload details

The assignment freezes endpoint names and financial conventions but does not finalize every query/body/envelope. These frontend expectations are **integration proposals**, not modifications to the official contract:

| Operation | Frontend request / expected response |
|---|---|
| Create | `{seed, duration_steps, step_minutes:15, start_time, initial_checking_cents, initial_vault_cents}` → `{run_id, status}` |
| Advance | `{expected_step}` → acknowledgement; refresh snapshot and collections |
| Scenario | `{scenario, effective_step, parameters}` → `{id, scenario, effective_step, status}` |
| Policy | Patch containing supported policy keys → accepted policy; refresh |
| History, transactions, decisions | `{items:[...]}` envelope |
| Forecast | `?horizon_minutes=15|30|60|1440` → `{as_of, points, model_version, method}` |
| Backtest | `{scenario, days:7|14|30, seed, strategies:[STATIC,REACTIVE,RESERVE_JUGGLER]}` → `{status, source, scenario, days, seed, results}` |
| Report | Current financial report or accepted backtest status/results; user-controlled refresh for asynchronous jobs |

Scenario parameters use `duration_steps`, `multiplier_bps`, `reduction_bps`, `delay_steps`, `fraction_bps`, `shock_cents`. Percent/factor controls explicitly convert to these units. The policy uses `risk_percentile`, `operational_buffer_cents`, `min_sweep_cents`, `vault_rate_bps`, `early_redemption_penalty_bps`, `lock_steps`, `allow_early_redemption`.

Snapshot core follows the assignment example. Additional mock fields include `duration_steps`, `policy`, `positions`, `alerts`, `scenarios`, `deployable_surplus_cents`, realized/accrued earnings, costs, outstanding borrowing and net benefit. Missing optional values are not substituted with sample values.

Model evaluation, when available, is expected as `{baseline:{mae_cents,rmse_cents,model_version}, ml:{...}, sample_count, started_at, ended_at}`. It is absent in mock mode. Confirm this with Member 1/2 before live use.

## Integration checkpoints

1. Agree exact payloads/envelopes, supported durations/policy keys, pagination, execution-status enum and errors with Member 2.
2. Agree stale-step conflict semantics, transactional snapshot consistency and backtest job/report association.
3. Confirm forecast interval meaning and risk-method decomposition with Member 1.
4. Normalize/validate in the real adapter. Do not infer old-contract units in components.
5. Set `VITE_USE_MOCKS=false`, configure browser-reachable API URL, restart/rebuild and exercise every route.
6. Check CORS with Member 2. No browser-security workaround is used.

No target endpoints are claimed as live-connected until those checks succeed. Real mode surfaces network, HTTP and schema errors and never silently falls back to mocks.
