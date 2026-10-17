# Member 1 Progress Tracker — Reserve Juggler

**Workstream**: Quantitative Treasury Intelligence Engine  
**Feature Branch**: `feat/treasury-intelligence`  
**Remote Target**: `origin/feat/treasury-intelligence`  

---

## Task Log

### [RJ-M1-06 reconciliation] One canonical four-tier family
- **Status**: Reconciled and tested; publication isolated on
  `codex/rj-m1-06-contract-reconciliation` with explicit user approval.
- **Compared**: `87a8217` and `974154e` field by field before integrating histories.
  Decisions and every retained/renamed/removed schema are recorded in
  `CONTRACT_RECONCILIATION.md`. Neither commit was automatically canonical.
- **Canonical module**: `treasury_intelligence.portfolio`. Keep UUID/run/source
  isolation, explicit cash/liquidity, per-loan liabilities, tier valuations and
  signed P&L from the local implementation. Port the teammate's useful native
  source/quote, schedule, cost, forecast-provenance, target and order-time checks.
  Retire the competing four_tier.py module and old schema payloads; no adapter.
- **Financial decisions**: No invented quantity-to-index conversion or half-up
  market-value formula. Historical repo entry is 17:00 with next-day 08:00 maturity.
  Estimates, accrued/realized interest, P&L, fees and stress are separate. Explicit
  paid/unpaid financing splits reconcile net liabilities without double charging.
- **Tests**: Contract suites **162 passed**; all Member 1 **329 passed**; complete
  branch suite **343 passed**; existing pipeline groups **9 passed**. Commands use
  `PYTHONPATH=.;backend`, `DATABASE_URL=sqlite:///:memory:` and pytest with
  `-q -p no:cacheprovider`. Fixture-loop-scope deprecation warning is pre-existing.
- **Handoff**: ENGINE_CONTRACT and FOUR_TIER_HANDOFF name the same canonical
  module, exact fields, view-only metadata and unchanged Member 2 persistence.
  Request/response fixtures use the canonical schema; original source rows retain
  source net flow and Decimal precision. Contract-only recommendation declaration
  raises NotImplementedError; no optimizer/forecast/replay is implemented.
- **Concurrent later work**: The shared branch advanced to `4bcf19c` (hourly
  forecasting) and `85d0c49` (instrument economics) during reconciliation. Those
  commits are NOT integrated into this RJ-M1-06 review branch. Adapting later
  algorithms to the approved canonical contracts is a separately authorized task.
- **Verification/publishing**: Review Git diff/status, refresh repository Graphify,
  preserve both audited histories without force-push, rerun the complete tests on
  the resolved tree, and publish only the approved review branch. Resulting commit
  hashes and remote confirmation are in the completion report.
- **Stop**: No RJ-M1-07 work; no Member 2 database/API or frontend changes.

### [RJ-M1-06] Four-Tier Contract Migration
- **Status**: COMPLETED (contract-only; no RJ-M1-07 work).
- **Inspected bases**: Member 1 `c35da91`; Member 2 four-tier persistence `52e58bc`.
  Preserved both workstreams without merging/reimplementing persistence.
- **Canonical contracts**: `treasury_intelligence/portfolio.py` defines typed
  cash/repo/bond/equity positions, liquidity, overdraft liability, valuation,
  portfolio source/state, four-tier policy/reserve and recommendation-only order
  plans. `PortfolioTreasuryContext` is an alias of `PortfolioState`, not a second
  portfolio definition. Package exports are additive.
- **Compatibility**: Legacy generic-vault types/signatures and all algorithms are
  unchanged apart from context/vault docstrings identifying their legacy scope.
  Naive organizer timestamps remain UNSPECIFIED and hourly; explicitly UTC
  synthetic timestamps remain UTC. Decimal percentage rates are not rounded to
  integer bps. Strict cents, signed P&L, immutable models and forbidden extras.
- **Member 2 handoff**: `FOUR_TIER_HANDOFF.md` maps the wire DTOs to existing tables
  and separates view metadata from persisted fields. Verified six DTO field sets
  against the actual ORM source at `52e58bc` using AST inspection, without ORM or
  database imports. Repo market value maps separately to position valuations.
- **Validation**: Source/run consistency, identities, tier/value/liquidity totals,
  separate liability principal, timestamp basis/causality, Decimal precision,
  discriminated union schemas, JSON round trips, deterministic serialization,
  invalid financial inputs and explicit recommendation-vs-execution semantics.
- **Tests**: New four-tier suite **90 passed**; all Member 1 tests **257 passed**;
  complete branch suite **271 passed**; existing pipeline groups **9 passed**.
  Commands (with `PYTHONPATH=.;backend`, `DATABASE_URL=sqlite:///:memory:`):
  `python -m pytest tests/treasury_intelligence -q -p no:cacheprovider` and
  `python -m pytest tests -q -p no:cacheprovider`.
  Existing pytest-asyncio fixture-loop-scope deprecation warning is non-fatal.
- **Boundaries**: No persistence, endpoints, frontend, forecasting algorithm,
  pricing/trading/interest execution or integration adapter changes. No organizer
  CSV is copied or edited. Public OpenAPI and Member 2 contracts are untouched.
- **Open questions**: Index quantity/notional convention, fill/accrual rounding,
  unpaid financing-cost treatment and the later four-tier algorithm/API adapter;
  these are documented rather than implemented or inferred.
- **Graphify**: Repository-level graph refreshed from actual Member 1 branch code;
  no invented implemented link to Member 2's separate-branch persistence.
- **Commit**: `feat(engine): add four-tier portfolio contracts` (hash in completion report).
- **Push target**: `origin/feat/treasury-intelligence`; no history rewrite.
- **Next task**: Await explicit assignment. Stop before RJ-M1-07.

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
