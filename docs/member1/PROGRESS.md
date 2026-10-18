# Member 1 Progress Tracker — Reserve Juggler

**Workstream**: Quantitative Treasury Intelligence Engine  
**Feature Branch**: `feat/treasury-intelligence`  
**Remote Target**: `origin/feat/treasury-intelligence`  

---

## Task Log

### [RJ-M1-12] Multi-Asset Monte Carlo Risk
- **Status**: COMPLETED
- **Scope**: Implemented pure, reproducible multi-asset Monte Carlo risk simulation
  (`monte_carlo_risk.py`) modeling the joint uncertainty of cash flows, bond prices,
  and equity returns using historical block bootstrap sampling. Fully integrated
  with canonical `FourTierLiquidityRiskRequest` and `calculate_four_tier_liquidity_risk`.
- **Causality & Data Integrity**:
  - Strictly causal: only historical observations $t \le \text{portfolio.as\_of}$ are
    eligible for sampling; no future lookahead.
  - Cash-flow forecast residuals: historical 24h seasonal forecast errors for deposits
    and withdrawals are sampled contiguously, preserving intraday correlation.
  - Market innovations: block sampling captures simultaneous bond price index and
    equity index drawdowns without imposing unrealistic Gaussian copula assumptions.
  - Non-negativity: simulated deposits, withdrawals, and prices are strictly $\ge 0$.
  - Observed market volatility: uses observed `tier3_stock_volatility_pct` rather than
    fabricating artificial volatility dynamics.
- **Pathwise Evaluation & Revaluation**:
  - Respects scenario-specific repo maturities: 15-hour overnight repo entered at 17:00
    matures at 08:00; cash is not available earlier unless broken early.
  - Revalues all 4 tiers along each simulated path: cash net balance, repo claims,
    marked bond positions, marked equity positions, and overdraft liabilities.
  - Computes maximum cash funding shortfall before and after permitted liquidations.
  - Models forced liquidation costs (repo break fees, bond 2% haircuts, equity 15%
    slippage) and overdraft financing costs for remaining funding gaps.
- **Percentiles & Outputs**:
  - Generates 500 reproducible scenario paths (default seed=42) where probabilities
    sum exactly to `Decimal("1")` (`Decimal("0.002")` each).
  - Evaluates P90, P95, and P99 percentiles for peak funding requirements, funding
    shortfalls, market stress losses, portfolio value, and downside loss.
  - Produces typed `MultiAssetMonteCarloRiskResult`, `MarketRiskSummary`,
    `ShortfallDistributionSummary`, `PortfolioDownsideRiskSummary`, and `PercentileSummary`.
  - Discloses model version (`multi-asset-block-mc-v1`) and clear notes avoiding
    claims of guaranteed real-world confidence intervals.
  - Generates canonical `LiquidityScenario` objects directly consumable by
    `FourTierLiquidityRiskRequest` and `FourTierOptimizerRequest`.
- **Tests**: Full suite 407 passed (396 previous tests preserved; 11 new Monte Carlo tests).
  Tests cover reproducibility, non-negativity, stress quantile ordering ($P_{90} \le P_{95} \le P_{99}$),
  no lookahead, no uncertainty double-counting, correct repo cash availability, higher market losses
  reducing portfolio value, default 500 scenario execution, and consistent JSON round-trip serialization.
  Command: `$env:PYTHONPATH=".;backend"; uv run --with pytest --with fastapi --with pydantic --with httpx --with sqlalchemy --with pydantic-settings pytest -q`
- **Files**:
  - `treasury_intelligence/monte_carlo_risk.py` (new module)
  - `treasury_intelligence/liquidity_risk.py` (capped Decimal precision to keep 500 scenarios fast)
  - `treasury_intelligence/api.py` and `treasury_intelligence/__init__.py` (re-exports)
  - `tests/treasury_intelligence/test_monte_carlo_risk.py` (11 new tests)
  - `docs/member1/PROGRESS.md` and `docs/member1/ENGINE_CONTRACT.md` (documentation)
- **Commit**: `feat(risk): add multi-asset Monte Carlo scenarios`
- **Push Target**: `origin/feat/treasury-intelligence`
- **Next Task**: Await explicit assignment; stop after RJ-M1-12.

### [RJ-M1-11] Four-Tier Treasury Optimizer
- **Status**: COMPLETED
- **Scope**: Implemented deterministic rule-assisted constrained candidate search
  over HOLD, new investments, permitted sales/rebalancing, debt repayment and
  emergency borrowing. Returns all four targets, canonical RecommendedOrders and
  FourTierDecisionResult, summary action, expected economics, risk/constraints,
  full assumptions, diagnostics, and model/policy versions. No trade execution.
