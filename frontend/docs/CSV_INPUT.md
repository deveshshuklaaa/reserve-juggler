# CSV input

Choose **Upload CSV** in the workflow bar at the top of any screen.
Files are read locally; nothing is uploaded
to FastAPI. Download a working cash-flow template from the import dialog.

Both formats accept UTF-8 (including BOM), quoted CSV, and CRLF/LF line endings.
Limits are 2 MB and 5,000 observations. Blank required cells, duplicate or unknown
headers, malformed CSV, invalid dates, unordered timestamps, and gaps are rejected
with source row numbers. Previewing or rejecting a file does not replace a run.

## Local mock replay

Required columns, in any order:

```csv
timestamp,inflow_cents,outflow_cents
2026-10-17T08:00:00Z,280000000,220000000
2026-10-17T08:15:00Z,240000000,310000000
```

Use at least two rows with regular 15-minute or hourly UTC timestamps ending in Z.
Amounts are nonnegative integer USD cents, with no dollar signs, decimal fractions,
thousands separators, or exponent notation. Parser sums remain safe integers.
Mock replay additionally limits each amount to $1B, each direction's total to $10B,
and the replay horizon to 2,880 fifteen-minute steps (30 days).

After explicit confirmation, the mock adapter derives start time and duration from
the validated rows. Step zero is 15 minutes before the first observation. Each row
posts at its recorded time. For hourly input, intervening steps have zero cash flow;
amounts are not interpolated or resampled. Generated customer and merchant flows
are disabled. The existing mock ledger starts with $20M checking and $6M vault
principal, applies its documented policies and costs, and labels transactions CSV.

Forecasts consume observed history only. Strategy Arena replays the complete
original dataset for every selected strategy with the same opening capital, seed,
and policy. Interactive Shock Lab overlays do not enter these comparisons. Reset
replays the same input. Settlement delay is unavailable for this format because
aggregate inflows do not identify merchant receipts. Other explicit stress overlays
remain available and can change the replay's original flows.

## Official organizer dataset

The 16-column format follows the source validator on Member 2's branch:
`backend/app/data/organizer.py`. All columns are required:

```text
timestamp, deposits_usd, withdrawals_usd, net_flow_usd,
repo_sweep_window_open, repo_sweep_mature, tier1_repo_rate_apy,
tier2_bond_yield_pct, tier2_bond_price_index, tier2_bond_mod_duration,
tier3_stock_index_price, tier3_stock_volatility_pct,
tier1_early_redemption_haircut_pct, tier2_bond_liquidation_haircut_pct,
tier3_stock_liquidation_haircut_pct, emergency_overdraft_penalty_apr_pct
```

Source timestamps remain `YYYY-MM-DD HH:00:00`, strictly continuous hourly,
with **UNSPECIFIED** timezone. No Z suffix or browser timezone conversion is added.
Source dollar amounts, percentage values, and flags are preserved as strings.
Decimal comparisons and net-flow reconciliation use exact BigInt arithmetic.
Net-flow differences produce warnings; supplied values are never corrected.

This format supports validation and preview only. It does not enter the cash/vault
mock ledger, which cannot reproduce organizer market and execution semantics.

## Backend integration boundary

Member 2 currently provides an on-server organizer-file reader and unimplemented
run route handlers. There is no published multipart upload or dataset creation
endpoint. The real adapter's `createRunFromCashflows` explicitly rejects locally
with NOT_IMPLEMENTED and performs no fetch. No request fields or endpoint paths
have been invented. The shared context also blocks local replay in real mode.

To enable live input, Member 2 must supply the upload/validation response, dataset
identity, source schema and time basis, run-to-dataset association, accepted limits,
and replay/execution semantics. Organizer data must retain all market fields.
