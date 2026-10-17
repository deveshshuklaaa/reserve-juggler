MEMBER 3 — UPDATED FOUR-TIER FRONTEND DEVELOPMENT HANDOFF
Reserve Juggler | HackForge 2026
Role: React Frontend, Financial Visualization and Judge Demo
Repository: https://github.com/deveshshuklaaa/reserve-juggler.git
Branch: Verify and reuse the existing frontend feature branch; the latest progress report calls it frontend.

1. Current reported progress
The frontend reportedly has:

Treasury Command Center.

Liquidity Shock Lab.

Treasury Strategy Arena.

Deterministic mock API.

A light banking theme.

Forty-one passing tests.

A passing production build.

Desktop and mobile layout checks.

However, the reported changes were still local and not yet committed or pushed.

DO NOT rebuild these screens.

First preserve the existing implementation, verify tests, commit the owned frontend files, and push to the existing frontend feature branch.

Do not change branch names without checking with the team.

2. Official requirement update
The organizer's problem is now a four-tier liquidity and investment system.

Tier 0: Cash buffer, 0%.

Tier 1: Overnight repo, floating APY, entry at 17:00, maturity at 08:00, 0.5% early-break fee.

Tier 2: Sovereign bonds, floating yield, price-index mark-to-market, 2% liquidation haircut.

Tier 3: Equities, index price and volatility, 15% emergency slippage.

Emergency overdraft: separate financing liability and cost.

Historical data contains 8,760 hourly observations.

Preserve the native historical hourly timeline. Do not fabricate 15-minute historical data to fit the existing dashboard.

3. Screen 1 — Treasury Command Center
Upgrade the existing screen.

Required KPI cards:

Tier 0 immediately available cash.

Required liquid reserve.

Tier 1 repo principal and interest.

Tier 2 bond market value.

Tier 3 equity market value.

Total gross portfolio assets.

Outstanding overdraft liabilities.

Net portfolio value.

Accrued and realized financial returns, separately.

Add a four-tier allocation chart.

Add an instrument table containing:

Instrument.

Current allocation.

Market value.

Latest rate or index price.

Current risk/liquidity status.

Liquidation fee.

Unrealized P&L where relevant.

Clearly distinguish liquid cash, locked repo, bonds, and equities.

Display the current historical hour, not a fabricated quarter-hour timestamp.

4. Repo visualization
Create a dedicated repo position panel.

Show:

Floating repo APY.

Whether the 17:00 sweep window is open.

Next maturity at 08:00.

Existing repo principal.

Accrued repo interest.

Available redemption rules.

Early-break fee.

Next scheduled repo settlement.

Do not show a 24-hour lock or fixed 5% APY as the official model.

5. Bonds and equities
Add market-value and P&L visualizations.

Tier 2:

Current bond price index.

Yield-to-maturity.

Modified duration.

Bond holdings.

Realized/unrealized P&L.

Liquidation haircut.

Tier 3:

Current stock index price.

Volatility.

Equity holdings.

Realized/unrealized P&L.

Emergency slippage.

Do not show a guaranteed equity yield.

Do not display bond quoted yield as automatically realized interest.

Use actual backend values.

6. Forecast visualization
Update the forecast chart to support:

Native hourly deposits.

Native hourly withdrawals.

Hourly net flow.

Forecasted inflows/outflows.

Forecast uncertainty.

Cumulative cash requirement.

Required Tier 0 reserve.

Recommended selectors:

Next 1 hour.

Next 3 hours.

Next 6 hours.

Next 15 hours.

Next 24 hours.

Clearly label historical actual data versus future predictions.

Show:

Baseline or ML model version.

Forecast cutoff time.

Risk policy.

Validation status.

7. Treasury decision panel
Expand the old HOLD/SWEEP/WITHDRAW/WARNING card to represent actual multi-asset decisions.

Support:

HOLD cash.

INVEST in repo, bonds or equities.

REBALANCE between tiers.

LIQUIDATE eligible positions.

LIQUIDITY_WARNING.

Show:

Recommended instrument.

Proposed allocation.

Required reserve.

Expected return.

Liquidity risk.

Applicable transaction or liquidation costs.

Explanation.

Recommendation/execution status.

Do not mark proposed trades as executed until Member 2 confirms execution.

8. Screen 2 — Liquidity Shock Lab
Preserve existing five cash-flow scenarios:

NORMAL.

HIGH_WITHDRAWAL.

LOW_DEPOSIT.

SETTLEMENT_DELAY.

LIQUIDITY_SHOCK.

Add asset-aware stress controls if supported:

Bond yield-rate shock.

Bond price decline.

Equity market crash.

Increased equity volatility.

Early repo redemption scenario.

High-cost emergency overdraft.

IMPORTANT:
The organizer CSV must remain immutable.

Apply judge-triggered shocks to a separate derived simulation or scenario overlay, not by editing the historical source file.

Do not claim historical market events were present in the CSV if they were artificially introduced for stress testing.