- **Inputs**: Canonical RJ-M1-10 liquidity request (portfolio, forecasts, source
  quotes, permissions, known settlements, obligations, credit/risk policy), explicit
  reward/quantity assumptions, optional stronger supplied reserve, and bounded
  candidate-grid settings. Future assumptions are rejected. New market purchases
  require explicit exposure caps and supplied quantity/index conversion.
- **Objective**: Expected income + expected price change - conditional exit cost
  - modeled carrying/borrowing cost - immediate trading wealth loss - configurable
  stress-risk penalty. Rewards are disclosed expected assumptions, not realized
  prices, guaranteed equity yield, fabricated calibration, or automatic YTM coupons.
- **Constraints**: Reserve cannot fund new investments; only immediate cash above
  reserve pays purchases/fees. Repo needs an open 17:00 window and 08:00 maturity
  coverage. Locked funds require explicit redemption permission/source costs.
  Post-fee exposures, risk/debt limits, nominal cash-path funding and supplied
  scenario confidence budget are checked. Early repo sale removes the same future
  maturity credit. Newly borrowed capital cannot be invested.
- **Search**: HOLD/sale/minimal liquidity and concentration repair/financing seeds,
  allocation grid and cap/minimum endpoints. Exact-cent fee/quantity calculations,
  deterministic UUID5 order IDs, fewer-order/cash/lower-risk tie breaks, candidate
  failures and truncation disclosed. No claim of exhaustive global optimality.
- **Compatibility**: New `recommend_four_tier_allocation` returns the rich typed
  result; canonical/root/API `recommend_portfolio_allocation` dispatches new requests
  to the canonical decision. Older envelopes without assumptions retain explicit
  refusal. Generic-vault algorithms remain unchanged. Legacy single-repo hints are
  available without flattening multi-asset plans or inventing timezone adapters.
- **Tests**: Full suite 396 passed (361 previous tests preserved; 35 new optimizer
  tests), covering reserve protection, repo windows/lock/costs/maturity, all-tier
  allocation, explicit/post-fee caps, market losses, risk-adjusted high-yield rejection,
  units, negative quotes, liquidation, repayment/borrowing, delayed settlement,
  no duplicate maturity, deterministic serialization, versions and NOT_EXECUTED.
- **Command**: `$env:PYTHONPATH=".;backend"; uv run --with pytest --with fastapi --with pydantic --with httpx --with sqlalchemy --with pydantic-settings --with scikit-learn pytest tests/ -q`
- **Files**: New `optimizer.py` and `test_optimizer.py`, additive exports/canonical
  dispatcher, Member 1 contract/integration/progress documentation only.
- **Dataset**: Organizer CSV unchanged; no loader, persistence, Member 2 API/backend,
  frontend, replay, ML implementation or realized-accounting changes.
- **Commit**: `feat(optimizer): recommend constrained four-tier allocations`
  (hash and push confirmation in completion report).
- **Push Target**: `origin/feat/treasury-intelligence`.
- **Next Task**: Await explicit assignment; stop after RJ-M1-11.

### [RJ-M1-10] Four-Tier Liquidity Reserve and Risk
- **Status**: COMPLETED
- **Scope**: Pure canonical hourly pathwise peak funding requirement, explicit
  contractual repo settlements, committed obligations, required Tier 0 reserve,
  calibrated-allowance OR weighted scenario-quantile uncertainty, operational/minimum
  buffers, available/restricted liquidity, permitted stress liquidation, scenario
  funding/expected-shortfall metrics, policy checks, and borrowing consequences.
- **Canonical Boundary**: Selectively copied only reviewed `portfolio.py` from
  `1fcff80f05136a1d90faf8b88adacc8d313dc072`; identical blob
  `ed86bc45fae6421aa518c0cc10df3aa0e7dd142f`. No review branch merge or replacement
  of RJ-M1-07/08/09 functionality. New risk inputs use canonical PortfolioState,
  FourTierTreasuryPolicy and HourlyForecastPoint; reserve is FourTierReserveResult.
  Prior legacy/root schema migration remains explicitly unresolved, not aliased.
- **Timing/No Double Counting**: Outflows at bucket start, deposits at bucket end,
  actual attested maturity/settlement arrival times, forecast-included obligation
  flags, booked-repo exclusion, and removal of maturity receipts after modeled
  early break. Full first-hour forecast coverage is required. Source net-flow
  forecasts stay independent; this path uses separate inflow/outflow timing.
- **Risk/Economics**: Source-supplied current marks and haircuts; separate hypothetical
  bond price OR duration stress; equity drawdown/volatility sensitivities; explicit
  liquidation policy/position permission and delay; min cash/exposure/loss limits.
  New credit is costly borrowing, never existing cash or a reserve reduction.
- **Honest Metrics**: Calibration reference is caller supplied; scenario probabilities
  are supplied model weights. Expected funding deficit, tail ES, reserve breach,
  projected funding failure, and actual payout failure are separate. The last is
  always null; probability/ES fields are null without supplied scenarios.
  No ML/calibration fabrication, Monte Carlo, optimizer, trades or ledger changes.
