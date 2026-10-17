# Quantitative engine testing report — RJ-M1-14

Branch: feat/treasury-intelligence. Baseline reviewed:
ad5e42ad9ad7b552d2c1aa7694ba354cabf79e95. Final code and regression tests were
validated before the release commit; no other member's files were changed.

| Check | Actual result |
| --- | --- |
| Original full tests/ baseline | 416 passed in 36.44s |
| Forecast/ML/Monte Carlo/demo targeted suite after timing fixes | 73 passed in 34.65s |
| Full tests/ after final financial fixes | 428 passed in 36.23s |
| Explicit fitted-cutoff + unpaid-liability regressions | 2 passed in 1.79s |
| Full-source chronological ML evaluation | Completed; 5 measured horizon reports, seed 42, 8,760 source rows |
| Legacy standalone demo | Completed; HOLD, SWEEP, WITHDRAW and LIQUIDITY_WARNING examples |
| Four-tier standalone demo | All 4 scenarios passed; typed nested JSON round trips passed |
| Source CSV fingerprint | Before/after and final SHA256 unchanged |
| git diff --check | Passed; only normal Windows LF/CRLF notices |
| Remote synchronization before commit | HEAD and origin/feat/treasury-intelligence equal (0 ahead / 0 behind) |

Full-suite command (repository root, PowerShell):

```powershell
$env:PYTHONPATH='.;backend'
$env:OMP_NUM_THREADS='1'
uv run --with pytest --with fastapi --with pydantic --with httpx --with sqlalchemy --with pydantic-settings --with scikit-learn pytest tests/ -q
```

The full suite covers legacy contracts, cent/bps/UTC interfaces, peak shortfall,
reserve rounding, financial economics, baseline features, decision precedence,
canonical four-tier contracts, hourly forecasting, chronological ML evaluation,
repo/bond/equity/overdraft economics, liquidity timing/scenarios, optimizer cash
and exposure constraints, Monte Carlo reproducibility and demo serialization.
All 416 original tests remain passing; the audit adds 12 regression cases.

New regression coverage: exact probability weights for 3 and 7 samples; missing
bootstrap hour rejection; endpoint cash versus peak demand; sale asset conservation;
repo maturity asset removal; first one-hour market innovation; existing debt cost;
ML artifact calibration availability and invalid start time; explicit ML seasonal
feature timing/future-row rejection; baseline target-time alignment/gap rejection;
no demo YTM cash income; unpaid financing included in demo liabilities.

Measured errors, package versions, configuration and source fingerprint are in
RELEASE_RESULTS.json and MODEL_EVALUATION_REPORT.md. Both standalone demonstrations
were run by docs/member1/run_release_validation.py against the complete source CSV;
RELEASE_DEMO_OUTPUT.txt records actual stdout. Its full evaluation was rerun after
seasonal timing corrections. Demonstration calculations are not strategy returns.

Source SHA256:
2e7c1d2e5b678e9975250211e7e0017022049c510e1dd90cd7f29e931837b0c5

Scope limits: the external CSV is available on this machine; optional dataset tests
may skip on machines without it. ML needs optional scikit-learn. No API/database,
execution-ledger, frontend, deployment, or real payout test is claimed. Remaining
integration blockers and statistical limitations are explicitly in FINAL_AUDIT.md.
