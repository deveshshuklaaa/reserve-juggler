# FOUR-TIER FRONTEND CONTRACT & DATA SPECIFICATION

**Project**: Reserve Juggler — HackForge 2026  
**Role**: Frontend Models, Normalization, and Mock Adapters (Task F1A)  
**Branch**: `frontend`  
**Status**: Implemented & Verified in Frontend Layer

---

## 1. Overview & Architectural Scope

This specification defines the frontend data contracts, normalization schemas, precision rules, and mock adapter interfaces for the **Four-Tier Treasury System**.

The platform categorizes institutional assets and liabilities into four distinct liquidity and investment tiers plus emergency credit:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        FOUR-TIER ASSET SPECTRUM                        │
├───────────────────┬───────────────────┬───────────────────┬────────────┤
│ Tier 0: Cash      │ Tier 1: Repo      │ Tier 2: Bonds     │ Tier 3: EQ │
│ Immediate Liquid  │ 17:00 -> 08:00    │ Sovereign Mark-to-│ Growth     │
│ 0% APY            │ Floating APY      │ Market, 2% Haircut│ 15% Slip   │
└───────────────────┴───────────────────┴───────────────────┴────────────┘
         ▲                   ▲                   ▲                 ▲
         └───────────────────┴───────────────────┴─────────────────┘
                                     │
                    Emergency Overdraft Liability (10% APY)
