# Member 2 integration — one canonical contract

The exact interface is [FOUR_TIER_HANDOFF.md](FOUR_TIER_HANDOFF.md). Import
PortfolioState, FourTierRecommendationRequest, FourTierDecisionResult and
recommend_portfolio_allocation from **treasury_intelligence.portfolio** or the
identical package-root exports. The function is contract-only and raises
NotImplementedError; no optimizer, fallback or execution is implemented.

The independent four_tier.py schemas from 974154e are retired, not adapted or
re-exported. Rebuild payloads against the canonical JSON schemas and updated
four_tier_request.json / four_tier_response.json fixtures. Preserve UUID position,
order and liability identities and run/dataset provenance. Source/history fixtures
retain the original Decimal values, hourly naive timestamps and supplied net flow.

Do not infer quantity-to-index conversion, half-up fill/accrual rounding or a
guaranteed equity return. Do not flatten loan liabilities into cash or charge paid
financing cost again. Paid/unpaid financing splits, supplied market values,
availability and all actual execution receipts are distinct. All proposed orders
remain NOT_EXECUTED, and actual financial movements belong to Member 2.

See [field-by-field resolutions](CONTRACT_RECONCILIATION.md) for every renamed,
removed or retained field from the concurrent commits. No persistence, API or
frontend code is modified by this contract reconciliation.
