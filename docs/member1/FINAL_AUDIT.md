# Final quantitative engine audit — RJ-M1-14

Release baseline: ad5e42ad9ad7b552d2c1aa7694ba354cabf79e95 on
feat/treasury-intelligence. This audit preserves completed functionality and changes
only Member 1 engine, regression tests and documentation. No execution, database,
API, frontend or source CSV was modified.

## Material corrections

- Monte Carlo stress NAV now uses ending cumulative cash flow, not peak funding
  requirement. Hypothetical sales and settled repos remove their asset claims once;
  new borrowing increases cash and liability equally. Existing debt financing and
  new-draw financing reduce NAV once. Demo portfolio snapshots also include unpaid financing liabilities. Market losses use per-position cent rounding.
- Scenario weights sum exactly to one for non-power-of-ten sample counts; gaps in
  hourly bootstrap history are rejected. Market stress includes the first sampled
  hourly price change, including one-hour scenarios. Downside ranks use consistent
  discrete adverse quantiles. Monetary summary means use Decimal/half-up cents.
- Fitted ML artifacts cannot be replayed before their training/calibration cutoff.
  Fit and inference reject future, unordered or missing-hour history. Calibration
  observations are included in artifact availability and serialized cutoff metadata.
- Explicit forecast start times now determine seasonal lag timestamps. Forecasts
  beginning at as_of no longer use the next hour's seasonal observation.
- The demo no longer treats quoted bond YTM as horizon cash income. No automatic
  bond coupon or guaranteed equity return is added.
- Integration handoffs now use actual canonical field/import names and identify
  compatibility boundaries. Evaluation documentation no longer advertises absent
  deposit/withdrawal RMSE fields or non-overlapping multi-hour samples.

## Verification matrix

| Requirement | Evidence / result |
| --- | --- |
| Legacy 00–05 | Full suite retains contract, financial_math, forecasting, decisions and demo_pipeline tests; legacy standalone demo runs |
| Native hourly forecast | hourly_forecasting + ML tests; contiguous hourly inputs; target-time alignment regression |
| Chronological evaluation | Train/validation/test slices, frozen model, past-only rolling test history; actual full-dataset report |
| No future observations | Feature/inference tests, decision quote validation, model artifact availability guard; row publication semantics remain caller responsibility |
| Source marks | instrument_economics observed-index gain/loss tests; canonical supplied mark validation; no second duration adjustment |
| Repo entry/maturity | Contracts/economics/optimizer tests enforce historical 17:00?08:00; actual 15h ACT/365 fixed accrual |
| Repo fees/lock | Source percentage fee; permission gates, maturity settlement, no instantly liquid locked funds |
| Bonds | Index-based positive/negative P&L, 2% haircut, separate signed duration scenario; YTM not a coupon |
| Equities | Observed-price P&L, emergency 15% slippage, exposure/volatility constraints; no guaranteed income |
| Overdraft | Separate principal/unpaid financing liabilities; actual-duration pure helpers; conservative full-horizon risk cost |
| Cash constraints | Timed reserve, reserve-first optimizer, window/exposure/quantity/cash tests and no speculative warning orders |
| Uncertainty | Scenario quantile OR explicit calibrated allowance; not both; point provisional buffers excluded from scenario reserve |
| JSON | Typed contract tests, nested decision/order serialization, actual demo round trips in release script |
| Measured metrics | RELEASE_RESULTS.json and MODEL_EVALUATION_REPORT.md; no fabricated performance or strategy returns |
| Member 2 | Canonical recommendation contract validated; no canonical execution adapter found under backend; end-to-end execution remains unverified |
| Member 3 | Canonical fields documented in MEMBER3_FRONTEND_FIELDS.md; no frontend integration found/changed |
| CSV integrity | Before/after SHA256 match the previously recorded source fingerprint; 8,760 rows, 16 fields, native naive hours |

## Known limitations and integration blockers

1. Canonical new portfolio/risk/optimizer schemas live in portfolio.py. Older
   four_tier.py models remain for compatibility, and several root names still refer
   to them. Forecast point conversion is explicit. Canonical metadata accepts only
   source_net_flow_usd, while current forecasting/evaluation targets deposits minus
   withdrawals. Preserve the true target in separate metadata; do not silently
   relabel it. Original 16-field source observations remain untouched.
2. No Member 2 execution adapter or Member 3 wiring is certified by this release.
   This is a recommendation engine, not a ledger/backtester. Execution, realized
   costs/returns, realized payout failures and order atomicity are external work.
3. Source timestamp timezone and publication time are unspecified. Historical
   replay must establish row availability; code cannot infer when an hourly total
   became known. Demo supplied current observations are assumed available.
4. Forecast uncertainty remains provisional unless an external calibration is
   supplied. Bootstrap percentiles are finite empirical stress-model estimates,
   not calibrated coverage guarantees. Current volatility regimes, rare crises and
   structural changes may be absent from history; sampled blocks do not rescale
   historical innovations to current volatility. Market paths are adverse block
   shocks, not an unbiased terminal-price or expected-return distribution.
5. Monte Carlo portfolio NAV is an adverse endpoint after full permitted
   hypothetical liquidations, not selected optimizer execution. It includes net
   banking flows, so downside is not pure investment loss. Negative endpoint cash
   represents unfunded obligations. New borrowing uses an observed APR; financing
   assumes full-horizon outstanding principal and no automatic repayment/compounding.
   Ordinary repo future interest is not automatically synthesized into this NAV.
6. Optimizer is a bounded deterministic candidate search, not a global optimum.
   Reward assumptions and unit conventions must be supplied; limited candidates,
   lot precision and execution frictions can affect results. No transaction is run.
7. Model evaluation measures derived-net forecast error, not official independent
   net_flow_usd accuracy, reserve coverage, economic profit or realized risk. Peak
   error uses hour-end netting, whereas liquidity checks debit withdrawals before
   deposits. The 3-hour model loses to baseline; model dominance is not established.
   Rolling paths can overlap for general settings and do not give independent
   confidence intervals. Pickled model artifacts must be trusted; old calibrated
   artifacts should be refitted to record their complete availability cutoff.
8. Scikit-learn is optional/lazy and needed only for ML evaluation/inference. Source
   Decimal values are preserved; ML feature fitting and statistical errors use
   floating-point numerics, with measured errors rounded to cents for reporting.

## Standalone reproduction

From the repository root in PowerShell:

```powershell
$env:PYTHONPATH='.;backend'
$env:OMP_NUM_THREADS='1'
uv run --with pytest --with fastapi --with pydantic --with httpx --with sqlalchemy --with pydantic-settings --with scikit-learn pytest tests/ -q
uv run --with pydantic python -m treasury_intelligence.demo
uv run --with pydantic python -m treasury_intelligence.four_tier_demo
uv run --with pydantic --with scikit-learn python docs/member1/run_release_validation.py 'C:\Users\Arvind Shekhawat\Downloads\treasury_4tier_dataset.csv'
```

The release script evaluates all 8,760 rows chronologically, runs both demos,
checks typed JSON round trips, verifies the CSV hash before/after and writes
RELEASE_RESULTS.json. Four-tier CLI can use the checked-in 168-row real-observation
fixture when no CSV is found; this is distinct from full-source model evaluation.
No service, database, frontend or ML dependency is needed for the baseline demos.
See TESTING_REPORT.md for actual commands/results and model report for errors.