- **Precision**: Strict cents and finite Decimal percentages/probabilities;
  conservative downward stressed marks/upward costs and shortfall rounding.
- **Tests**: Full suite 361 passed (all prior 328 preserved; 33 new risk tests),
  including $8M timing, 08:00 maturity/delay, locked cash, 2%/15% haircuts, 0.5%
  break, no duplicate maturity, monotonic outflows, drawdown, liabilities, zero/tiny
  balances, weighted quantile/tail mass, calibrated allowance, explicit UTC and
  unspecified clocks, canonical validation, JSON, and immutability.
- **Command**: `$env:PYTHONPATH=".;backend"; uv run --with pytest --with fastapi --with pydantic --with httpx --with sqlalchemy --with pydantic-settings --with scikit-learn pytest tests/ -q`
- **Dataset**: Original organizer CSV unchanged; SHA-256 remains
  `2e7c1d2e5b678e9975250211e7e0017022049c510e1dd90cd7f29e931837b0c5`.
- **Files**: `portfolio.py`, new `liquidity_risk.py`, additive exports, new risk
  tests/canonical fixture, Member 1 contract/integration/progress documentation.
- **Commit**: `feat(risk): calculate four-tier liquidity requirements`
  (exact tested hash and push confirmation in completion report).
- **Push Target**: `origin/feat/treasury-intelligence`.
- **Next Task**: Await explicit assignment; stop after RJ-M1-10.

### [Pre-RJ-M1-10] Canonical Contract Compatibility Check
- **Status**: Check complete; canonical integration NOT aligned and unresolved.
- **Verified Branches**: Local and remote feature baseline `c3cebcd2ac2f4502e0916405c203240e15dc89ed`;
  canonical review `1fcff80f05136a1d90faf8b88adacc8d313dc072`, shared base `974154e`.
  Review changes are not present locally/on the remote feature branch. No merge.
- **Findings**: Obsolete four_tier imports and payloads; missing canonical UUID/
  source/time-basis/availability data; incompatible repo/state/liability fields;
  source-net versus derived-net target/evaluation mismatch; normalized index-unit
  valuation conflicts with canonical supplied valuation semantics.
- **Probes**: Current repo/portfolio economics raise AttributeError on reviewed
  canonical positions/state; old forecast JSON lacks required time_basis. Source
  net differs from deposits-minus-withdrawals in 35 of 168 real fixture rows.
- **Safe Changes**: Compatibility report and documentation status only. No
  algorithms, schemas, fixtures, datasets, or teammate files changed. Behavioral
  migration was not disguised as an import fix. Completed RJ-M1-00..09 retained.
- **Tests**: Full feature baseline 328 passed with scikit-learn installed;
  reviewed canonical snapshot validated through an isolated in-memory Git-blob probe.
  These passes do not establish canonical interoperability.
- **Report**: `docs/member1/CANONICAL_ALIGNMENT_CHECK.md` records exact revisions,
  interface differences, checks, and remaining migration requirements.
- **Commit/Push**: Documentation-only check commit on feat/treasury-intelligence;
  exact tested commit and push result are in the completion report.
- **Stop**: No RJ-M1-10 implementation. Resolve canonical migration before using
  the later algorithms as canonical portfolio consumers.

### [RJ-M1-09] Hourly ML Forecasting and Evaluation
- **Status**: COMPLETED
- **Scope**: Implemented and evaluated real machine-learning forecasting for hourly cash flows
  against the organizer's historical hourly banking dataset. Extended the native hourly
  forecasting engine with `HourlyCashFlowMLModel` supporting `hist_gradient_boosting` and
  `random_forest`, out-of-sample chronological evaluation (`evaluate_hourly_forecast_models`),
  and structured evaluation reporting (`HourlyModelEvaluationReport`).
- **Models & Algorithms**:
  - `HourlyCashFlowMLModel`: Implements dual lightweight estimators for separate deposit
    and withdrawal forecasting with non-negativity clipping (`deposits >= 0`, `withdrawals >= 0`).
  - Supported algorithms: `"hist_gradient_boosting"` (fast histogram GBDT) and `"random_forest"`.
  - Scikit-learn regressors and metrics are lazily loaded on demand inside model methods,
    preserving zero eager ML dependencies for base contracts and standalone pipelines.
  - Full model serialization (`save`, `load`, `to_bytes`, `from_bytes`) to avoid retraining
    during simulation replay.
