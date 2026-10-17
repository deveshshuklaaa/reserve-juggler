# Measured model evaluation ? RJ-M1-14

Actual evaluation on all 8,760 organizer hourly observations; no source data was modified.

HistGradientBoostingRegressor (seed 42), separate deposit/withdrawal estimators,
compared with 24-hour seasonal naive. Chronological partitions: 6,132 training
rows through 2026-09-13 11:00; 1,314 validation rows through 2026-11-07 05:00;
1,314 test-partition rows from 2026-11-07 06:00 through 2026-12-31 23:00.
The fitted artifact includes validation residual calibration and is first usable
after that calibration cutoff. Each algorithm is fitted once; 1,270 supervised
feature/target pairs across five horizons. Test origins advance 24 hours; realized
paths begin one hour after each origin. No test labels enter fitting/calibration.

Errors below are measured USD. Improvement is positive when ML error is lower.

| Horizon h | Test paths | ML net MAE | Baseline net MAE | MAE improvement % | ML net RMSE | Cumulative net MAE | Peak drain MAE |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 55 | 2137786.63 | 2511495.05 | 14.88 | 3057268.98 | 2137786.63 | 339668.44 |
| 3 | 55 | 2943170.44 | 2679713.37 | -9.83 | 3649718.36 | 8583333.3 | 729130.14 |
| 6 | 55 | 3238219.17 | 3330653.79 | 2.78 | 4523191.79 | 12806169.25 | 3340400.46 |
| 15 | 55 | 2398612.28 | 2894189.67 | 17.12 | 3617603.77 | 17607962.32 | 9558303.88 |
| 24 | 54 | 1982263.63 | 2267089.05 | 12.56 | 3105491.35 | 19522952.59 | 11894570.57 |

The 3-hour ML forecast is worse than baseline; do not claim universal improvement.
These metrics target deposits minus withdrawals, not the independent source
net_flow_usd field. Deposit/withdrawal MAE and additional baseline errors are in
RELEASE_RESULTS.json. Peak drain uses hour-end netting, not intrahour reserve
coverage or realized payout failure. Test paths can overlap under other stride
settings; this run uses stride 24 with horizons no longer than 24. It samples
origins at one fixed daily phase and is not exhaustive hour-by-hour evaluation.
No strategy profit, calibrated tail coverage, execution success or Sharpe ratio
has been measured or claimed. USD errors use floating-point model statistics
rounded to cents and serialized as Decimal strings.

Reproduce with run_release_validation.py using the command in FINAL_AUDIT.md.
Runtime packages: pydantic 2.13.4, scikit-learn 1.9.0.
Source SHA256 before and after: `2e7c1d2e5b678e9975250211e7e0017022049c510e1dd90cd7f29e931837b0c5`.

Actual four-tier demo: all four scenarios passed; the corrected seasonal timing
gives $146,607,437.64 reserve, $253,392,562.36 repo principal and $18,535.83
estimated overnight interest. Outside-window HOLD, shortage WARNING and the
observed-price/synthetic-shock mark-to-market example also pass. These are
illustrations with declared starting capital, not measured investment returns.
Both standalone demo outputs are recorded in RELEASE_DEMO_OUTPUT.txt.
