# Pre-RJ-M1-10 canonical contract check

Checked 2026-10-18 on `feat/treasury-intelligence`. **Not aligned; RJ-M1-10
must not assume canonical portfolio inputs work with the current algorithms.**
This is a compatibility finding, not a new optimizer or completed migration.

## Verified Git state

- Local HEAD and freshly fetched `origin/feat/treasury-intelligence`:
  `c3cebcd2ac2f4502e0916405c203240e15dc89ed` (RJ-M1-09).
- Reviewed canonical branch `origin/codex/rj-m1-06-contract-reconciliation`:
  `1fcff80f05136a1d90faf8b88adacc8d313dc072`.
- Common ancestor: `974154e962c6ef27ba19d1ff6c87ac3a245b2797`.
- `treasury_intelligence/portfolio.py` is absent from both local HEAD and the
  remote feature branch. It is present on the separate review branch.
- Review-only commits are `87a8217`, `af36805`, and `1fcff80`; feature-only
  commits after the shared base are RJ-M1-07, RJ-M1-08, and RJ-M1-09.
  The review progress log explicitly says those later algorithms are not integrated.
- No merge, checkout, reset, file deletion, or cherry-pick was performed. Fetch
  only refreshed remote references. Existing algorithms and their history remain.

## Public interface differences

| Area | Current RJ-M1-07/08/09 interface | Reviewed canonical contract / conflict |
| --- | --- | --- |
| Module and root imports | `four_tier.py`; root/API export its types | `portfolio.py`; old family retired, not a supported wire adapter |
| Source identity | String position IDs and aggregate context | UUID position/run/order IDs, dataset/source provenance and explicit time basis |
| Forecast inputs | Hourly points/metadata have no time_basis | Canonical HourlyForecastPoint and ForecastRiskMetadata require it |
| Historical request | FourTierPortfolioState, FourTierRiskPolicy | PortfolioState, FourTierTreasuryPolicy, history_available_at attestation and source-backed quotes |
| Net-flow target | Forecast metadata declares deposits_minus_withdrawals | Canonical metadata permits source_net_flow_usd only; cannot honestly relabel existing targets |
| Repo economics | Tier1RepoPosition.matures_at, entry_apy_pct, early_break_allowed, early_break_fee_pct | RepoPosition.scheduled_maturity_at, applicable_apy_pct, optional early_redemption_allowed, required source haircut and explicit status/liquidity |
| Market positions | Normalized index_units and imposed index-times-units cent valuation | Explicit quantity/acquisition indices and supplied current valuations; no inferred quantity conversion |
| Portfolio economics | `.repos/.bonds/.equities`, aggregate `.overdraft`, independently recomputed totals | `.repo_positions/.bond_positions/.equity_positions`, per-loan `.overdrafts`, reconciled PortfolioValuation |
| Liability costs | Aggregate accrued financing cost | Explicit paid/unpaid split; only outstanding principal and unpaid cost enter liabilities |
| Orders/results | TradeRecommendation / PortfolioRecommendation | RecommendedOrder / FourTierDecisionResult; UUID/action/tier names and supplied reserves differ |
| Cost/risk fields | CostBreakdown includes market_loss_cents | Canonical fee breakdown excludes market P&L; losses remain separate |

Obsolete imports are in `hourly_forecasting.py`, `ml_forecasting.py`,
`instrument_economics.py`, `api.py`, and package `__init__.py`. Existing fixtures
and their contract tests also encode the old family. There are not two active
schema families in the current tree: the competing canonical family exists only
on the review branch. Copying it without migrating consumers would create that
duplication and leave the old algorithms incompatible.

## Executed checks

- Full current feature suite: **328 passed** with pytest, Pydantic, FastAPI/httpx,
  SQLAlchemy/settings, and scikit-learn available. Command:
  `$env:PYTHONPATH=".;backend"; uv run --with pytest --with fastapi --with pydantic --with httpx --with sqlalchemy --with pydantic-settings --with scikit-learn pytest tests/ -q`
- Loaded the reviewed `portfolio.py` from its Git blob into a temporary in-memory
  module, without changing repository files. Its supplied canonical portfolio
  fixture validates against that reviewed code.
- Current point/metadata JSON fails canonical validation because time_basis is
  absent. Current repo JSON fails required identity/liquidity/name checks.
- Passing a reviewed RepoPosition to current `calculate_repo_economics` raises
  AttributeError for `matures_at`; passing PortfolioState to current
  `calculate_portfolio_values` raises AttributeError for `repos`.
- **35 of the 168 real fixture rows** have source net flow different from exact
  deposits minus withdrawals. Example: 2026-01-01 14:00 source net 165091.77 USD
  versus derived 165091.78 USD. Current `_extract_amounts` preserves source net
  in its USD slot but recomputes its cents slot, and ML evaluation builds actual
  net/shortfall from deposits minus withdrawals. Source-target evaluation must
  therefore be recomputed, not presented as already measured by RJ-M1-09.

## Safe outcome and unresolved work

This check corrects documentation to distinguish reviewed canonical contracts
from the implemented feature-branch interfaces. It does **not** silently alias
incompatible models, relabel forecast targets, impose a unit conversion on
canonical quantities, or merge a review snapshot over completed later work.
No financial algorithm was rewritten under an import-compatibility fix.

Before canonical integration can be marked complete, select the reviewed contract
files/tests selectively while retaining RJ-M1-07/08/09, migrate their consumers
and fixtures to canonical identities/time/source requirements, adapt repo and
per-loan liability fields, honor supplied portfolio valuation, and explicitly
resolve source-net forecasting/evaluation and quantity-to-price valuation semantics.
These are behavior-changing migration decisions, not safe import-only edits.
The existing 328 passing tests establish the old feature baseline, **not canonical
interoperability**. RJ-M1-10 remains unimplemented.