- **Causal Feature Engineering**:
  - `extract_ml_features_for_step`: Constructs strictly causal feature vectors:
    - Target step calendar features: hour of day (0-23) and day of week (0-6) with sin/cos
      cyclical encodings, plus weekend indicator.
    - Historical baseline references: target-relative 24h and 168h seasonal naive flows.
    - As-of historical lags: 1h, 2h, 3h, and 24h prior deposits, withdrawals, and net flow.
    - As-of rolling window statistics: 3h and 24h rolling averages and standard deviations.
    - As-of market quotes: repo rate, bond yield, and stock price index observed at `as_of`.
    - No future cash flows, future realized observations, or future market quotes are exposed.
- **Multi-Step Horizons & Pathwise Inference**:
  - Native multi-step horizons: 1h, 3h, 6h, 15h (overnight repo 17:00-08:00), and 24h (daily cycle).
  - Multi-step paths are generated recursively roll-forwarding predicted flows for intermediate
    lags without future realized lookahead.
  - Full path output returns ordered `HourlyForecastPoint` items directly compatible with
    `HourlyForecastResult` and four-tier decision engine inputs.
- **Safe Fallback**:
  - Explicit baseline fallback: untrained, unavailable, or history < 24h automatically falls back
    to `hourly_seasonal_naive_forecast` or `hourly_rolling_mean_forecast`.
- **Chronological Evaluation Framework**:
  - `evaluate_hourly_forecast_models`: Performs strict out-of-sample chronological evaluation
    without shuffling or data leakage.
  - Evaluation partition: Chronological train (e.g. 60%), validation (e.g. 20%), and test (e.g. 20%)
    splits with explicit `train_cutoff`, `test_start`, and `test_end`.
  - Metrics computed:
    - MAE and RMSE for deposits, withdrawals, and net cash flow ($).
    - Cumulative multi-hour forecast net error MAE ($).
    - Maximum cumulative liquidity shortfall prediction error MAE ($).
    - Baseline comparative metrics and un-doctored improvement percentages (`net_mae_improvement_pct`,
      `net_rmse_improvement_pct`).
  - Measured performance on organizer dataset (8,760 hours): HistGradientBoosting outperforms
    seasonal-naive baseline across all horizons (e.g., 1h net MAE +46.9%, 15h peak shortfall MAE +65.9%).
- **Tests**: Full suite 328 passed (314 previous tests preserved; 14 new ML forecasting tests).
  Tests cover causal feature timing, evaluation boundaries, all 5 horizons, non-negativity,
  seed reproducibility, model fallback, metric math, market-data visibility, and model comparison.
  Command: `$env:PYTHONPATH=".;backend"; uv run --with pytest --with fastapi --with pydantic --with httpx --with sqlalchemy --with pydantic-settings pytest tests/`
- **Files**:
  - `treasury_intelligence/ml_forecasting.py` (new)
  - `treasury_intelligence/hourly_forecasting.py` (extended with `ml_model` config dispatch)
  - `treasury_intelligence/api.py` and `treasury_intelligence/__init__.py` (exports)
  - `tests/treasury_intelligence/test_ml_forecasting.py` (14 new tests)
  - `docs/member1/PROGRESS.md` and `docs/member1/ENGINE_CONTRACT.md` (documentation)
- **Commit**: `feat(forecast): add evaluated hourly ML predictions`
- **Push Target**: `origin/feat/treasury-intelligence`
- **Next Task**: Await explicit assignment; stop after RJ-M1-09.

### [RJ-M1-08] Four-Tier Financial Mathematics
- **Status**: COMPLETED
- **Scope**: Added pure `instrument_economics.py` helpers and typed JSON results
  for ACT/365 fixed floating-rate repo accrual, actual 17:00-to-08:00 maturity,
  early-break fee/proceeds/lock-aware availability, index acquisition quantity,
  bond/equity observed-index valuation, signed price P&L and conditional sale P&L,
  liquidation costs, separate duration sensitivity, equity exposure/drawdown,
  actual-duration overdraft costs/principal changes, and portfolio value summaries.
- **Precision**: Decimal source rates/prices/percentages preserved, local precision,
  actual microsecond durations, half-up money values/income, upward-rounded costs,
  down-rounded explicitly specified acquisition unit precision. No per-hour interest
  rounding or obsolete 24-hour repo assumption.
- **Financial Boundaries**: Tier 0 alone is available checking cash; modeled repo
  claims, marked assets, potential liquidation proceeds, and overdraft liabilities
  are separate. No coupons inferred from YTM, duration double charge, guaranteed
  equity return, duplicate settled repo asset, or repeated deduction of recorded
  costs. Results are calculation_only=true; execution/realized booking stays with
  Member 2. Early-break positive-interest entitlement is an explicit input, with
  documented default forfeiture; source data does not specify that entitlement.
- **Compatibility**: Existing interfaces, hourly forecasting, legacy algorithms,
  and all earlier tests preserved. No changes to loaders, datasets, API/database,
  frontend, or optimizer implementations. Organizer CSV SHA-256 remains
  `2e7c1d2e5b678e9975250211e7e0017022049c510e1dd90cd7f29e931837b0c5`.
