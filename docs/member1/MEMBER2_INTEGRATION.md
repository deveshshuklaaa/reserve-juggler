# Member 2 integration handoff — RJ-M1-14

Use explicit module imports at the canonical boundary:

```python
from treasury_intelligence.portfolio import PortfolioState, FourTierTreasuryPolicy, HourlyForecastPoint
from treasury_intelligence.liquidity_risk import FourTierLiquidityRiskRequest, calculate_four_tier_liquidity_risk
from treasury_intelligence.optimizer import AllocationOptimizerRequest, AllocationRewardModel, recommend_four_tier_allocation
from treasury_intelligence.monte_carlo_risk import simulate_multi_asset_monte_carlo_risk
```

The optimizer returns `AllocationOptimizerResult`; its `decision` is canonical
`FourTierDecisionResult`. Consume `decision.targets`, `decision.orders`,
`decision.expected_costs`, `decision.explanations`, `decision.feasible`, and
`summary_action`. `model_dump(mode="json")` produces JSON-compatible values;
Decimals are strings. Recommendations and orders always remain NOT_EXECUTED.
Member 2 alone validates and executes orders, records fills and updates persistence.

Orders supply UUID identity/provenance, tier, action, optional position_id/quantity,
amount_cents, expected_proceeds_cents, expected_costs, earliest_execution_at,
expected_settlement_at, and expected_maturity_at. Amount interpretation is action-specific;
read the optimizer contract before booking cash legs. Preserve order sequence and
revalidate balances, quotes, settlement, unit conventions, exposure and credit caps.
Do not infer a fill from feasibility, stable order identity, or recommendation status.

Build canonical snapshots with separate cash, repo_positions, bond_positions,
equity_positions, overdrafts and valuation. Market positions use
current_market_value_cents and current_market_price_index; canonical schemas accept
supplied valuations, not an implicit units-to-USD convention. New market purchases
require an explicit usd_per_index_point_per_unit reward assumption. Liabilities
include principal and unpaid financing cost. Existing debt is never available cash.

Historical observations remain naive/time_basis=UNSPECIFIED and hourly. Establish
when each row becomes known: a timestamp alone is not proof that its full hourly
flows were available at that instant. Only completed/available history belongs in
forecast inputs. Quotes and model training/calibration cutoffs cannot exceed as_of.
The demo assumes its supplied decision-time observation is available.

Forecasting still returns the compatibility `four_tier.HourlyForecastResult`.
Explicitly copy point fields into canonical `portfolio.HourlyForecastPoint` (including
time_basis). Preserve metadata separately: forecast net targets deposits minus
withdrawals, whereas canonical metadata currently permits source_net_flow_usd only.
Do not relabel the target. Source net_flow_usd is independent. Root names such as
HourlyForecastPoint, MarketRateObservation and OverdraftLiability retain older
contracts; avoid mixing root models into canonical snapshots. Legacy economics
portfolio/repo helpers also consume their documented older position family; scalar
bond/equity calculations remain usable with explicit conversion conventions.

Liquidity forecast starts at portfolio.as_of. Outflows debit hour start; inflows
credit hour end. Supply explicit repo settlements only when not already in cash or
forecast deposits. Remove settled claims once. Repo entry is 17:00, maturity next-day
08:00; ACT/365 fixed interest covers actual 15 hours, quoted percentage divided by
100. Future floating fixings cannot be used for a live estimate. Source early-break
haircut applies only when both policy and position permit redemption.

Choose calibrated allowance OR complete weighted scenario quantiles. Scenario
reserve already includes uncertainty; do not add provisional point buffers again.
Liquidation proceeds are stressed marks minus source haircuts, subject to permission
and settlement timing. Duration is a separate hypothetical stress, never a second
charge against observed bond marks. Bond YTM is not a cash coupon; equity price
returns are not guaranteed interest.

Monte Carlo NAV is a hypothetical full permitted-liquidation endpoint, not selected
optimizer execution. It removes sold/settled assets, includes cash flows once,
separates new borrowing from assets, and charges existing/new principal financing.
Unfunded cash may be negative. New borrowing uses a supplied portfolio quote or the
latest available historical APR, never an invented default. Full-horizon borrowing
cost is conservative; this is not a realized execution/backtesting ledger.

Integration readiness: contract/demo round trips are tested. No Member 2 API or
execution adapter has been modified or certified end-to-end. See FINAL_AUDIT.md for
remaining boundary and data-availability limitations.
