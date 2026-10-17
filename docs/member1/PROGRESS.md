# Member 1 Progress Tracker — Reserve Juggler

**Workstream**: Quantitative Treasury Intelligence Engine  
**Feature Branch**: `feat/treasury-intelligence`  
**Remote Target**: `origin/feat/treasury-intelligence`  

---

## Task Log

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