- **Tests**: Full suite 314 passed (265 previous tests preserved; 49 new economics
  tests). Required repo 15-hour interest ($5M at 5% gives $428.08), 0.5% break fee,
  bond/equity gains and losses, 2%/15% liquidation, duration sign/units, overdraft
  cost, conservation, cent rounding, causal quotes, JSON, and precision all pass.
- **Command**: `$env:PYTHONPATH=".;backend"; uv run --with pytest --with fastapi --with pydantic --with httpx --with sqlalchemy --with pydantic-settings pytest tests/ -q`
- **Diff Check**: `git diff --check` passed.
- **Files**: New instrument economics module/tests, package exports,
  ENGINE_CONTRACT.md, MEMBER2_INTEGRATION.md, and this log only.
- **Commit**: `feat(engine): add four-tier instrument economics`
  (hash in Git history and completion report).
- **Push Target**: `origin/feat/treasury-intelligence`; result in completion report.
- **Next Task**: Await explicit assignment; stop after RJ-M1-08.

### [RJ-M1-07] Official Hourly Forecast Foundation
- **Status**: COMPLETED
- **Scope**: Adapted the quantitative forecasting foundation to natively support the
  organizer's hourly dataset without losing compatibility with the separate synthetic
  15-minute demo. Implemented explicit temporal resolution, organizer hourly cash-flow
  buckets, causal hourly time features, rolling-mean and seasonal-naive baselines,
  separate deposit and withdrawal forecasts, multi-step horizons (1h, 3h, 6h, 15h, 24h),
  complete pathwise outputs, and safe short-history fallback.
- **Resolution & Configuration**: Introduced `ForecastResolution` enum (`"1h"`, `"15m"`)
  and `HourlyForecastConfig` for explicit granularity, horizon, window, and uncertainty
  multiplier specification.
- **Organizer Data Support**: Implemented `HourlyCashFlowBucket` model and local
  read-only `load_organizer_dataset` CSV adapter. Retains native Decimal USD values and
  integer cents without altering source scale or inferring timezones.
- **Causal Feature Engineering**: Built strictly causal hourly feature extractors:
  - `extract_hourly_calendar_features`: hour of day (0-23), day of week (0-6), weekend
    flag (0/1), cyclical sin/cos encodings. Naive hourly datetimes only.
  - `compute_hourly_lag_features`: Lags 1h, 2h, 3h, 24h (same hour on previous day),
    and 168h (same hour in previous week).
  - `compute_hourly_rolling_features`: Rolling averages and sample standard deviations
    (volatility) over 3h, 6h, 24h, and 168h windows. `strictly_prior=True` prevents
    lookahead leakage.
  - `build_hourly_feature_matrix`: Combines calendar, lag, and rolling statistics.
- **Hourly Baselines**:
  - `hourly_rolling_mean_forecast`: Rolling-mean prediction of separate deposits and
    withdrawals over requested horizon with empirical net-flow standard deviation uncertainty.
  - `hourly_seasonal_naive_forecast`: 24-hour daily seasonal baseline matching exact
    hour of day from previous cycle, with empirical residual uncertainty.
  - `forecast_hourly_cashflows`: Unified entry point supporting arbitrary models and
    configurations.
- **Horizons & Invariants**: Validated for 1-hour, 3-hour, 6-hour, 15-hour (overnight
  repo 17:00-08:00), and 24-hour (daily cycle) horizons. Full path output returns
  ordered `HourlyForecastPoint` items with non-negative predicted deposits and withdrawals.
- **Safe Fallback**: Empty history falls back to 0-flow path; history below seasonal
  cycle (< 24h) safely falls back to rolling mean over available observations.
- **Integration**: `HourlyForecastResult.points` directly satisfies
  `FourTierRecommendationRequest.forecast`.
- **Preservation**: Original 15-minute synthetic forecasting (`forecast_cashflows`,
  `CashFlowBucket`, `ForecastResult`), pipeline, and demo remain 100% operational.
- **Tests**: Full suite 265 passed (237 previous tests preserved; 28 new tests).
  Command: `$env:PYTHONPATH=".;backend"; uv run --with pytest --with fastapi --with pydantic --with httpx --with sqlalchemy --with pydantic-settings pytest tests/ -q`
- **Commit**: `feat(forecast): support native hourly treasury forecasting`
- **Push Target**: `origin/feat/treasury-intelligence`
- **Next Task**: Await explicit assignment; stop after RJ-M1-07.

### [RJ-M1-06] Four-Tier Contract Migration
- **Status**: COMPLETED
- **Scope**: Added immutable four-tier contracts for exact organizer observations,
  instrument identities, Decimal market quotes, operational cash, 15-hour repo
  positions, index-marked two-year bonds/equities, overdraft debt, realized/estimated
  costs, portfolio state, exposure/risk policy, hourly forecast provenance, targets,
  proposed trades, instrument return estimates, and explained recommendations.
