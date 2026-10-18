# Reserve Juggler backend and engine integration contract

## Authority and scope

Source requirements: `docs/MEMBER_2_SPEC.md`, titled **MEMBER 2 — COMPLETE DEVELOPMENT
AGENT PROMPT**, specifically sections 8, 11, 13, 15–16, 19–20, and 24–27.
The current milestone defines interfaces and persistence only; it does not
implement simulation, ledger execution, forecasting, fallback logic, or metrics.

`contracts/openapi.yaml` is the frozen public REST contract. It must exactly match
FastAPI's generated schema from `backend/app/v1_contracts.py` and
`backend/app/routers/runs.py`; the parity test enforces this. Update both together.
The published schema uses OpenAPI 3.1, matching the installed FastAPI generator.
`GET /api/v1/openapi.json` serves it; `/docs` and `/redoc` display it.

`database/migrations/002_member2_contract.sql` is the persistence definition for
the new contract. No migration or field name implies a working service.

## Confirmed incompatibilities in the initial repository

| Existing contract | Member 2 requirement | Resolution in this milestone |
| --- | --- | --- |
| Global `/api/treasury/*`, `/api/simulation/*` | UUID run-scoped `/api/v1/runs/*` | Publish only specified run routes and `/health` |
| Integer run IDs | UUID run IDs | UUID path validation and SQL primary/foreign keys |
| Dollar floats and `NUMERIC(18,4)` | Stored integer cents and basis-point rates | New strict integer schemas and `BIGINT` monetary columns |
| Implicit transaction direction by type | Explicit INFLOW/OUTFLOW, settlements in either direction | `direction` field, API validation, SQL checks |
| Four lowercase scenarios | Five specified uppercase scenarios | Shared `Scenario` enum and SQL constraints |
| Wall-clock/naive timestamps | UTC-aware virtual clock, 15-minute steps | Reject naive contract timestamps; normalize offsets to UTC |
| 60-minute forecast, duration in minutes | Default horizon 96 intervals, duration 288 steps | 1440-minute forecast default, 288-step run default |
| One undifferentiated vault balance | Locked and redeemable balances, position maturity/rates | Distinct snapshot fields and vault position/movement tables |
| Unlinked global rows | Run isolation and execution references | Run FKs, step uniqueness, ledger reference uniqueness |
| FastAPI default `detail` errors | `error_code`, `message`, `details` | Common error envelope and documented status codes |
| Hard-coded demo responses | Actual future measured results | New routes return explicit 501 until services exist |
| No agreed engine contract | Frozen Member 1 interface | Integration placeholder; missing agreement recorded below |

## HTTP contract

`/health` is the documented infrastructure exception to the `/api/v1` prefix.
There is no new `/api/v1/treasury/*` or `/api/v1/simulation/*` API.

| Method | Path | Success schema |
| --- | --- | --- |
| POST | `/api/v1/runs` | `RunCreated` (201) |
| GET | `/api/v1/runs/{id}/snapshot` | `SimulationSnapshot` |
| POST | `/api/v1/runs/{id}/advance` | `SimulationSnapshot` |
| POST | `/api/v1/runs/{id}/scenario` | `ScenarioApplied` |
| PATCH | `/api/v1/runs/{id}/policy` | `TreasuryPolicy` |
| GET | `/api/v1/runs/{id}/history` | `SimulationSnapshot[]` |
| GET | `/api/v1/runs/{id}/forecast` | `ForecastSummary` or null |
| GET | `/api/v1/runs/{id}/decisions` | `DecisionRecord[]` |
| GET | `/api/v1/runs/{id}/transactions` | `TransactionRecord[]` |
| POST | `/api/v1/runs/{id}/backtest` | `BacktestResult` |
| GET | `/api/v1/runs/{id}/report` | `PerformanceReport` |

