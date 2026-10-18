# Reserve Juggler frontend

Apple-inspired light React treasury workspace for Member 3. All repository changes are confined to `frontend/`, on the existing `frontend` branch.

> Four-tier update: this commit preserves the working cash/vault demonstration as milestone F0. It is not yet the official four-tier model. Native hourly historical data, floating overnight repo terms, bonds, equities, and source-time semantics are planned for F1 onward after the quantitative and API contracts are received. See `docs/F0_STATUS.md` and `docs/MEMBER3_FOUR_TIER_HANDOFF.md`.

## Run locally

From this repository's `frontend` directory:

```powershell
npm.cmd ci
npm.cmd run dev
```

Open http://localhost:3000. On macOS/Linux use `npm` instead of `npm.cmd`.

```powershell
npm.cmd test
npm.cmd run build
npm.cmd run preview
```

Node 20.19+ or 22.12+ is recommended for the current test tooling. The development environment used Node 24.21.0. The existing frontend Dockerfile uses Node 20; no backend/container orchestration changes were made.

## Environment

Copy `.env.example` to `.env.local` and restart Vite after changing it.

```dotenv
VITE_USE_MOCKS=true
VITE_API_BASE_URL=http://localhost:8000
```

Mocks default to enabled. Setting `VITE_USE_MOCKS=false` selects the real Fetch adapter. The original `VITE_API_URL` is accepted as a compatibility alias for the base URL, not for old response schemas. Vite variables are public and baked into production builds; changing container environment variables after building will not rewrite static assets.

The current backend has the old `/api` contract. Live integration is pending. There is no automatic mock fallback in real mode. Review `docs/API_CONTRACT_GAPS.md` before connecting FastAPI.

## Screens

- `/`: Treasury Command Center, six KPIs, cash-flow/reserve/yield histories, future forecast, recorded decision and explanation, allocation, transactions, positions, audit log, snapshot CSV.
- `/shock-lab`: five scenarios, validated parameters, scheduled event confirmation, pre/post snapshots, reserve policy, liquidity response chart and event log.
- `/strategy-arena`: seeded 7/14/30-day mock backtests, three selectable policies, metric table, benefit/cost/risk/idle-cash charts, recorded liquidity histories, ranking criteria and CSV. Model evaluation remains unavailable until measured results are provided.

## Repeatable demonstration

1. Click **Create simulation**. Initial checking is $20M and locked vault principal $6M, seed 2026.
2. Click **Step**. A recorded sweep creates another vault position. Expand **Why this decision?** and inspect pre/post balances.
3. Play several steps, then pause. Change cash-flow windows and inspect the separate forecast region.
4. Open **Liquidity Shock Lab**. Choose **Withdrawal spike**, keep 3× and eight steps, then click **Trigger scenario**.
5. Observe that balances have not changed simply because the scenario was submitted. Advance a step to populate the after column. Continue to observe reserve pressure.
6. Inspect locked vault positions. They are unavailable for redemption unless their ORIGINAL position terms allow an early exit. An updated policy affects new positions only.
7. Apply a different risk percentile/buffer. The active snapshot refreshes; the decision card still describes its own recorded calculation until the next decision.
8. Open **Strategy Arena**. Choose a scenario, seed and duration. Run the comparison; all policies receive the same external transaction demand.
9. Change the ranking criterion and export the source-labeled CSV. No strategy is automatically declared the winner.
10. Reset to create a fresh reproducible run. A page reload intentionally discards the in-memory mock session.

## Architecture and ownership

See `docs/ARCHITECTURE.md`, `docs/API_CONTRACT_GAPS.md`, and `docs/MOCK_MODEL.md`. The supplied assignment is preserved in `docs/MEMBER3_SPEC.md`. Its dark-theme and branch suggestions are superseded by the user's light-theme and `frontend` branch instructions.

React owns view preferences, form drafts and playback. The selected API owns all financial balances and outcomes. The mock engine is a separate development adapter and never runs as a live-mode financial fallback.

## Verification and limitations

Vitest/Testing Library cover financial units, zero/null handling, deterministic simulation, capital conservation, scenario scheduling, locked-vault behavior, maturation, policy immutability, errors, API parity, one-in-flight advancement, pause, stale conflicts, decision rendering, transaction signs, and the complete three-screen journey.

Real FastAPI integration, calibrated forecasting, ML evaluation, Monte Carlo distributions and sensitivity analyses are pending the other members' outputs. The frontend does not invent those results. Exact target request/response details beyond the assignment are provisional and isolated in the adapters.

Mock data and runs are in memory. Backtests use a browser worker to keep the UI responsive. In test environments without Worker support, the same pure engine runs directly. No authentication, real customer data or real transfers are implemented.