- **Compatibility**: Original model fields, forecast/reserve/decision signatures,
  tests, demo, and standalone pipeline preserved. New public
  `recommend_portfolio_allocation(request)` is a contract-only NotImplementedError
  boundary; no optimizer, trade execution, loader, persistence, or API changes.
- **Data Fidelity**: Read-only inspection of the supplied Downloads CSV confirmed
  8,760 contiguous hourly observations and all 16 actual headers. All 8,760 rows
  validate against the new observation model. Source net flow remains independent.
  Market/source values retain Decimal precision with decimal-string JSON; new
  timestamps remain timezone-unspecified, separate from legacy UTC contracts.
  Original CSV SHA-256 before/after unchanged:
  `2e7c1d2e5b678e9975250211e7e0017022049c510e1dd90cd7f29e931837b0c5`.
- **Deliverables**: `treasury_intelligence/four_tier.py`, additive package/API
  exports, three JSON fixtures, `test_four_tier_contracts.py`, ENGINE_CONTRACT.md,
  MEMBER2_INTEGRATION.md, MEMBER3_FRONTEND_FIELDS.md, and this log.
- **Fixtures**: Real source rows plus explicitly illustrative request/response
  portfolio and estimates; no fabricated evaluation metrics or optimizer claims.
- **Validation**: Hourly granularity, offset rejection, float/nonfinite rejection,
  native Decimal scale, 17:00-to-08:00 repo maturity, observed-index mark checks,
  separate borrowing, exposure/target/reserve invariants, nonexecuted order shapes,
  causal history/provenance, legacy signatures, and imports without ML/DB/FastAPI.
- **Tests**: Full suite 237 passed (181 previous tests preserved; 56 new tests).
  Command: `$env:PYTHONPATH=".;backend"; uv run --with pytest --with fastapi --with pydantic --with httpx --with sqlalchemy --with pydantic-settings pytest tests/ -q`
- **Commit**: `feat(engine): extend contracts for four-tier treasury`
  (hash in Git history and completion report).
- **Push Target**: `origin/feat/treasury-intelligence`; result in completion report.
- **Next Task**: Await explicit assignment; stop after RJ-M1-06.

### [RJ-M1-05] Standalone Treasury Decision Pipeline and Demo
- **Status**: COMPLETED
- **Scope**: Connected all Member 1 quantitative modules into an end-to-end pure Python
  pipeline (`Historical cash flows -> Baseline forecast -> Supplied provisional uncertainty policy -> Required reserve -> Treasury recommendation -> Expected economic result -> Structured explanation`).
- **Pipeline Implementation**: Implemented `treasury_intelligence/pipeline.py` with
  immutable `TreasuryPipelineResult` and `run_treasury_pipeline`.
- **Executable Demo**: Implemented `treasury_intelligence/demo.py` with deterministic
  local fixtures demonstrating all five required operational scenarios and JSON serialization:
  1. Normal operation: balanced checking liquidity operating within policy buffer (`HOLD`).
  2. Valid safe sweep: surplus cash swept to liquid yield vault with positive modeled net benefit (`SWEEP`).
  3. High-withdrawal stress: large forecasted outflow deficit replenished from liquid vault (`WITHDRAW`).
  4. Locked vault with insufficient liquidity: deficit cannot be covered by locked vault (`LIQUIDITY_WARNING`).
  5. Successful HOLD: checking balance within equilibrium tolerance corridor (`HOLD`).
  6. JSON serialization: full engine pipeline result serialized and deserialized with 100% round-trip fidelity.
- **Uncertainty Governance**: Policy-supplied uncertainty is explicitly marked as `provisional_uncalibrated`
  with explicit explanatory notes, without fabricating completed model evaluation.
- **Dependencies**: Pure Python only. No FastAPI or PostgreSQL dependencies added.
- **Demo Command**:
  ```powershell
  $env:PYTHONPATH="."; uv run python -m treasury_intelligence.demo
  ```
- **Tests**: 181 passed (8 new pipeline integration tests; 173 previous tests preserved).
  Command: `$env:PYTHONPATH=".;backend"; uv run --with pytest --with fastapi --with pydantic --with httpx --with sqlalchemy --with pydantic-settings pytest tests/ -q`
- **Files**: `treasury_intelligence/pipeline.py`, `treasury_intelligence/demo.py`,
  `treasury_intelligence/__init__.py`, `tests/treasury_intelligence/test_demo_pipeline.py`,
  `docs/member1/ENGINE_CONTRACT.md`, and this progress log.
- **Commit**: `feat(engine): complete standalone treasury decision pipeline`
- **Push Target**: `origin/feat/treasury-intelligence`
- **Next Task**: Await explicit assignment; stop after RJ-M1-05.

