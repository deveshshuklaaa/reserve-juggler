# PENDING BACKEND MAPPINGS FOR MEMBER 2 (FASTAPI INTEGRATION)

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
