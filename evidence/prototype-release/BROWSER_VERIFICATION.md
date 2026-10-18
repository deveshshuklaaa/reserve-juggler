# Final built-client browser verification

Application checkpoint: 19a37fe2ed34a449272448ad141678ec80299608.
Backend: unchanged core 1d943eeb652775ef0aecb8cf73bd781293722d36.
Production Vite preview http://127.0.0.1:3017; actual Uvicorn on 8017;
PostgreSQL reserve_juggler_m2_test_release_d5c756fa6f29.
VITE_USE_MOCKS=false; badge “FastAPI mode” / “Backend backtesting.”

## Actual browser actions and result

1. Created a live simulation through the production UI; actual POST returned 201.
2. Earlier live command-center run 0ada2d26-67c5-4976-ad3f-f7cbd131991b
   advanced one hour, displaying recorded cash 1,785,840,948 cents and real
   deposit/withdrawal/decision rows. Screenshot frontend-live-step.png.
3. Selected Normal operations, seven days, all three strategies. Browser creation
   defaults seed 2026 and source start Oct 17 2026 08:00. Selected seed matched
   the actual parent, not an unsupported seed override.
4. After discovering the adapter fabricated zero sweep/debt fields, added a
   failing test, fixed mapping, rebuilt, RELOADED the final bundle and repeated
   this one browser path to verify that specific regression. No overlapping
   comparison requests or 14/30-day scenario matrices were launched.
5. Final parent 03a41867-5a8b-410f-83b3-55b389637d04, NORMAL, seed 2026,
   initial 2,000,000,000 cents, no scenario schedule. Parent duration 192, but
   endpoint's documented fallback comparison is SEVEN days / 168 hours:
   Oct 17 08:00 through Oct 24 08:00 EXCLUSIVE.
6. Actual POST /backtest returned 200; final browser displayed “COMPARISON
   COMPLETE,” “7-day treasury outcomes,” seed 2026, Normal operations,
   three strategies. Four financial columns/rows and real sampled history
   rendered. Model evaluation remained unavailable, not fabricated.
7. Final screenshot frontend-final-comparison.png and accessibility transcript
   frontend-final-browser.txt capture the completed result.
   Production main asset index-BXTN6JKM.js SHA256:
   c485e2c1e27f121ea3e31cb9f42ff14f8cceb79ed7921efa225b8f14db21fb7a.

Values actually visible in the final browser, INTEGER CENTS:

| Metric | STATIC | REACTIVE | RESERVE_JUGGLER |
| --- | ---: | ---: | ---: |
| realized_interest_cents | 33983 | 47300 | 61665 |
| average_checking_cents | 414319096 | 417236032 | 398885252 |
| penalties_cents | 15120954 | 0 | 0 |
| borrowing_costs_cents | 3680122 | 3677638 | 3677636 |
| borrowing_outstanding_cents | 1922501392 | 1907367121 | 1907352756 |
| reserve_breaches | 52 | 52 | 52 |
| emergency_events | 52 | 52 | 52 |
| failed_payouts | 8 | 8 | 8 |
| sweeps | 3 | 1 | 1 |
| net_benefit_cents | -18767093 | -3630338 | -3615971 |

The OLD client showed debt/sweeps as zero despite actual debt. The final client
correctly shows approximately $19m debt and 3/1/1 sweeps. It does not show a
zero-debt “success.” This was a real display defect, not a runtime fix.

These browser results use a DIFFERENT source window/seed (the same default policy) from the
retained Jan 1, seed-42 comparison in PROTOTYPE_RELEASE_HANDOFF.md. Do not
compare their numerical returns as if inputs matched. HTTP child runs are
ephemeral by contract; their IDs/ledgers are not claimed to remain committed.
Retained Jan 1 runs supply independently inspectable durable receipts/metrics.

## Evidence and limitations

The selected seven-day NORMAL browser path PASSED on the final production
client. Arbitrary dropdown changes, 14/30 days, stress-schedule labeling,
multiasset-specific frontend helpers, generic promotional claims and source-time
labels remain limitations described in the main handoff, NOT verified features.

The three-strategy browser path took minutes and completed within the corrected
five-minute timeout. The separately timed Jan 1 API comparison took about 171s.
No precise browser elapsed-time measurement is claimed.

Backend and frontend are intentionally left on local ports 8017 and 3017 for
prototype use; the original shared server on 8000 was not stopped or modified.
The disposable demo DB is retained. Nothing was pushed and main is untouched.
No RJ-M1-16 certification or broad historical-comparison release approval.

