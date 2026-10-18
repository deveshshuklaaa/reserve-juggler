# PENDING BACKEND MAPPINGS FOR MEMBER 2 (FASTAPI INTEGRATION)

## Verified branch audit — 2026-10-18

Inspected Member 1 `feat/treasury-intelligence` at `14a8d72` and Member 2
`feat/simulation-backend` at `52e58bc`. The proposals below are historical frontend
assumptions, not the finalized quantitative contract.

Member 1 authority: `docs/member1/MEMBER3_FRONTEND_FIELDS.md` and
`docs/member1/MEMBER2_INTEGRATION.md` on its branch. Canonical portfolio fields are
`cash`, `repo_positions`, `bond_positions`, `equity_positions`, `overdrafts`, and
`valuation`. Optimizer outputs use `decision.targets`, `decision.reserve`,
`decision.orders`, `decision.expected_costs`, `decision.explanations`,
`decision.feasible`, and `summary_action`. Existing frontend tier models require an
explicit adapter; their defaults must not fill missing LIVE financial values.

- Money fields ending `_cents` are integers; reject unsafe JavaScript integers.
- Decimal strings preserve precision. `_pct` means percentage points, not basis
  points; allocation limits can still use basis points.
- Hourly timestamps can have `time_basis=UNSPECIFIED`; never append `Z` or infer a
  browser timezone. The old 15-minute UTC convention is not universal.
- Proposed orders are `NOT_EXECUTED`. Feasibility is not an execution receipt.
  Only Member 2 can establish actual fills, ledger movements, and updated balances.
- Preserve source `net_flow_usd` separately from forecast deposits-minus-withdrawals.
- Scenario-quantile reserve already includes uncertainty; do not add a second
  uncertainty allowance. Provisional uncertainty is not a calibrated confidence band.
- Available cash, restricted liquidity, hypothetical liquidation proceeds, market
  losses, and portfolio downside are distinct. Modeled outcomes are estimates.
- Preserve `search_truncated`; a feasible selected candidate is not proof of a
  globally optimal allocation. Actual payout failure is unknown without execution.

Member 2 registers `/api/v1/runs` in `backend/app/main.py`, but every handler in
`backend/app/routers/runs.py` currently calls `unavailable()` and returns HTTP 501.
Persistence foundations do not establish working simulation services. LIVE mode
must surface this failure rather than substitute mock success.

Integration gate: Member 2 must expose working create/advance/snapshot/forecast/
decision/transaction routes with canonical payload examples and execution receipts.
Then verify Simulation → Forecast → Allocation → Execution → Updated Dashboard.
No live end-to-end verification has been completed by this audit.

Additional frozen v1 request/response differences (not silently coerced):

| Current frontend/mock input | Member 2 frozen v1 contract |
| --- | --- |
| initial_checking_cents, initial_vault_cents, step_minutes | initial_cash_cents; no opening vault or step_minutes input |
| risk_percentile=95 | risk_percentile=0.95 |
| min_sweep_cents, vault_rate_bps, lock_steps, allow_early_redemption | minimum_sweep_cents, vault_yield_bps, vault_lock_steps, early_redemption_allowed |
| Scenario request includes effective_step | ScenarioRequest has scenario and parameters only |
| STATIC / REACTIVE strategy IDs | STATIC_RESERVE / REACTIVE_RESERVE |
| Backtest request includes days, seed, scenario | BacktestRequest currently accepts only strategies |
| Forecast points and requested horizon query | ForecastSummary has reserve components/model version; route has no horizon parameter |
| Snapshot status, policy, positions, alerts and extended financial totals | These fields are absent from the frozen SimulationSnapshot |

Resolve these in a documented wire adapter after Member 2 confirms the intended
service contract. In particular, do not silently drop opening vault capital or
describe different strategy definitions as equivalent. The current LIVE client is
not certified compatible merely because the route names match.

**Project**: Reserve Juggler — HackForge 2026  
**Deliverable**: Task F1A Requirement  
**Target Milestone**: F1B / F6 Live Backend Integration  
**Date**: October 2026

---

## Overview

Before frontend milestone **F1B** (Live Backend Handshake) and **F2** (Four-Tier UI Presentation), Member 2 must confirm the schema envelopes, field names, and execution semantics listed below.

The frontend has already implemented internal normalization models, precision formatting, and deterministic mock fixtures in Task F1A to operate without blocking on backend development.

---

## 1. Portfolio Snapshot Schema (`GET /api/v1/runs/{id}/snapshot`)

