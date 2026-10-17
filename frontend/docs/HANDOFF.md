# Frontend handoff — 17 October 2026

## Delivered

The light-themed Treasury Command Center, Liquidity Shock Lab and Treasury Strategy Arena work independently in mock mode. Playback, explicit scenario scheduling, immutable vault terms, before/after snapshots, policy application, decision explanations, comparative charts and CSV exports are implemented. The real Fetch adapter uses the assignment's proposed routes and has no silent mock fallback.

All repository changes are under `frontend/`. Branch: `frontend`. No backend, shared OpenAPI, forecasting, database, root CI or orchestration files were changed. The tested baseline is preserved through milestone F0; see F0_STATUS.md and Git history for publication status.

## File inventory

- Setup: `package.json`, `package-lock.json`, `vite.config.js`, `index.html`, `.env.example`, `Dockerfile`.
- Bootstrap/theme: `src/App.jsx`, `src/index.css`; original `main.jsx` retained.
- Transport: `src/api/client.js`, `http.js`, `treasuryApi.js`, `mockTreasuryApi.js`, `validation.js`.
- Shared state: `src/context/SimulationContext.jsx`.
- Development model: `src/mocks/constants.js`, `mockEngine.js`, `backtest.worker.js`.
- Shared views: `src/components/Layout.jsx`, `ui.jsx`, `Charts.jsx`, `Treasury.jsx`, `ModelEvaluation.jsx`.
- Screens: `src/pages/TreasuryDashboard.jsx`, `LiquidityShockLab.jsx`, `StrategyArena.jsx`.
- Financial display and export: `src/utils/format.js`.
- Tests: `tests/setup.js`, `finance.test.js`, `mockEngine.test.js`, `api.test.js`, `screens.test.jsx`.
- Documentation: `README.md`, `docs/MEMBER3_SPEC.md`, `ARCHITECTURE.md`, `API_CONTRACT_GAPS.md`, `MOCK_MODEL.md`, this handoff.
- Screenshots: `docs/screenshots/command-center.jpg`, `shock-lab.jpg`, `strategy-arena.jpg`, `command-center-mobile.jpg`.

The README gives install/run/build/test commands, mock/live environment settings, the presentation click sequence and remaining integration work. API_CONTRACT_GAPS maps every target operation to the current backend and identifies provisional payload details. MOCK_MODEL explains every demonstration assumption.

## Actual verification

- `npm.cmd test`: **42 passing tests in four files**, including mobile navigation focus and Escape handling.
- `npm.cmd run build`: **passed**, including a separate backtest-worker bundle.
- Dependency installation after upgrading Vitest to 4.1.11: **zero reported vulnerabilities**.
- `git diff --check`: **passed**; Windows line-ending notices only.
- Browser at **1366×768**: create, advance, recorded sweep, charts, transactions, positions and audit inspected; no page-width overflow.
- Browser Shock Lab: scenario accepted before balances changed, after values appeared only after the effective step; locked-liquidity warning observed.
- Browser Arena: 7-day comparison completed in the worker, all three strategies displayed, actual mock results selected Reactive as the net-benefit leader. The UI does not force Reserve Juggler to win.
- CSV export downloaded successfully; header includes source/run/scenario/seed/duration and integer-cent financial metrics.
- Browser at **390×844**: drawer navigation, KPI grid and playback controls inspected; no horizontal page overflow. Wide tables remain inside their own scroll containers.
- Browser console check: **no warning/error entries** during the inspected workflow.

Screenshots are retained for all three screens and the mobile Command Center. Browser viewport overrides were reset after testing.

## Integration status and limits

`/health` is the only target route also present in the old backend. The expanded `/api/v1` operations are implemented as client bindings and mocks, not claimed to be running in FastAPI. Exact bodies, collection envelopes, optional fields, supported capabilities and asynchronous report-job association still require agreement with Member 2.

No trained model, calibration, ML benchmark, Monte Carlo distribution or optimizer sensitivity data has been fabricated. The measured-model view accepts optional evaluation output but displays an honest unavailable state with the current mocks. Real backend end-to-end tests and Docker execution were not performed. In-memory runs intentionally reset on page reload.

Do not present mock backtest figures as project financial performance. The prototype ledger's assumptions, including whole-position early exits and simplified borrowing without repayment, are explicit in MOCK_MODEL.
