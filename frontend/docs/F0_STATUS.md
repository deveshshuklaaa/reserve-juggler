# F0 — Preserve the existing frontend

Date: 17 October 2026. Branch: `frontend`. Milestone scope: preserve the functional three-screen baseline; stop before F1.

## Preserved baseline

- Treasury Command Center, Liquidity Shock Lab and Treasury Strategy Arena.
- Apple-inspired light design, compact top navigation, responsive mobile menu and snapshot-derived capital allocation graphic.
- Independent deterministic mock API, centralized Fetch adapter, safe simulation playback and decision/execution separation.
- Existing cash/vault demonstration, scenario controls, comparison model and financial-unit tests.
- Build configuration, lockfile, screenshots, running instructions, contract-gap analysis and development-model documentation.

The current mock's 15-minute interval, fixed vault-rate default and generic lock are **legacy synthetic-demo assumptions**. They must not be presented as the new official repo or historical replay behavior. They are preserved in F0 without silently changing financial semantics.

## Verified

- `npm.cmd test`: **42 tests passed in four files**, 6.03 seconds in the F0 verification run.
- Production build: verified before publication; includes the independent backtest-worker bundle.
- Repository scope: only frontend-owned files are staged for the milestone.
- Existing branch and origin tracking are retained. No force-push or merge into develop/main is part of F0.

The final milestone report provides the actual commit hash and successful push confirmation. Git history is the authoritative publication record.

## Accepted requirement changes for F1 onward

The received team handoffs supersede the original two-tier assignment wherever they conflict. They describe:

1. Tier 0 cash, Tier 1 floating-rate overnight repo, Tier 2 sovereign bonds and Tier 3 equities.
2. Separate market value, principal, realized/accrued earnings, unrealized P&L, liquidation proceeds and overdraft liabilities.
3. Repo entry at 17:00 and maturity at 08:00; original position terms and applicable fees must remain explicit.
4. Native hourly historical observations. Do not fabricate quarter-hour history or silently label timezone-unspecified source timestamps UTC.
5. Decimal-string market prices/rates where required, alongside integer-cent ledger amounts.
6. Multi-asset recommendations and independently confirmed execution statuses.
7. Asset-aware stress overlays separated from immutable source history, with unsupported controls disabled.
8. All Cash, Cash + Repo Rule, and Four-Tier Reserve Juggler comparisons driven by the backend benchmark engine.

The organizer PDF/CSV dimensions and instrument terms are reported by the handoffs; the actual organizer source files have not been independently inspected in this milestone.

## Blockers before F1

- Member 1's RJ-M1-06 four-tier quantitative contract and example forecast/risk/allocation/explanation output.
- Member 2's finalized OpenAPI and example dataset metadata, run creation/advance, portfolio/positions, execution, scenario and report payloads.
- Explicit source-time/timezone and precision conventions for historical replay, repo entry/maturity and market valuations.

Next task: F1 data models, precision-preserving formatting and additive adapter/mock changes against those agreed schemas. No F1 implementation is included in F0. Do not invent endpoints, official historical data, market prices or benchmark results while waiting for the contracts.