Member 2 must confirm the nesting structure for four-tier asset valuations:

* **Proposal A (Recommended — Enveloped under `four_tier`)**:
  ```json
  {
    "run_id": "run-101",
    "step": 42,
    "timestamp": "2026-01-02 18:00:00",
    "checking_cents": 2000000000,
    "required_reserve_cents": 450000000,
    "four_tier": {
      "tier0": { "checking_cents": 2000000000, "required_reserve_cents": 450000000, "deployable_surplus_cents": 1550000000 },
      "tier1": { "principal_cents": 600000000, "repo_apy_bps": 525, "repo_apy_decimal": "5.2500", "accrued_interest_cents": 86301, "status": "LOCKED", "early_break_fee_bps": 50 },
      "tier2": { "notional_cents": 400000000, "market_value_cents": 411167512, "current_price": "101.2500", "ytm_bps": 445, "modified_duration": 4.25, "haircut_bps": 200, "unrealized_pnl_cents": 11167512 },
      "tier3": { "market_value_cents": 222750000, "current_price": "445.5000", "volatility_bps": 1680, "slippage_bps": 1500, "unrealized_pnl_cents": 12750000 },
      "overdraft": { "borrowing_outstanding_cents": 0, "financing_rate_bps": 1000, "financing_cost_cents": 0, "liability_status": "CLEARED" }
    }
  }
  ```
* **Status**: Pending Member 2 confirmation. The frontend accepts either enveloped `four_tier` or top-level tier keys.

---

## 2. Source Historical Timeline & Timestamps (`GET /api/v1/runs/{id}/history`)

* **Question**: Will historical observation timestamps be returned in raw organizer format (timezone-unspecified, e.g. `"2026-01-01 17:00:00"`) or standard ISO string with UTC offset (e.g. `"2026-01-01T17:00:00Z"`)?
* **Frontend Requirement**: If the source CSV is timezone-unspecified, the backend should preserve the source string without forcing an arbitrary timezone conversion. The frontend utility `formatSourceTimestamp()` handles both safely.

---

## 3. Overnight Repo 17:00 Sweep Window

* **Question**: Does the backend simulation enforce strict 17:00 entry window gating for Tier 1 sweeps?
* **Expected Field**: `entry_window_open: boolean` in repo position or snapshot state.
* **Maturity**: Settled at next-day 08:00 step. Principal and interest credited to Tier 0 checking.
* **Early Break Penalty**: Fixed at 50 bps (0.5%) if redeemed prior to 08:00 maturity.

---

## 4. Multi-Asset Decisions & Execution Semantics (`GET /api/v1/runs/{id}/decisions`)

* **Actions**: Member 2 must confirm support for multi-asset decision enums:
  * `HOLD`, `INVEST_REPO`, `INVEST_BONDS`, `INVEST_EQUITIES`, `REBALANCE`, `LIQUIDATE`, `WITHDRAW`, `SWEEP`, `LIQUIDITY_WARNING`.
* **Execution Status**: Must include:
  * `executed: boolean` (must remain `false` for unconfirmed recommendations).
  * `execution_status: "RECOMMENDED" | "EXECUTED" | "NOT_REQUIRED" | "REJECTED"`.

---

## 5. Price Indices & Precision Formats

* **Question**: Are Tier 2 bond price index and Tier 3 equity index returned as:
  1. High-precision decimal strings (e.g. `"101.2500"`, `"445.5000"`)?
  2. Fixed-point integer scaled values (e.g. `1012500` with 4 decimal places)?
* **Frontend Handling**: Frontend supports both and preserves strings to prevent IEEE-754 precision loss.

---

## 6. Overdraft Liability Schema

* **Fields Required**:
  * `borrowing_outstanding_cents` (`integer cents`): Principal debt.
  * `financing_rate_bps` (`integer basis points`): 1000 bps default.
  * `financing_cost_cents` (`integer cents`): Accumulated interest expense.
  * `liability_status` (`string`): `"ACTIVE" | "CLEARED"`.

---

## 7. Action Items for Member 2

1. Review `frontend/docs/FOUR_TIER_FRONTEND_CONTRACT.md`.
2. Verify matching Pydantic schemas in `backend/app/schemas/` or `treasury_intelligence/portfolio`.
3. Provide sample JSON payloads for:
   * A snapshot with active Tier 1, 2, and 3 positions.
   * A multi-asset recommendation (`INVEST_BONDS` and `REBALANCE`).
   * A 7-day four-tier strategy backtest report.
