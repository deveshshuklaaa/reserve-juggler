# Member 1 integration status — 2026-10-18

Reviewed upstream commits:

- Member 1: `feat/treasury-intelligence`, `14a8d72`.
- Member 2: `feat/simulation-backend`, `52e58bc`.

The final Member 1 handoffs are `docs/member1/MEMBER3_FRONTEND_FIELDS.md` and
`docs/member1/MEMBER2_INTEGRATION.md` on the intelligence branch. These supersede
older `four_tier.py` examples for canonical portfolio consumers.

## Frontend delivered

- `src/models/canonical.js` validates canonical portfolios, optimizer results and
  hourly forecast point structures without Python imports or execution behavior.
  It checks safe integer money, valuation reconciliation, explicit time basis,
  nested provenance, and the recommendation/receipt boundary.
- `PortfolioInspector` displays multiple repo, bond, equity and overdraft records,
  quoted percentages, price indices, quantities, duration, supplied P&L, maturity,
  available/restricted liquidity, gross assets, liabilities and net portfolio value.
- Supplied optimizer results display targets, proposed orders in engine sequence,
  settlement/maturity terms, expected costs, rationale, policy feasibility, versions,
  estimated income/price changes, search truncation, and baseline versus selected
  plan funding gaps. All remain NOT_EXECUTED.
- Precision formatting uses decimal-string/BigInt rounding; rate units are explicit.
  A value of 4.292 in a `_pct` field means 4.292%, not 429.2 basis points.
- The actual Member 1 canonical portfolio fixture is tested verbatim under
  `tests/fixtures/member1-portfolio.json`; its origin is commit `14a8d72`,
  `tests/treasury_intelligence/fixtures/canonical_liquidity_portfolio.json`.
- The existing mock vault simulation remains available across all three screens.
  Its four-tier compatibility display uses the current snapshot, with zero bond/
  equity positions. It is explicitly not presented as the finalized optimizer or
  canonical overnight repo execution model.
- Shock Lab uses actual before/current snapshot differences. Arena diagnostics
  use completed comparison results. Hardcoded survival probabilities, risk ratios,
  regulatory compliance claims, and preselected winners have been removed.
- The first-visit experience has four responsive presentation scenes, scroll-linked
  transforms, animated light/flow visuals, chapter navigation and reduced-motion
  support. Its interactive preview conserves cash and labels the illustrative rule.

## Data boundary and remaining integration

The component staging interface is `snapshot.portfolio` (canonical PortfolioState)
and optional `snapshot.optimizer_result` (AllocationOptimizerResult). These are
frontend composition inputs, **not a claim that Member 2 publishes this envelope**.
Once Member 2 confirms the wire shape, map its real response into these inputs in
the centralized API layer. Do not change the backend to satisfy a guessed envelope.

No new LIVE endpoint has been invented. The four-tier real adapter operations still
explicitly return NOT_IMPLEMENTED until actual HTTP routes are confirmed. Existing
v1 requests preserve Member 2's error_code/message, accept its bare-array collection
responses, nullable reserves, and nullable or summary-only forecast objects. A
summary-only forecast does not create a fabricated chart series.

Member 2's `/api/v1/runs` route handlers all return HTTP 501 in the audited commit.
The v1 response models still describe the older cash/vault simulation. They do not
expose the final canonical portfolio, optimizer, native hourly history/forecast,
full Monte Carlo result, or execution receipts. The existing chart and backtest
views therefore remain compatibility/mock views until that mapping is confirmed.
The frozen request models also differ in opening cash/vault support, policy aliases,
percentile units, strategy IDs, and backtest parameters; see the audited table in
PENDING_BACKEND_MAPPINGS.md. Matching URL paths alone does not establish compatibility.

Member 1 itself reports an unresolved metadata target mismatch: hourly forecasts
target deposits-minus-withdrawals, while canonical metadata restricts the target
to source_net_flow_usd. Preserve both meanings; do not relabel or coerce either.
Hourly observation availability and timezone meaning must also be supplied upstream.

## Integration gate

F1A boundary/UI alignment can proceed independently. F1B/F6 LIVE handshake and
full-system certification remain blocked by working backend routes and payloads.
The next gate is a real create/advance/snapshot/forecast/decision/transaction sample,
including an execution receipt that can be reconciled with updated holdings.

Jointly verify Simulation → Forecast → Allocation → Execution → Updated Dashboard.
Do not report full frontend or end-to-end integration completion from mock tests.