All run paths require UUIDs. Every new run route returns 501 for schema-valid
requests until business services are implemented. No run is created and no
money moves in this milestone. Validation returns 422. The error envelope is
`{"error_code": "...", "message": "...", "details": {}}`, with details also
permitted as a list of validation locations/types. Future services must use
400 for invalid parameters, 404 for unknown runs, 409 for stale `expected_step`
or incompatible state, and 500 for unexpected errors. Schema publication does
not mean these future financial state transitions are already enforced.

Empty collections are `[]`. Unavailable initial forecast/decision/reserve and
uncomputed report metrics are null, never invented zero results. The initial
creation response is intentionally smaller than a complete financial snapshot.
Omitted or null PATCH policy fields mean unchanged; only non-null fields are
eligible for application by the future service.

Existing `/api/*` demo routes remain hidden compatibility endpoints using the
old schemas and public database tables, because frontend changes are excluded
from this task. They are not part of the v1 contract and do not satisfy Member 2.
Remove them after Member 3 migrates. Existing consumers of `/openapi.json` must
use `/api/v1/openapi.json` or `/docs`.

## Shared financial and data conventions

- USD amounts: strict integer cents, nonnegative unless explicitly signed.
  Monetary storage uses signed 64-bit `BIGINT`; no dollar floats enter v1.
- Rates: strict integer basis points. Policy contract range is 0–10000;
  `risk_percentile` is a dimensionless number strictly between 0 and 1.
- Timestamps: timezone-aware ISO 8601 normalized to UTC. Naive values fail validation.
- Interval: 15 minutes; 96 intervals/day. Default run: 288 steps (72 hours).
- Default horizon: 1440 minutes (96 intervals). Default vault: 96 steps at 500 bps.
- Scenario enum: NORMAL, HIGH_WITHDRAWAL, LOW_DEPOSIT, SETTLEMENT_DELAY,
  LIQUIDITY_SHOCK. Scenario changes apply prospectively in the future service.
- Net external cash flow is inflow minus outflow. Treasury movements are separate.
- Transaction and run IDs are UUIDs. Public `transaction_id`, `entry_id`, and
  `position_id` map respectively to SQL `transactions.id`, `ledger_entries.id`,
  and `vault_positions.id`; API `run_id` maps to `simulation_runs.id`.
- `vault_redeemable_cents` is the eligible subset of locked principal, not an
  additional asset balance to add to `vault_locked_cents`.
- Realized interest, accrued interest, penalties, borrowing costs, unpaid cash,
  and signed net benefit have separate fields. Averages round to integer cents;
  exact rounding and interest day-count policy await implementation agreement.

## Database/backend mapping

Migration 001 and existing ORM classes describe legacy dollar demo data. Migration
002 adds `reserve_juggler_v1` with the ten specified tables. Keeping the schemas
separate is an explicit compatibility decision: no dollar row is reinterpreted
as cents, no integer ID is guessed into a UUID, and no existing demo table is
overwritten. Future v1 repositories must explicitly use `reserve_juggler_v1`;
they are not implemented in this milestone. Existing `Base.metadata.create_all`
does not apply migration 002.

| Table | Backend/public mapping |
| --- | --- |
| `simulation_runs` | `CreateRunRequest`, `RunCreated`; `policy_json` is `TreasuryPolicy` |
| `transactions` | `TransactionRecord` |
| `ledger_entries` | `LedgerEntry`; unique `(run_id, reference_id)` |
| `vault_positions` | `VaultPosition` |
| `vault_movements` | Principal/interest/penalty cents, composite run/position FK |
| `forecasts` | `ForecastSummary` in `forecast_json`; `risk_json` reserved pending engine agreement |
| `liquidity_snapshots` | Snapshot scalar fields; forecast/decision joined by `(run_id, step)` |
| `treasury_decisions` | Action/amount/status; `explanation_json` is a string list; `decision_details_json` contains pre/post checking and executed fields |
| `scenario_events` | `ScenarioApplied`; parameters match the accepted scenario request |
| `backtest_results` | Strategy/scenario/seed; `metrics_json` is `FinancialMetrics` |