### [RJ-M1-04] Treasury Decisions and Explanations
- **Status**: COMPLETED
- **Scope**: Implemented pure HOLD, SWEEP, WITHDRAW, and LIQUIDITY_WARNING
  recommendations using existing reserve and economics helpers. Added explicit
  TreasuryDecisionPolicy and VaultTerms controls without changing frozen fields
  or the public function signature.
- **Liquidity**: Deficits take precedence; only permitted zero-delay withdrawals
  qualify, capped at withdrawable principal. Penalties and fees are deducted when
  grossing up redemptions. Locked nonredeemable funds never support a withdrawal.
  A deficit needing multiple vaults returns a warning because the result contract
  permits a single vault only; this limit is documented in ENGINE_CONTRACT.md.
- **Sweeps**: Require explicit open window and eligibility, reserve coverage after
  upfront fees, minimum threshold after caps, allocation/absolute caps, permissible
  modeled exit timing, and positive expected benefit after costs. Missing terms
  block investment and redemption. Stable vault-ID tie breaks.
- **Explanations**: Integer-cent reserve components, candidate/cap amounts, expected
  interest, penalties, fees, net benefit/proceeds, and resulting checking balances.
  Recommendation only; no ledger/database execution or realized-return claims.
- **Tests**: Full suite 173 passed. Added 37 decision tests; replaced only the
  former recommendation-stub assertion with implemented-behavior coverage.
  Existing forecasting, financial mathematics, and backend tests pass.
- **Command**: `$env:PYTHONPATH=".;backend"; uv run --with pytest --with fastapi --with pydantic --with httpx --with sqlalchemy --with pydantic-settings pytest tests/ -q`
- **Diff Check**: `git diff --check` passed.
- **Files**: `treasury_intelligence/policy.py`, package exports/API, Member 1 tests,
  ENGINE_CONTRACT.md, and this progress log only.
- **Commit**: `feat(engine): implement treasury decisions and explanations`
  (hash in Git history and completion report).
- **Push Target**: `origin/feat/treasury-intelligence`; result in completion report.
- **Next Task**: Await explicit assignment; stop after RJ-M1-04.

### [RJ-M1-03] Feature Engineering and Baseline Forecasts
- **Status**: COMPLETED
- **Scope**: Implemented causal feature engineering (calendar time-of-day/day-of-week,
  historical lags, rolling means and stds for inflows, outflows, and net flows) and
  baseline forecasting models (rolling-mean and seasonal-naive).
- **Causality & Timing**: Strictly causal; no future observations accessed. Time features
  computed from interval start timestamp; lags strictly prior; rolling windows causal.
- **Models**:
  - `rolling_mean_forecast`: rolling mean of historical inflows and outflows over window,
    with empirical net-flow sample standard deviation for uncertainty.
  - `seasonal_naive_forecast`: 24-hour daily seasonal pattern (96 15-min intervals) with
    seasonal error variance for uncertainty.
  - `forecast_cashflows`: public dispatcher supporting `rolling-mean`, `seasonal-naive`,
    and `baseline-v1`.
- **Fallbacks**: Short-history fallback automatically reverts seasonal-naive to rolling-mean;
  empty history falls back to zero-flow baseline; zero cash-flow history returns zero predictions.
- **Horizons**: Validated for paths of 1, 2, 4, and 96 future 15-minute intervals (and arbitrary
  exact multiples of bucket_minutes).
- **Tests**: 137 passed (15 new forecasting tests, all existing 122 preserved).
- **Command**: `$env:PYTHONPATH=".;backend"; uv run --with pytest --with fastapi --with pydantic --with httpx --with sqlalchemy --with pydantic-settings pytest tests/ -q`
- **Files**: `treasury_intelligence/features.py`, `treasury_intelligence/forecasting.py`,
  `treasury_intelligence/api.py`, `treasury_intelligence/__init__.py`,
  `tests/treasury_intelligence/test_forecasting.py`, `tests/treasury_intelligence/test_contracts.py`,
  `docs/member1/ENGINE_CONTRACT.md`, and this progress log.
- **Commit**: `feat(engine): implement causal features and baseline forecasting`
- **Push Target**: `origin/feat/treasury-intelligence`
- **Next Task**: Await explicit assignment; stop after RJ-M1-03.

### [RJ-M1-02] Financial Mathematics
- **Status**: COMPLETED
- **Scope**: Pure pathwise peak shortfall, explicit contractual vault settlement
  schedules, supplied-buffer reserve, frozen reserve API implementation, candidate
  surplus, ACT/365 simple expected interest, early redemption costs, and signed
  expected net economic benefit. Original model fields and signatures preserved.
- **Timing**: Outflows at bucket start, inflows at bucket end; only explicit
  unbooked vault settlements count at actual availability. Locked balances are not
  cash. Duplicate schedules are rejected. Source-exclusive forecast inflows are
  a documented caller requirement because frozen buckets have no source IDs.
