# Member 1 release verification - RJ-M1-15

Readiness: **BLOCKED** for an unqualified single-contract integration release.
Canonical recommendation import and JSON consumption are verified. This status
reflects unresolved integration criteria, not a failed quantitative test or demo.
No production code, backend, database, API or frontend files changed in this task.

## Git and completed work

Verified branch: feat/treasury-intelligence. Remote:
https://github.com/deveshshuklaaa/reserve-juggler.git.
Starting tested engine commit: 14a8d72596047a652bd8d98b485da501c2539746.
Working tree was clean at start. After git fetch origin, HEAD and
origin/feat/treasury-intelligence matched (0 ahead / 0 behind).
History includes the audit, contracts, legacy financial math/forecast/decisions,
standalone pipeline, four-tier contracts, hourly forecasts, instrument economics,
ML evaluation, liquidity risk, optimizer, Monte Carlo risk, official-data demo and
RJ-M1-14 validation commits. Completed functionality/history was preserved.
The subsequent RJ-M1-15 commit contains documentation and illustrative JSON only;
its exact hash and remote match are reported after push rather than self-embedded.

## Actual verification results

| Check | Actual outcome |
| --- | --- |
| Full repository tests, including complete Member 1 suite | 428 passed in 36.94s |
| Official CSV standalone four-tier demonstration | All 4 scenarios passed |
| Full demo typed JSON round trip | Passed |
| Source row/field count | 8,760 rows, 16 source fields |
| Native time semantics | Every source timestamp naive; every consecutive interval exactly 3,600 seconds |
| CSV integrity before/after demonstration | Same SHA256 as original recorded source |
| Canonical request/result/risk JSON round trips | Passed |
| Canonical recommendation dispatcher | Same decision as implemented optimizer |
| Published example output | Regeneration exactly matches integration_response.json |
| Precision check | Decimal fields serialize as strings; cent target fields serialize as integers |
| Dependency isolation | Canonical example succeeds with sklearn/FastAPI/SQLAlchemy/httpx imports explicitly blocked |
| Completed ML measurements | Present in MODEL_EVALUATION_REPORT.md and RELEASE_RESULTS.json; not recomputed in this task |

Source SHA256:
2e7c1d2e5b678e9975250211e7e0017022049c510e1dd90cd7f29e931837b0c5

Source file used read-only:
C:\Users\Arvind Shekhawat\Downloads\treasury_4tier_dataset.csv.

Official-data scenario results: INVEST / HOLD / WARNING / HOLD. The 17:00 example
reserves 14,660,743,764 cents, recommends 25,339,256,236 cents of repo and estimates
1,853,583 cents interest. The outside-window example holds cash; the short-cash
example warns; the bond/equity shock example marks losses and haircut proceeds.
All recommendations remain NOT_EXECUTED. These are demonstrations, not measured
strategy returns. The new JSON wire example instead uses one illustrative nominal
scenario; its allocation must not be confused with the Monte Carlo demo results.

Full test command from repository root:

```powershell
$env:PYTHONPATH='.;backend'
$env:OMP_NUM_THREADS='1'
uv run --with pytest --with fastapi --with pydantic --with httpx --with sqlalchemy --with pydantic-settings --with scikit-learn pytest tests/ -q
```

Official-data demo invocation:

```python
from pathlib import Path
from treasury_intelligence.four_tier_demo import run_four_tier_demo
r = run_four_tier_demo(Path(r"C:\Users\Arvind Shekhawat\Downloads\treasury_4tier_dataset.csv"), limit=None)
assert r.all_passed
assert r.model_validate_json(r.model_dump_json()) == r
print(r.summary_report)
```

Measured ML net-MAE improvement over seasonal naive remains 1h +14.88%, 3h -9.83%,
6h +2.78%, 15h +17.12%, 24h +12.56%. These actual earlier results use a chronological
70/15/15 partition, seed 42 and stride 24 on all source rows. Metrics target
source deposits minus withdrawals, not independent net_flow_usd. Peak metric uses
hour-end netting, not the reserve engine's withdrawal-before-deposit timing.

## Integration blockers and dependency notes

1. portfolio.py is canonical, but overlapping four_tier.py schemas are still
   actively used by forecasting, ML, economics, demo and root exports. Those imports
   resolve; they are not missing modules. There is no single unified model family,
   and deleting compatibility code would break supported functionality.
2. Forecast metadata targets deposits_minus_withdrawals, while canonical metadata
   permits only source_net_flow_usd. The documented explicit point conversion works;
   an automatic metadata-preserving unified adapter is absent. The portfolio
   recommendation dispatcher also retains the old request annotation, despite
   supporting AllocationOptimizerRequest at runtime. Prefer the explicit typed
   optimizer entry point.
3. Dataset timezone/publication timing is unspecified. Member 2 must determine
   available information at each replay cutoff rather than infer full hourly flow
   availability from the row timestamp.
4. No canonical execution/backend or frontend wiring was found/certified. Member 2
   must own execution validation, cash legs, fills, accounting and persistence.
5. Core runtime needs treasury_intelligence/requirements.txt (Pydantic). Optional
   ML requires scikit-learn, not listed in core requirements. Test commands supply
   optional backend/test dependencies without making them engine dependencies.
6. Three legacy evaluation/scenario/allocation functions remain declared stubs;
   implemented modern equivalents and exact imports are in FOUR_TIER_HANDOFF.md.

Member 2: use FOUR_TIER_HANDOFF.md, MEMBER2_INTEGRATION.md, ENGINE_CONTRACT.md,
integration_request.json, integration_response.json and the complete package.
Member 3: use MEMBER3_FRONTEND_FIELDS.md and integration_response.json. Current
portfolio balances/marks are a separate snapshot; costs, targets, explanations and
execution status must retain their documented meanings. FINAL_AUDIT.md records
remaining statistical/search limitations. Do not merge into main/develop as part
of this verification.
