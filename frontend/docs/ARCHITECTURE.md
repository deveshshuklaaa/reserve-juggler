# Frontend architecture

## Existing code and resulting structure

The starter had React 19/Vite 6, one monolithic dashboard, five Fetch helpers, inline/dark styling, hardcoded fallback financial values and fixed allocation percentages. The React bootstrap, port 3000 and Nginx SPA fallback are retained. The dashboard and transport have been replaced with separated screen, component and adapter modules.

```text
src/
  App.jsx                     Router and render error boundary
  context/SimulationContext   Shared run snapshots and serialized mutations
  api/client                  Environment-selected adapter
  api/http                    JSON, typed errors, timeout and AbortSignal handling
  api/treasuryApi             Proposed /api/v1 Fetch implementation
  api/mockTreasuryApi         Identical public interface, isolated in-memory runs
  api/validation              Shared response checks
  mocks/mockEngine            Deterministic development ledger and baseline
  mocks/backtest.worker       Off-main-thread comparison execution
  mocks/constants             Scenario enums, strategies and defaults
  components/Layout           Persistent navigation, status and playback
  components/ui               Reusable panels, metrics, buttons and state feedback
  components/Charts           Reusable Recharts histories and comparison bars
  components/Treasury         Decision, allocation, feed, positions and audit
  components/ModelEvaluation  Measured evaluation or explicit unavailable state
  pages/                      Three mandatory screens
  utils/format                Cents, basis points, UTC and CSV utilities
tests/                        Financial, adapter, engine and UI journey tests
```

## State and requests

The provider stores one confirmed bundle: snapshot, history, transactions, decisions, forecast. All pages share the current run. Form drafts, table filters, horizon/window controls and explanation visibility remain local.

Mutations use a synchronous ref lock so rapid repeated clicks cannot enqueue overlapping financial operations. Each advance sends `expected_step`. After successful mutation, data is fetched again. Playback schedules the next step only after the prior advance/refresh completes, with a 1.5-second pause. A 409 refreshes the current run and pauses rather than retrying the mutation.

An AbortController and run-generation token prevent stale response commits after unmount/replacement. Errors pause playback and retain the last confirmed snapshot with a visible warning. Request failures never replace financial data with invented values. A new run clears reports and pre-shock comparison state.

Before-shock state is captured when scenario submission starts and retained only after acceptance. After values remain absent until the effective step has executed. Draft settings cannot retroactively relabel the configuration of completed backtests.

## Financial display

- Safe integer USD cents throughout the data layer; divide by 100 only at formatting.
- Rates in basis points; risk percentile explicitly uses percent values 90/95/99.
- UTC ISO timestamps; labels always identify UTC.
- Zero is a valid value. Missing fields display an em dash.
- Latest snapshot balances already include executed decisions. The UI never subtracts the sweep again.
- Principal, accrual, realized interest, costs and borrowing liabilities are separated.
- Scenario-quantile explanation mode omits an extra uncertainty term.
- Settlement sign/color uses `direction`, not transaction category.
- CSV includes source, run/seed/step or comparison configuration and explicit `_cents` headers.

## Visual system

The revised design takes its hierarchy and restraint from Apple's product pages: system typography, large financial figures, a neutral #f5f5f7 canvas, white surfaces, ink text and #0071e3 actions. Compact top navigation replaces the original sidebar. The overview groups available cash and reserve/surplus values beside an SVG allocation ring derived from the current snapshot. Supporting earnings metrics use a quiet secondary strip; chart and transaction sections have their own clear hierarchy.

The SONOTYPE reference informed deliberate composition and restrained entrance motion. Treasury workflows, the React stack and all financial data conventions remain intact. Status uses text plus semantic colors. Mobile navigation manages focus, traps its tab order, closes on Escape and makes the workspace inert while open. Data tables scroll in their own containers. Motion respects reduced-motion preferences. System typography avoids external font dependencies.

## Backend integration

All real calls stay in `api/treasuryApi.js`; frontend expectations are documented separately from the unchanged old OpenAPI. Finalize the target shapes with Member 2, adjust the adapter/validators, then run the documented full journey with mocks disabled. React screens do not call Python or perform real financial calculations.
