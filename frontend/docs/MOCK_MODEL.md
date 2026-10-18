# Deterministic frontend development model

This model demonstrates interfaces and interactions while Members 1 and 2 finish their services. It is not the production forecasting/risk model, a calibrated financial guarantee or evidence of ML performance.

## Defaults and repeatability

Seed 2026; start 2026-10-17 08:00 UTC; checking $20M; initial vault $6M; 15-minute steps; two-day interactive run; vault rate 500 bps; 96-step lock. API instances retain isolated in-memory runs. Reset reproduces the seed/configuration; reloading starts fresh. Backtest day counts are 7/14/30 and do not advance the interactive run.

The pseudorandom stream is derived only from seed and external-event step. Strategy actions do not consume random numbers, so all compared policies receive identical external cash-flow demand. Policy and scenario settings determine the rest of the result. The UI receives only executed history and current forecasts, never future generated actual transactions.

## Flows and scenarios

Each interval produces deposits, incoming merchant settlements and customer payouts. Signs come from explicit direction. HIGH_WITHDRAWAL multiplies withdrawal demand; LOW_DEPOSIT reduces deposits; SETTLEMENT_DELAY defers a configured fraction of incoming receipts and releases the same cents later; LIQUIDITY_SHOCK adds one outflow at the effective step; NORMAL restores future baseline generation. Historical shocks are retained. A newer effective event supersedes an earlier active flow regime.

Scheduling does not change checking. Only advancing applies external flows and policy decisions. Scenarios report scheduled/active/completed (or superseded) status. Requested payout demand is recorded separately from funded actual outflows. Failed payouts are counted and never recorded as successfully paid transactions.

## Ledger and vault terms

All money is integer cents. Each vault position carries its own original rate, maturity and early-exit terms. Simple ACT/365 interest accrues with a BigInt fractional-cent remainder. It is credited to realized earnings only when principal and interest mature into checking. New policy settings cannot change existing positions.

Early redemption uses eligible original terms, forfeits accrued interest and deducts the original principal penalty. The simplified mock redeems whole positions. Locked positions without early-exit permission are unavailable. Emergency credit has a $10M cap; borrowing has a simplified one-basis-point charge per interval. Unfunded borrowing costs increase liabilities. No debt repayment policy is modeled. Unfunded payouts create explicit failure events rather than negative available checking.

Conservation is tested at each step:

`checking + remaining vault principal − outstanding borrowing = initial principal + external inflows − funded payouts + realized interest − redemption penalties − borrowing costs`

Accrued, unrealized interest is disclosed separately and is not included in principal allocation. Cash sweeps and redemptions do not independently create profit. Net benefit is realized interest minus penalties and borrowing costs; it is a demonstration metric, not an incremental benefit against a counterfactual.

## Baseline and policies

The mock baseline uses only the latest eight observed demand intervals. It estimates a simple mean net drain, a heuristic peak requirement and a percentile-scaled buffer plus operational reserve. Confidence bands are heuristic and explicitly not calibrated probabilities. It must never be described as trained ML or Monte Carlo.

STATIC targets $14M cash; REACTIVE uses the latest observed drain plus a fixed floor; RESERVE_JUGGLER uses the observed baseline, uncertainty-style buffer and active vault constraints. A sweep must exceed the minimum threshold. Recommendations include recorded explanations, pre/post checking and actual mock execution status. Shortfall warnings can remain unexecuted.

These definitions exist only in the mock adapter. Real mode reads backend decisions verbatim. Backtests run the same pure model in a worker, preserve seeded external demand, and calculate actual mock outcomes without forcing Reserve Juggler to win. MAE/RMSE and optimizer sensitivities are not invented.

## Integration limits

Report-job polling/status schemas and optional capability negotiation remain to be finalized. Real backend comparison support, risk outputs and evaluation are pending. This mock has no real funds, persistence, auth, banking rails, sophisticated borrowing policy or calibrated risk forecasts. It provides a coherent, tested frontend demonstration.
