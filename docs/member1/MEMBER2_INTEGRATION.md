# Member 2: four-tier contract boundary

Import `FourTierRecommendationRequest`, `PortfolioRecommendation`, and
`recommend_portfolio_allocation` from `treasury_intelligence`. They depend on
Pydantic, not ML, FastAPI, ORM, or a dataset loader. The recommendation function is
a contract-only stub in RJ-M1-06. No API/database files or old signatures changed.

- Validate CSV row strings with `OrganizerHourlyObservation.model_validate(row)`.
  It matches all 16 headers. Load with strings/Decimal, never float. Preserve the
  source CSV and hourly rows; retain source net_flow_usd independently.
- New timestamps have unspecified timezone. Do not use the old UTC contracts as
  an implicit adapter. Establish source availability semantics before a backtest;
  only rows available by the decision cutoff may be supplied.
- Snapshot Tier 0 cash, unsettled repo principal, index-marked bonds/equities,
  and overdraft debt separately. Market units are normalized dollar-per-index-point
  exposure. Marked cents are half-up; the schema verifies units times index.
- Repo entry is 17:00, maturity next-day 08:00. Do not add both repo principal
  and a maturity cash credit to liquid cash. Apply actual settlement once. Source
  flags are not position-level execution receipts. Validate early-break permissions.
- Response trades provide instrument/action, gross principal, market units,
  position references, execution/settlement timing, repo maturity, expected costs,
  and explanations. BUY/SELL amounts are before separately reported costs.
  Reconcile budget/targets, source policy, reserve, all cash legs, fees, credit limits,
  holdings, timing, and quote freshness before execution. Preserve trade tuple order;
  no atomicity is promised. The schema does not implement this execution gate.
- Borrowing is liability financing, never return. Keep realized financing,
  market losses, liquidation slippage, and transaction fees distinguishable.
  Observed bond index changes already mark the position; duration stress is
  hypothetical and must not be charged again to the same mark.
- `recommendation_only=true` / `execution_status=NOT_EXECUTED` are fixed. Store
  actual execution receipts in Member 2's own models; do not label a recommendation
  as executed. The example response is illustrative, not an optimizer output.

Serialize with `model_dump_json()` or `model_dump(mode="json")`; Decimal fields
become strings. Read the request/response fixtures and ENGINE_CONTRACT.md for the
complete field contract. Legacy single-vault APIs remain operational for compatibility.

RJ-M1-08 adds `instrument_economics` pure helpers (also package exports). Use supplied
Decimal rate fixings for repo/overdraft accrual, source index marks for bonds/equity,
and conditional sale P&L for execution planning. Results are calculation_only=true,
not accounting receipts. Repo defaults to forfeiting positive interest on early break
unless the product explicitly permits payment. ACT/365 fixed uses actual duration;
income rounds half up, fees/funding round upward. Read the RJ-M1-08 contract section
for repayment timing, cost-basis allocation, and no-double-counting conventions.