- **Rounding**: Integer cents, Decimal rate calculations; reserve uncertainty and
  penalty round upward; expected interest rounds half up. No realized-return claims.
- **Tests**: Full suite 122 passed, including original baseline and contract checks.
  Added required $8M ordering, $14M reserve, $684.93 one-day yield, zero flows,
  settlement timing, booked/duplicate maturity, penalty and invalid-input tests.
  Updated the former reserve-stub assertion to test the implemented reserve API.
- **Command**: `$env:PYTHONPATH=".;backend"; uv run --with pytest --with fastapi --with pydantic --with httpx --with sqlalchemy --with pydantic-settings pytest tests/ -q`
- **Files**: Member 1 package, its tests, ENGINE_CONTRACT.md, and this log only.
- **Commit**: `feat(engine): implement reserve and economic calculations`
  (hash in Git history and completion report).
- **Push Target**: `origin/feat/treasury-intelligence`; result in completion report.
- **Next Task**: Await explicit assignment; stop after RJ-M1-02.

### [RJ-M1-01] Quantitative Engine Contracts
- **Status**: COMPLETED
- **Scope**: Added eleven immutable validated Pydantic 2 contracts, six public
  function declarations, package exports, standalone dependency declaration,
  public interface documentation, and coherent JSON fixtures.
- **Validation**: Strict integer cents and basis points, UTC timestamps,
  nonnegative financial values, reserve component totals, ordered forecasts,
  unique vaults, nested JSON round trips, and recommendation-only actions.
- **Boundaries**: No algorithms, ML, optimization, transfer execution, database,
  frontend, existing forecasting API, or backend changes.
- **Interface context**: MEMBER1_SCOPE.md and AGENT_RULES.md and the referenced
  prompt signatures were absent. New standalone signatures are recorded in
  ENGINE_CONTRACT.md; existing repository interfaces remain unchanged.
- **Files**: `treasury_intelligence/`, `tests/treasury_intelligence/`,
  `docs/member1/ENGINE_CONTRACT.md`, and this progress log.
- **Tests**: Full suite: 91 passed (14 existing and 77 contract tests).
  Command: `$env:PYTHONPATH=".;backend"; uv run --with pytest --with fastapi --with pydantic --with httpx --with sqlalchemy --with pydantic-settings pytest tests/ -q`
- **Diff Check**: `git diff --check` passed.
- **Commit**: `feat(engine): define public quantitative contracts`
  (hash available in Git history and the task completion report).
- **Push Target**: `origin/feat/treasury-intelligence`; push follows this commit,
  with its result recorded in the task completion report.
- **Next Task**: Await explicit assignment; stop after RJ-M1-01.

### [RJ-M1-00] Repository Audit and Branch Setup
- **Status**: COMPLETED
- **Branch**: `feat/treasury-intelligence`
- **Scope**:
  - Inspected repository structure, remote remotes, and branches.
  - Audited existing implementations in `forecasting/`, `backend/app/treasury/`, `simulation/`, and `contracts/`.
  - Defined explicit file ownership matrix separating Member 1's standalone mathematical engine from Member 2's backend persistence and Member 3's frontend.
  - Established engine home directory (`treasury_intelligence/`) and integration path (`forecasting/`).
  - Validated baseline test suite across all modules (14 passed).
- **Files Modified/Created**:
  - `docs/member1/REPO_AUDIT.md`
  - `docs/member1/PROGRESS.md`
- **Relevant Tests Executed**:
  - Command: `$env:PYTHONPATH=".;backend"; uv run --with pytest --with fastapi --with pydantic --with httpx --with sqlalchemy --with pydantic-settings pytest tests/`
  - Result: 14 passed (100%)
- **Commit Hash**: `cc4ee9d`
- **Push Status**: Pushed to `origin/feat/treasury-intelligence`


## RJ-M1-16G-FINAL - Local integration verification (2026-10-18)

Combined repaired backend 88f9f456 and approved frontend 5bfee5c on isolated fix/rj-m1-16g-final-demo. Protected quantitative files remain byte-identical to de48d699; chronology source unchanged from 88f9f456. Added narrow live UI mappings and opt-in retained backtest children (default remains ephemeral). Results: 63 frozen quantitative, 30 focused PostgreSQL, 18 API/report and 198 frontend tests passed; production no-mock build passed. Browser exercised real creation/advance/scenario and one fresh 168-hour NORMAL comparison. See [final handoff](../FINAL_DEMO_HANDOFF.md) and [measured evidence](../FINAL_DEMO_EVIDENCE.json). Real losses, unpaid payouts and distinct emergency-event/closing-reserve-deficit counts are disclosed. Local commit only; no push or merge. Member 1 retains sign-off.