Show before/after changes to:

Cash reserve.

Repo positions.

Bond value.

Equity value.

Portfolio value.

Emergency costs.

Treasury decisions.

9. Screen 3 — Strategy Arena
Upgrade the current three-strategy comparison to:

All Cash.

Cash + Repo Rule.

Four-Tier Reserve Juggler.

Optionally retain a static multi-asset baseline.

Show actual historical-replay metrics:

Ending net portfolio value.

Repo interest.

Realized market P&L.

Unrealized market P&L.

Early redemption fees.

Bond liquidation costs.

Equity slippage.

Overdraft costs.

Average idle cash.

Reserve breaches.

Failed payouts.

Maximum drawdown.

Risk-adjusted return where available.

Only show results produced by Member 2's benchmark engine.

Do not claim Reserve Juggler won if the actual result does not support that conclusion.

10. API integration
The existing frontend reportedly uses /api/v1/runs/... routes through a Fetch adapter.

Preserve this integration approach.

Member 2 owns the finalized API.

Work with the approved OpenAPI contract.

Add support for:

Dataset metadata.

Historical hourly run mode.

Portfolio position summaries.

Tier-specific market valuations.

Multi-asset decisions.

Backtest report results.

Asset stress scenarios where available.

Keep frontend components separated from mock/live API adapters.

In LIVE mode, no financial result may come from a mock fixture.

Use clearly labeled mock mode if the backend is not yet available.

11. Precision and timing
Use:

Integer cents for ledger amounts.

Decimal-string rates and prices where appropriate.

Source-time labels for historical observations.

Explicit timezone status.

Correct percentage conversion.

Do not silently treat source historical timestamps as UTC.

Do not use the old assumption that all vault assets pay fixed 5% interest.

12. Updated task milestones
F0 — Preserve current frontend
Verify 41 tests and build, inspect changes, commit and push to the existing frontend branch.

F1 — Four-tier models and API adapter
Implement additive frontend contracts, mock fixtures, formatting and backend adapter changes.

F2 — Four-tier Treasury Command Center
Portfolio KPI cards, instrument valuations, repo schedule and P&L charts.

F3 — Forecasts and decision explanations
Hourly forecast chart, required reserve, four-tier allocation explanation.

F4 — Multi-asset Liquidity Shock Lab
Existing scenarios plus bond/equity stress controls where backend-supported.

F5 — Four-tier Strategy Arena
Historical backtest metrics, comparison charts and honest performance reporting.

F6 — Live backend integration
Connect Member 2's actual API, remove mock-only assumptions and test execution statuses.

F7 — Final demo and release
Responsive validation, financial-label audit, CSV export, screenshots and demo rehearsal.

After each milestone:

Run relevant tests.

Verify the production build when appropriate.

Update progress documentation.

Commit only frontend-owned files.

Push to the existing frontend branch.

Report actual outcomes.

STOP before the next milestone.

13. Important restrictions
Do not:

Rewrite the entire React project.

Change Member 1's optimization code.

Change Member 2's backend/database code.

Invent performance results.

Display fake market returns as real results.

Assume all holdings are instantly liquid.

Hard-code bond/equity market prices.

Rewrite historical timestamps.

Present synthetic stress overlays as unmodified organizer history.

Change the API contract without coordination.

14. Immediate next action
Complete F0 first.

Verify the existing frontend's tests and build, commit its current functional state and push successfully.

Then obtain Member 1's updated four-tier engine contract and Member 2's finalized API schemas before starting F1.

Final objective: A polished, interactive, four-tier treasury command center that demonstrates actual forecasting, market valuation, reserve decisions, stress outcomes, and historical benchmark performance without fabricated financial claims.






Reserve Juggler — Official Requirements Update

The organizers' PDF confirms that we must build a FOUR-TIER treasury platform, not just checking + one vault.

We now have:

Tier 0: Cash.

Tier 1: Overnight repo, 17:00–08:00.

Tier 2: Sovereign bonds with price and duration risk.

Tier 3: Equities with market volatility and liquidation costs.

The official CSV contains 8,760 HOURLY observations and 16 columns. We must preserve it unchanged.

Member 1 (me): Extending our completed quantitative engine for hourly forecasting, four-tier risk, instrument economics, and multi-asset optimization. First new task is RJ-M1-06.

Member 2: Continue from the organizer-data foundation. Verify four-tier persistence, then implement hourly execution, repo, bonds, equities, and historical backtesting.

Member 3: First commit/push the existing working three-screen frontend, then upgrade it for the four tiers and the finalized API.

Integration rules:

Keep existing feature branches.

Commit and push after each tested milestone.

No silent breaking API changes.

Member 1 owns recommendations; Member 2 owns execution; Member 3 displays results.

No fake 15-minute historical data, guaranteed equity returns, or fabricated benchmark metrics.

Share contracts and example JSON as soon as they are ready.

Please send your latest commit hash, completed milestone, current blockers, and next task before we start integration.