The SQL constraints define unique forecasts/snapshots/decisions per run step,
unique ledger references, and one movement of each type per full vault position.
Partial redemption is not defined. Future repositories must provide transactions
and state checks; unique keys alone do not implement execution idempotency.

Migration deployment is still manual through the existing migration workflow.
The existing Docker mounts put SQL files in nested init directories; automatic
application is not repaired here because Docker configuration is outside scope.

## Member 1 integration placeholder — NOT AN AGREED ENGINE CONTRACT

Member 1 owns `backend/app/engine/`; that directory does not exist in this checkout.
No prior `ENGINE_CONTRACT.md`, `engine_contract`, `forecast_cashflows`, or
`recommend_treasury_action` was found. The specification's equivalent function
examples do not establish the actual import path or exact signatures.

Existing interfaces discovered, unchanged:

```python
# forecasting/forecaster.py — CashFlowForecaster
forecast_flows(self, recent_transactions: List[Dict[str, Any]] = None,
               horizon_minutes: int = None) -> Dict[str, Any]

# backend/app/treasury/engine.py — TreasuryDecisionEngine
calculate_required_reserve(self, predicted_outflow: float,
                           predicted_inflow: float, uncertainty: float) -> float
evaluate_decision(self, checking_balance: float, vault_balance: float,
                  predicted_outflow: float, predicted_inflow: float,
                  uncertainty: float) -> Dict[str, Any]
```

The existing forecaster returns `timestamp`, `horizon_minutes`,
`predicted_inflow`, `predicted_outflow`, `predicted_net_flow`, `uncertainty`,
and `model_version`. The decision engine returns `decision_type`, `amount`,
`required_reserve`, `deployable_cash`, `forecast_value`, `forecast_uncertainty`,
`safety_buffer`, and `reason`; it returns neither timestamp nor ID. It takes a
single accessible vault balance rather than locked positions/maturity schedules.
These dollar-based functions are not wired into v1 and cannot be assumed to
satisfy Member 1's future interface. No mathematical implementation is edited.

`backend/app/services/treasury_adapter.py` is the sole reserved integration
location, currently only a labeled placeholder. A future authorized fallback
must identify itself as `fallback-baseline-v1`. No fallback calculations exist yet.

Still required from Member 1: callable import paths and exact signatures; history,
context, policy, forecast, risk and recommendation field schemas; units; net-flow
signs; uncertainty semantics; maturity/obligation representation; error behavior;
sync/async/state lifecycle; and engine version metadata. The adapter must reveal
only completed chronological history, never future realized transactions.

The existing balance-dependent safety-buffer description conflicts with the
existing engine's fixed-buffer calculation. That mathematical agreement remains
with Member 1; this milestone does not select or rewrite the formula.

## Contract decisions requiring team review

The spec fixes paths and core fields but leaves detailed shapes open. This
milestone selects 201 for creation, integer-cent averages, nullable initial
forecast/decision/metrics, list history/decisions/transactions responses, query
limits, the three uppercase strategy identifiers, the policy rate bounds above,
and additive PostgreSQL schema isolation. These are explicit backend contract
decisions for review, not claims of an agreed Member 1 function contract.
Scenario parameter dictionaries and engine `risk_json` remain extensible pending
their exact schemas; no corresponding operation succeeds yet. Other policy
settings (borrowing facility, sweep window, horizon) need their final field
definitions before those business features are implemented.

## Verification limits

The contract and regression suite passed against isolated in-memory SQLite.
Migration 002 has not been applied to PostgreSQL in this milestone: the local
Docker daemon was unavailable. A real PostgreSQL apply/rerun and constraint test
is required before v1 repositories begin using this schema.

`graphify update .` refreshed the repository code graph, including the new route
and schema modules. Graphify skipped SQL extraction because `tree_sitter_sql`
was unavailable; database relationships must be read directly from migration 002
until that extraction can be retried. No engine integration or ledger behavior
should be inferred from documentation/graph nodes.