```

---

## 2. Canonical Frontend Data Models

All monetary quantities are represented strictly as **integer USD cents** (`_cents` suffix).  
Rates, yields, and price index values preserve full precision using decimal strings.

### Tier 0 — Cash Buffer
* **`checking_cents`** (`integer`, cents): Cash immediately available in operating checking.
* **`required_reserve_cents`** (`integer`, cents): Minimum liquid cash required by risk policy (e.g. 95% or 99% quantile shortfall + operational buffer).
* **`operational_buffer_cents`** (`integer`, cents): Base safety reserve configured in policy.
* **`deployable_surplus_cents`** (`integer`, cents): Surplus checking cash above the required reserve eligible for sweeps (`max(0, checking - required_reserve)`).
* **`immediate_liquidity_cents`** (`integer`, cents): Cash available with zero settlement lag (`checking_cents`).
* **`status`** (`string`): `'BALANCED' | 'SURPLUS' | 'DEFICIT'`.

### Tier 1 — Overnight Repo
* **`id`** (`string`): Position identifier (e.g. `'REPO-2026-001'`).
* **`principal_cents`** (`integer`, cents): Current repo principal allocated.
* **`repo_apy_bps`** (`integer`, basis points): Annualized floating repo yield (e.g. `520` for 5.20%).
* **`repo_apy_decimal`** (`string`, decimal): Precision-preserving decimal rate string (e.g. `'5.2000'`).
* **`accrued_interest_cents`** (`integer`, cents): Uncredited interest earned since entry.
* **`realized_interest_cents`** (`integer`, cents): Cash interest credited at maturity.
* **`status`** (`string`): `'LOCKED' | 'MATURED' | 'REDEEMED'`.
* **`entry_window_open`** (`boolean`): True only during the daily 17:00 sweep window.
* **`entry_time`** (`string`): Sweep window time (always `'17:00'`).
* **`maturity_time`** (`string`): Daily settlement time (always `'08:00'`).
* **`early_redemption_allowed`** (`boolean`): Whether early termination is permitted.
* **`early_break_fee_bps`** (`integer`): Early redemption penalty (fixed at `50` bps / 0.5%).
* **`break_fee_cents`** (`integer`, cents): Calculated early break penalty if broken while locked.
* **`net_redeemable_cents`** (`integer`, cents): Liquidity recoverable immediately (`principal - break_fee` if locked).

### Tier 2 — Sovereign Bonds
* **`id`** (`string`): Bond issue identifier (e.g. `'BOND-SOV-10Y'`).
* **`notional_cents`** (`integer`, cents): Par / face value in cents.
* **`quantity`** (`number`): Number of bond contracts held.
* **`acquisition_price`** (`string`, decimal): Cost-basis price index string (e.g. `'98.5000'`).
* **`current_price`** (`string`, decimal): Current mark-to-market index price string (e.g. `'101.2500'`).
* **`market_value_cents`** (`integer`, cents): Mark-to-market valuation.
* **`ytm_bps`** (`integer`, basis points): Yield-to-maturity in bps (e.g. `445`).
* **`ytm_decimal`** (`string`, decimal): Precision-preserving YTM string (e.g. `'4.4500'`).
* **`modified_duration`** (`number`): Interest-rate sensitivity duration (e.g. `4.25` years).
* **`liquidation_haircut_bps`** (`integer`): Liquidation haircut (fixed at `200` bps / 2.0%).
* **`haircut_cents`** (`integer`, cents): Haircut discount applied if liquidated for immediate cash.
* **`realized_pnl_cents`** (`integer`, cents): Realized capital gain/loss upon sale.
* **`unrealized_pnl_cents`** (`integer`, cents): Open mark-to-market capital gain/loss.
* **`available_liquidity_cents`** (`integer`, cents): Net realizable cash value (`market_value - haircut`).
* **`liquidity_status`** (`string`): `'2-DAY_SETTLEMENT_OR_HAIRCUT'`.

### Tier 3 — Growth Equities
* **`id`** (`string`): Equity portfolio / index identifier.
* **`quantity`** (`number`): Share or unit quantity.
* **`acquisition_price`** (`string`, decimal): Benchmark acquisition index price (e.g. `'420.0000'`).
* **`current_price`** (`string`, decimal): Current stock index price (e.g. `'445.5000'`).
* **`market_value_cents`** (`integer`, cents): Mark-to-market valuation.
* **`cost_basis_cents`** (`integer`, cents): Original capital allocated.
* **`volatility_bps`** (`integer`): Annualized index volatility in bps (e.g. `1680` for 16.80%).
* **`volatility_decimal`** (`string`, decimal): Volatility decimal percentage string (e.g. `'16.80'`).
* **`emergency_slippage_bps`** (`integer`): Emergency fire-sale discount (fixed at `1500` bps / 15.0%).
* **`slippage_cents`** (`integer`, cents): Estimated slippage loss on forced immediate liquidation.
* **`realized_pnl_cents`** (`integer`, cents): Realized trading gain/loss.
* **`unrealized_pnl_cents`** (`integer`, cents): Open mark-to-market gain/loss.
* **`available_liquidity_cents`** (`integer`, cents): Value accessible in emergency (`market_value - slippage`).
* **`liquidity_status`** (`string`): `'MARKET_VOLATILITY_AND_SLIPPAGE'`.

### Emergency Overdraft
* **`borrowing_outstanding_cents`** (`integer`, cents): Unpaid principal borrowing liability.
* **`financing_rate_bps`** (`integer`): Annual financing penalty rate (fixed at `1000` bps / 10.0%).
* **`financing_cost_cents`** (`integer`, cents): Cumulative interest fees incurred.
* **`liability_status`** (`string`): `'ACTIVE' | 'CLEARED'`.
* **`is_active`** (`boolean`): True if outstanding debt &gt; 0.

### Portfolio Aggregates
* **`gross_assets_cents`**: `Tier 0 + Tier 1 Principal + Tier 2 Market Value + Tier 3 Market Value`.
* **`total_liabilities_cents`**: `Overdraft Borrowing Outstanding`.
* **`net_portfolio_value_cents`**: `gross_assets_cents - total_liabilities_cents`.
* **`total_immediate_liquidity_cents`**: `Tier 0 Cash + Tier 1 Net Redeemable + Tier 2 Liquidatable + Tier 3 Liquidatable`.
* **`total_realized_returns_cents`**: `Repo Interest Realized + Bond Realized P&L + Equity Realized P&L`.
* **`total_unrealized_returns_cents`**: `Repo Accrued Interest + Bond Unrealized P&L + Equity Unrealized P&L`.
* **`net_financial_benefit_cents`**: `Total Realized Returns - Overdraft Financing Costs - Break Fees`.

---

## 3. Precision & Time Invariants

1. **Integer Cents**: All balance sheet line items, transactions, P&L, and reserve buffers use signed 64-bit safe integer USD cents.
2. **Precision-Preserving Decimal Strings**: Quoted prices (e.g. bond index `101.2500`, equity index `445.5000`) and yields must be preserved as strings or formatted with exact decimals without IEEE-754 binary floating-point drift.
3. **Source Timestamps**:
   - The official historical dataset consists of **8,760 hourly observations**.
   - Timestamps in historical replay mode are **timezone-unspecified** (e.g. `'2026-01-01 17:00:00'`).
   - The frontend **does not append 'Z' or convert timezone-unspecified historical timestamps to UTC**.
   - Synthetic demo simulations use explicit ISO UTC (`'2026-10-17T08:00:00.000Z'`).

---

## 4. Multi-Asset Treasury Decisions

The decision model distinguishes between **recommendations** and **executed trades**:

| Action Enum | Tier | Description |
|---|---|---|
| `HOLD` | Tier 0 | Maintain operating balance within target corridor. |
| `INVEST_REPO` | Tier 1 | Sweep deployable surplus into overnight repo at 17:00. |
| `INVEST_BONDS` | Tier 2 | Allocate long-term liquidity buffer into sovereign bonds. |
| `INVEST_EQUITIES`| Tier 3 | Allocate growth surplus into index equity basket. |
| `REBALANCE` | All | Reallocate between tiers to optimize yield / restore cash. |
| `LIQUIDATE` | Tier 2/3 | Liquidate bonds or equities to satisfy reserve deficit. |
| `WITHDRAW` | Tier 1 | Redeem mature or broken repo principal to checking. |
| `LIQUIDITY_WARNING`| Tier 0 | Critical cash deficit below safety threshold. |

Every decision object explicitly provides:
* **`executed`** (`boolean`): False for recommendations awaiting backend confirmation; true only when confirmed on ledger.
* **`execution_status`** (`string`): `'NOT_REQUIRED' | 'EXECUTED' | 'RECOMMENDED' | 'REJECTED'`.

---

## 5. Strategy Arena Benchmark Contract

The backtest benchmark model evaluates three standardized strategies across identical market conditions:
1. **All Cash (`ALL_CASH`)**: 100% held in Tier 0 checking. 0% yield, 0% default risk, maximum cash drag.
2. **Cash + Repo (`CASH_PLUS_REPO`)**: Sweeps into overnight repo during the 17:00 window, maintaining required cash reserves.
3. **Four-Tier Reserve Juggler (`FOUR_TIER_AUTOPILOT`)**: Autonomous optimization across Tier 0 (Cash), Tier 1 (Repo), Tier 2 (Bonds), and Tier 3 (Equities) with dynamic shock damping.

Metrics reported:
* Ending Net Portfolio Value (`ending_net_portfolio_cents`)
* Realized Yield (`realized_yield_cents`)
* Realized Market P&L (`realized_pnl_cents`)
* Unrealized Market P&L (`unrealized_pnl_cents`)
* Total Transaction & Liquidation Costs (`costs_cents`)
* Overdraft Liabilities Incurred (`overdraft_costs_cents`)
* Reserve Breaches (`reserve_breaches`)
* Capital Efficiency Score (`capital_efficiency_score`)
