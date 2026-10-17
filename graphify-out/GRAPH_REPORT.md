# Graph Report - reserve-juggler  (2026-10-18)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 1688 nodes · 4223 edges · 106 communities (85 shown, 21 thin omitted)
- Extraction: 94% EXTRACTED · 6% INFERRED · 0% AMBIGUOUS · INFERRED: 259 edges (avg confidence: 0.94)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `9e13c63b`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- run_service.py
- portfolio.py
- fixture
- test_four_tier_runtime.py
- monte_carlo_risk.py
- test_optimizer.py
- hourly_engine.py
- test_ml_forecasting.py
- demo.py
- four_tier.py
- test_instrument_economics.py
- test_decisions.py
- test_liquidity_risk.py
- test_persistence.py
- README.md
- simulate_multi_asset_monte_carlo_risk
- pipeline.py
- package.json
- treasury_intelligence/__init__.py
- MEMBER_2_SPEC.md
- test_forecasting.py
- treasury_adapter.py
- 30. BACKEND TESTING REQUIREMENTS
- test_organizer_data.py
- typing
- hourly_seasonal_naive_forecast
- test_strategy_dispatch_and_causality.py
- test_financial_math.py
- instrument_economics.py
- _search
- reserve_juggler_v1.simulation_runs
- persistence/models.py
- repositories.py
- schemas.py
- hourly_forecasting.py
- test_hourly_forecasting.py
- nonnegative_integer
- pytest
- treasury.py
- TreasuryDecisionEngine
- datetime
- CashFlowBucket
- field_validator
- organizer.py
- HourlyObservation
- evaluate_liquidity_risk
- 24. DATABASE DESIGN
- 42. FINAL DELIVERABLES
- test_api_versioning.py
- .load
- 31. FINANCIAL INVARIANTS
- 35. PARALLEL DEVELOPMENT RULES
- 40. JUDGE-READY TECHNICAL EXPLANATIONS
- OrganizerHourlyObservation
- recommend_four_tier_allocation
- HourlyCashFlowBucket
- GRAPHIFY — MANDATORY PROJECT KNOWLEDGE GRAPH
- 21. STRESS SCENARIO ENGINE
- 34. MEMBER 2 DEVELOPMENT TIMELINE
- 41. DEFINITION OF DONE
- http_error
- maximum_cumulative_shortfall
- advance_simulation_step
- 12. TRANSACTION DISTRIBUTION MODEL
- 23. FINANCIAL PERFORMANCE METRICS
- load_organizer_dataset
- GRAPHIFY — MANDATORY PROJECT KNOWLEDGE GRAPH
- OrganizerDatasetSource
- Four-tier persistence foundation (Milestone 2)
- 11. SYNTHETIC TRANSACTION GENERATOR
- 16. YIELD VAULT LEDGER
- 18. EMERGENCY LIQUIDITY AND PAYOUT FAILURES
- 22. STRATEGY BACKTESTING
- 26. API REQUEST AND RESPONSE EXAMPLES
- validate_hourly_forecast_inputs
- 19. SIMULATION STEP EXECUTION
- 37. EARLY HANDOFF TO MEMBER 1
- Organizer historical data foundation
- 15. CHECKING ACCOUNT LEDGER
- 17. EARLY VAULT REDEMPTION
- 20. INTEGRATION WITH MEMBER 1
- 28. BACKTEST IMPLEMENTATION DETAILS
- 29. FRONTEND INTEGRATION SUPPORT
- 2. PROJECT PROBLEM STATEMENT
- 6. YOUR EXACT RESPONSIBILITIES
- PULL_REQUEST_TEMPLATE.md
- VaultTerms
- GIT MILESTONE RULE — MANDATORY

## God Nodes (most connected - your core abstractions)
1. `Contract` - 44 edges
2. `fixture()` - 39 edges
3. `request()` - 38 edges
4. `ContractModel` - 35 edges
5. `optimize()` - 33 edges
6. `simulate_multi_asset_monte_carlo_risk()` - 32 edges
7. `decide()` - 30 edges
8. `FourTierContract` - 29 edges
9. `request()` - 28 edges
10. `CashFlowBucket` - 27 edges

## Surprising Connections (you probably didn't know these)
- `Schema, precision, and immutability` --references--> `HourlyObservation`  [INFERRED]
  docs/organizer-data.md → backend/app/data/organizer.py
- `Idempotency` --references--> `advance()`  [INFERRED]
  docs/MEMBER_2_SPEC.md → backend/app/routers/runs.py
- `Integrity and repository contract` --references--> `RunScopedRepository`  [INFERRED]
  docs/four-tier-persistence.md → backend/app/persistence/repositories.py
- `Provenance and diagnostics` --references--> `DatasetValidationError`  [INFERRED]
  docs/organizer-data.md → backend/app/data/organizer.py
- `Organizer treasury CSV (authoritative hourly source)` --configured_source_for--> `OrganizerDatasetSource`  [EXTRACTED]
  treasury_4tier_dataset.csv → backend/app/data/organizer.py

## Import Cycles
- None detected.

## Communities (106 total, 21 thin omitted)

### Community 0 - "run_service.py"
Cohesion: 0.05
Nodes (67): SimulationRun, advance(), backtest(), create_run(), decisions(), forecast(), history(), policy() (+59 more)

### Community 1 - "portfolio.py"
Cohesion: 0.07
Nodes (17): hydrate_portfolio_state(), hydrate_portfolio_state(), BondPosition, CashPosition, _check_times(), EquityPosition, MarketPosition, MarketPriceObservation (+9 more)

### Community 2 - "fixture"
Cohesion: 0.06
Nodes (35): raw_rows(), dataset(), pg_url(), dataset(), pg_url(), dataset(), pg_url(), test_all_financial_fields_reject_negative_values() (+27 more)

### Community 3 - "test_four_tier_runtime.py"
Cohesion: 0.06
Nodes (17): clean_database(), pg_engine(), session(), test_api_endpoint_simulation_step(), client(), override_get_db(), pg_engine(), test_accounting_identities() (+9 more)

### Community 4 - "monte_carlo_risk.py"
Cohesion: 0.11
Nodes (23): _calculate(), calculate_four_tier_liquidity_risk(), collect(), _ceil(), CommittedObligation, _cost(), _events(), FourTierLiquidityRiskRequest (+15 more)

### Community 5 - "test_optimizer.py"
Cohesion: 0.19
Nodes (38): asset(), optimize(), portfolio(), request(), test_all_four_tiers_can_be_recommended_in_one_constrained_plan(), test_bond_and_equity_exposure_caps_and_positive_quantities(), test_debt_repayment_is_compared_to_investing(), test_declared_bond_yield_never_automatically_becomes_a_coupon() (+30 more)

### Community 6 - "hourly_engine.py"
Cohesion: 0.11
Nodes (20): CashAccount, LiquidityBreach, OverdraftLiability, OverdraftMovement, PortfolioValuation, RepoPosition, SourceLinked, TreasuryDecision (+12 more)

### Community 7 - "test_ml_forecasting.py"
Cohesion: 0.10
Nodes (14): test_chronological_evaluation_framework_metrics(), test_comparison_of_two_lightweight_models(), test_extract_ml_features_timing_and_no_lookahead(), test_hourly_ml_forecast_result_contract(), test_market_data_visibility_isolated_at_as_of(), test_ml_forecast_fallback_when_untrained(), test_ml_model_fit_and_supported_horizons(), test_ml_model_save_and_load() (+6 more)

### Community 8 - "demo.py"
Cohesion: 0.15
Nodes (23): test_pipeline_cli_demo_execution(), test_pipeline_deterministic_reproducibility(), test_pipeline_high_withdrawal_stress(), test_pipeline_json_serialization_roundtrip(), test_pipeline_locked_vault_insufficient_liquidity(), test_pipeline_normal_operation(), test_pipeline_successful_hold(), test_pipeline_valid_safe_sweep() (+15 more)

### Community 9 - "four_tier.py"
Cohesion: 0.09
Nodes (19): _all_assets(), AllocationTarget, CostBreakdown, ExposureConstraint, FourTierContract, FourTierPortfolioState, FourTierRecommendationRequest, FourTierRiskPolicy (+11 more)

### Community 10 - "test_instrument_economics.py"
Cohesion: 0.12
Nodes (31): fixing(), portfolio(), repo(), round_trip(), test_actual_repo_maturity_and_fifteen_hour_interest(), test_bond_observed_price_gain_and_loss(), test_bond_yield_quote_and_duration_not_added_to_mark(), test_borrowed_cash_and_principal_liability_cancel_in_portfolio_value() (+23 more)

### Community 11 - "test_decisions.py"
Cohesion: 0.18
Nodes (34): decide(), forecast(), policy(), terms(), test_action_precedence_deficit_before_window_minimum_or_investment(), test_aggregate_cover_requires_separate_multi_vault_plan(), test_capped_below_minimum(), test_delayed_withdrawal_cannot_meet_immediate_deficit() (+26 more)

### Community 12 - "test_liquidity_risk.py"
Cohesion: 0.23
Nodes (34): calculate(), path(), policy(), request(), state(), test_adverse_outflows_monotonically_increase_reserve(), test_bond_equity_stress_and_liquidation_penalties(), test_booked_maturity_not_counted_again_and_duplicate_rejected() (+26 more)

### Community 13 - "test_persistence.py"
Cohesion: 0.12
Nodes (25): apply_migrations(), BondPosition, InvestmentMovement, LedgerEntry, RunScopedRepository, bond(), clean_database(), ledger() (+17 more)

### Community 14 - "README.md"
Cohesion: 0.06
Nodes (30): 1. Team Workstreams & Responsibilities, 2. Branching Strategy, 3. Engineering Philosophy & Guidelines, Feature Branch Lifecycle:, 1. Overview & Objective, 2.1. Expected Liquidity Requirement ($L_{req}$), 2.2. Forecast Uncertainty ($\sigma_{forecast}$), 2.3. Operational Safety Buffer ($B_{safety}$) (+22 more)

### Community 15 - "simulate_multi_asset_monte_carlo_risk"
Cohesion: 0.16
Nodes (21): make_forecast(), make_policy(), make_portfolio(), test_consistent_json_serialization(), test_correct_repo_cash_availability(), test_default_500_scenarios_and_runtime(), test_forced_liquidation_and_overdraft_costs(), test_higher_market_losses_reduce_portfolio_value() (+13 more)

### Community 16 - "pipeline.py"
Cohesion: 0.12
Nodes (14): early_redemption_penalty(), expected_net_economic_benefit(), _rate(), simple_annualized_vault_yield(), recommend_treasury_action(), penalty(), result(), TreasuryDecisionPolicy (+6 more)

### Community 17 - "package.json"
Cohesion: 0.10
Nodes (25): dependencies, react, react-dom, devDependencies, vite, @vitejs/plugin-react, name, private (+17 more)

### Community 18 - "treasury_intelligence/__init__.py"
Cohesion: 0.13
Nodes (13): evaluate_allocation_candidates(), evaluate_forecasting_models(), generate_risk_scenarios(), HourlyModelEvaluationReport, MarketRiskSummary, PercentileSummary, PortfolioDownsideRiskSummary, ShortfallDistributionSummary (+5 more)

### Community 19 - "MEMBER_2_SPEC.md"
Cohesion: 0.07
Nodes (27): 10. SIMULATION INITIALIZATION, 13. HISTORICAL DATA GENERATION, 14. REAL-TIME TRANSACTION AGGREGATOR, 1. YOUR ROLE AND MISSION, 25. FASTAPI CONTRACT, 27. API ERROR HANDLING, 32. DOCKER AND ENVIRONMENT MANAGEMENT, 33. PERFORMANCE REQUIREMENTS (+19 more)

### Community 20 - "test_forecasting.py"
Cohesion: 0.12
Nodes (16): make_history(), test_calendar_features_causal(), test_causality_and_input_validation(), test_correct_lag_alignment(), test_feature_matrix_generation(), test_forecast_horizons_1_2_4_96(), test_json_serialization_roundtrip(), test_nonnegative_predicted_inflow_outflow() (+8 more)

### Community 21 - "treasury_adapter.py"
Cohesion: 0.12
Nodes (9): build_four_tier_policy(), evaluate_liquidity_risk(), get_hourly_forecasts_from_db(), get_information_cutoff(), build_four_tier_policy(), test_calibration_artifacts_after_cutoff_rejected(), test_forecast_causal_invariance(), CalibratedForecastAllowance (+1 more)

### Community 22 - "30. BACKEND TESTING REQUIREMENTS"
Cohesion: 0.08
Nodes (26): 30. BACKEND TESTING REQUIREMENTS, Test 10 — Emergency borrowing, Test 11 — Payout failure, Test 12 — Normal scenario, Test 13 — High withdrawal scenario, Test 14 — Low deposit scenario, Test 15 — Settlement delay, Test 16 — Liquidity shock (+18 more)

### Community 23 - "test_organizer_data.py"
Cohesion: 0.12
Nodes (16): DatasetValidationError, dataset(), test_content_hash_changes_when_bytes_change(), test_dataset_validation_rejects_invalid_records(), test_exact_diagnostics_under_low_decimal_context(), test_fractional_bps_and_high_precision_are_preserved(), test_invalid_boolean_flags(), test_invalid_financial_domains() (+8 more)

### Community 24 - "typing"
Cohesion: 0.12
Nodes (4): get_db(), root(), get_health(), get_recent_transactions()

### Community 25 - "hourly_seasonal_naive_forecast"
Cohesion: 0.12
Nodes (12): test_hourly_forecast_result_serialization_and_immutability(), test_safe_fallback_empty_history(), test_safe_fallback_short_history_below_seasonal_cycle(), test_seasonal_naive_matches_previous_day_hour(), test_supported_hourly_horizons_path_completeness(), test_ml_forecast_fallback_when_none_model(), ForecastRiskMetadata, HourlyForecastPoint (+4 more)

### Community 26 - "test_strategy_dispatch_and_causality.py"
Cohesion: 0.11
Nodes (10): _create_test_run(), dataset(), pg_engine(), pg_url(), session(), test_accounting_invariants_and_sweep_across_strategies(), test_future_dated_inputs_excluded_and_rejected(), test_strategy_dispatch_policy_paths() (+2 more)

### Community 27 - "test_financial_math.py"
Cohesion: 0.17
Nodes (16): context(), maturity(), path(), test_booked_maturity_is_not_counted_again(), test_fourteen_million_reserve(), test_frozen_reserve_api_rounds_up_and_uses_path(), test_invalid_maturity_schedule(), test_invalid_money() (+8 more)

### Community 28 - "instrument_economics.py"
Cohesion: 0.18
Nodes (16): AnnualRateFixing, calculate_overdraft_economics(), calculate_portfolio_values(), calculate_repo_economics(), DurationSensitivityResult, EconomicsResult, EquityRiskResult, _floating_interest() (+8 more)

### Community 29 - "_search"
Cohesion: 0.16
Nodes (17): CandidateAssessment, _ceil(), _fee(), _floor(), _Plan, _search(), assess(), buy() (+9 more)

### Community 30 - "reserve_juggler_v1.simulation_runs"
Cohesion: 0.24
Nodes (23): 003: four-tier persistence (storage only), reserve_juggler_v1.backtest_results, reserve_juggler_v1.bond_positions, reserve_juggler_v1.cash_accounts, reserve_juggler_v1.dataset_sources, reserve_juggler_v1.equity_positions, reserve_juggler_v1.forecasts, reserve_juggler_v1.investment_movements (+15 more)

### Community 31 - "persistence/models.py"
Cohesion: 0.13
Nodes (14): Cents, EquityPosition, exact(), ExactNumeric, market_args(), MarketPosition, money(), position_args() (+6 more)

### Community 32 - "repositories.py"
Cohesion: 0.13
Nodes (11): DatasetSource, OrganizerObservation, configuration_identity(), DatasetRepository, RunRepository, Integrity and repository contract, test_internal_errors_use_safe_envelope(), historical_run() (+3 more)

### Community 33 - "schemas.py"
Cohesion: 0.17
Nodes (16): get_simulation_results(), start_simulation(), update_scenario(), Decision, Forecast, ForecastBase, HealthStatus, LiquiditySnapshot (+8 more)

### Community 34 - "hourly_forecasting.py"
Cohesion: 0.17
Nodes (6): build_hourly_feature_matrix(), compute_hourly_lag_features(), compute_hourly_rolling_features(), _extract_amounts(), extract_hourly_calendar_features(), ForecastResolution

### Community 35 - "test_hourly_forecasting.py"
Cohesion: 0.15
Nodes (15): test_15_hour_overnight_repo_horizon(), test_24_hour_daily_cycle_horizon(), test_baseline_reproducibility(), test_build_hourly_feature_matrix_shapes_and_values(), test_causal_rolling_features_and_volatility(), test_correct_hourly_lag_alignment_and_named_aliases(), test_extract_hourly_calendar_features(), test_full_downloads_dataset_if_present() (+7 more)

### Community 36 - "nonnegative_integer"
Cohesion: 0.25
Nodes (12): calculate_bond_economics(), calculate_duration_sensitivity(), calculate_equity_economics(), calculate_equity_risk(), calculate_index_acquisition(), _dec(), _market_economics(), MarketEconomicsResult (+4 more)

### Community 37 - "pytest"
Cohesion: 0.17
Nodes (4): CashFlowForecaster, test_forecaster_baseline(), test_forecaster_with_transactions(), test_end_to_end_pipeline()

### Community 38 - "treasury.py"
Cohesion: 0.33
Nodes (11): DecisionModel, ForecastModel, LiquiditySnapshotModel, SimulationRunModel, TransactionModel, get_current_forecast(), get_current_liquidity(), get_decisions_history() (+3 more)

### Community 39 - "TreasuryDecisionEngine"
Cohesion: 0.19
Nodes (6): TreasuryDecisionEngine, test_hold_decision_in_corridor(), test_liquidity_warning_on_extreme_insolvency(), test_required_reserve_calculation(), test_sweep_decision_on_excess_cash(), test_withdraw_decision_on_liquidity_deficit()

### Community 40 - "datetime"
Cohesion: 0.18
Nodes (4): TransactionGenerator, test_generator_baseline_event(), test_generator_deposit_run(), test_generator_payroll_spike()

### Community 41 - "CashFlowBucket"
Cohesion: 0.30
Nodes (8): test_preservation_of_15_minute_synthetic_mode(), forecast_cashflows(), rolling_mean_forecast(), seasonal_naive_forecast(), validate_forecast_inputs(), CashFlowBucket, ForecastPoint, ForecastResult

### Community 42 - "field_validator"
Cohesion: 0.14
Nodes (3): ForecastRiskMetadata, FourTierRecommendationRequest, OrganizerHourlyObservation

### Community 43 - "organizer.py"
Cohesion: 0.20
Nodes (4): _configured_path(), _exact_difference(), _exact_total(), Provenance and diagnostics

### Community 44 - "HourlyObservation"
Cohesion: 0.20
Nodes (3): HourlyObservation, OrganizerDataset, Historical replay (planned, NOT implemented)

### Community 45 - "evaluate_liquidity_risk"
Cohesion: 0.20
Nodes (3): evaluate_liquidity_risk(), generate_hourly_forecast_points(), get_information_cutoff()

### Community 46 - "24. DATABASE DESIGN"
Cohesion: 0.17
Nodes (12): 24. DATABASE DESIGN, Database requirements, Table 10 — backtest_results, Table 1 — simulation_runs, Table 2 — transactions, Table 3 — ledger_entries, Table 4 — vault_positions, Table 5 — vault_movements (+4 more)

### Community 47 - "42. FINAL DELIVERABLES"
Cohesion: 0.17
Nodes (12): 42. FINAL DELIVERABLES, A. Implementation summary, B. Database schema, C. Backend API documentation, D. Transaction simulator documentation, E. Ledger documentation, F. Backtesting documentation, G. Integration instructions for Member 1 (+4 more)

### Community 48 - "test_api_versioning.py"
Cohesion: 0.20
Nodes (4): test_backtest_routes_return_honest_unimplemented_error(), test_create_request_rejects_incompatible_units_or_values(), test_implemented_routes_return_not_found_for_missing_run(), test_spec_defaults_and_utc_normalization()

### Community 49 - ".load"
Cohesion: 0.24
Nodes (6): DatasetMetadata, DatasetValidation, FrozenModel, ReconciliationSummary, ValidationIssue, Organizer treasury CSV (authoritative hourly source)

### Community 50 - "31. FINANCIAL INVARIANTS"
Cohesion: 0.18
Nodes (11): 31. FINANCIAL INVARIANTS, Invariant 10 — Strategy isolation, Invariant 1 — Principal conservation, Invariant 2 — Interest accounting, Invariant 3 — No double execution, Invariant 4 — No free liquidity, Invariant 5 — Honest payout status, Invariant 6 — Accurate borrowing costs (+3 more)

### Community 51 - "35. PARALLEL DEVELOPMENT RULES"
Cohesion: 0.18
Nodes (11): 35. PARALLEL DEVELOPMENT RULES, Rule 1, Rule 10, Rule 2, Rule 3, Rule 4, Rule 5, Rule 6 (+3 more)

### Community 52 - "40. JUDGE-READY TECHNICAL EXPLANATIONS"
Cohesion: 0.18
Nodes (11): 40. JUDGE-READY TECHNICAL EXPLANATIONS, Are these actual bank transactions?, How are transactions generated?, How do you compare against baselines?, How do you measure financial performance?, How do you prevent misleading results?, How does the system simulate real time?, How is a sweep executed? (+3 more)

### Community 53 - "OrganizerHourlyObservation"
Cohesion: 0.20
Nodes (3): InstrumentReturnEstimate, OrganizerHourlyObservation, TradeRecommendation

### Community 54 - "recommend_four_tier_allocation"
Cohesion: 0.20
Nodes (5): AllocationOptimizerResult, recommend_four_tier_allocation(), collect(), FourTierDecisionResult, recommend_portfolio_allocation()

### Community 55 - "HourlyCashFlowBucket"
Cohesion: 0.20
Nodes (5): test_hourly_cashflow_bucket_from_observation(), test_hourly_cashflow_bucket_model(), test_single_observation_history_rolling_mean(), test_ml_forecast_fallback_when_insufficient_history(), HourlyCashFlowBucket

### Community 56 - "GRAPHIFY — MANDATORY PROJECT KNOWLEDGE GRAPH"
Cohesion: 0.22
Nodes (8): GIT MILESTONE RULE — MANDATORY, Graphify accuracy rule, GRAPHIFY — MANDATORY PROJECT KNOWLEDGE GRAPH, Important, Initial setup, Milestone examples, Project Rules and Guidelines, Regular updates

### Community 57 - "21. STRESS SCENARIO ENGINE"
Cohesion: 0.22
Nodes (9): 21. STRESS SCENARIO ENGINE, HIGH_WITHDRAWAL, LIQUIDITY_SHOCK, LOW_DEPOSIT, Mid-run scenario application, NORMAL, Scenario implementation rule, SETTLEMENT_DELAY (+1 more)

### Community 58 - "34. MEMBER 2 DEVELOPMENT TIMELINE"
Cohesion: 0.22
Nodes (9): 34. MEMBER 2 DEVELOPMENT TIMELINE, Hours 0–1 — Contract and Repository Setup, Hours 10–14 — Backtesting and Member 1 Integration, Hours 14–18 — Advanced Metrics and Reliability, Hours 18–21 — Final Integration, Hours 1–4 — Transaction and Ledger Foundation, Hours 21–24 — Feature Freeze, Hours 4–7 — Simulation and API (+1 more)

### Community 59 - "41. DEFINITION OF DONE"
Cohesion: 0.22
Nodes (9): 41. DEFINITION OF DONE, API, Database, Evaluation, Integration, Simulation engine, Stress testing, Transaction engine (+1 more)

### Community 60 - "http_error"
Cohesion: 0.32
Nodes (3): http_error(), unexpected_error(), validation_error()

### Community 61 - "maximum_cumulative_shortfall"
Cohesion: 0.29
Nodes (3): known_vault_maturities(), maximum_cumulative_shortfall(), VaultMaturity

### Community 63 - "advance_simulation_step"
Cohesion: 0.29
Nodes (3): advance_simulation_step(), StepRequest, StepResponse

### Community 64 - "12. TRANSACTION DISTRIBUTION MODEL"
Cohesion: 0.29
Nodes (7): 12. TRANSACTION DISTRIBUTION MODEL, Deposit distribution, Merchant settlements, Randomness, Time-of-day behavior, Transaction volume, Withdrawal distribution

### Community 65 - "23. FINANCIAL PERFORMANCE METRICS"
Cohesion: 0.29
Nodes (7): 23. FINANCIAL PERFORMANCE METRICS, Baseline comparison, Core financial metric, Liquidity metrics, Transaction metrics, Treasury activity metrics, Yield metrics

### Community 66 - "load_organizer_dataset"
Cohesion: 0.29
Nodes (3): test_load_organizer_dataset_from_fixture_and_limits(), test_full_dataset_ml_evaluation_if_present(), load_organizer_dataset()

### Community 67 - "GRAPHIFY — MANDATORY PROJECT KNOWLEDGE GRAPH"
Cohesion: 0.33
Nodes (5): Graphify accuracy rule, GRAPHIFY — MANDATORY PROJECT KNOWLEDGE GRAPH, Important, Initial setup, Regular updates

### Community 68 - "OrganizerDatasetSource"
Cohesion: 0.33
Nodes (4): Settings, OrganizerDatasetSource, test_environment_configuration(), write()

### Community 69 - "Four-tier persistence foundation (Milestone 2)"
Cohesion: 0.33
Nodes (5): Applying and verifying migrations, Authoritative storage, Deliberate boundaries / remaining contracts, Four-tier persistence foundation (Milestone 2), Precision and time

### Community 70 - "11. SYNTHETIC TRANSACTION GENERATOR"
Cohesion: 0.33
Nodes (6): 11. SYNTHETIC TRANSACTION GENERATOR, A. DEPOSIT, B. WITHDRAWAL, C. MERCHANT_SETTLEMENT, Required behavior, Required transaction fields

### Community 71 - "16. YIELD VAULT LEDGER"
Cohesion: 0.33
Nodes (6): 16. YIELD VAULT LEDGER, Creating a vault position, Interest accounting, Interest calculation, Maturity processing, Required position fields

### Community 72 - "18. EMERGENCY LIQUIDITY AND PAYOUT FAILURES"
Cohesion: 0.33
Nodes (6): 18. EMERGENCY LIQUIDITY AND PAYOUT FAILURES, Emergency borrowing configuration, Important metrics, Scenario A — Sufficient checking, Scenario B — Checking insufficient, emergency borrowing allowed, Scenario C — Funding unavailable

### Community 73 - "22. STRATEGY BACKTESTING"
Cohesion: 0.33
Nodes (6): 22. STRATEGY BACKTESTING, Critical fairness rule, Recommended implementation, Strategy A — STATIC RESERVE, Strategy B — REACTIVE RESERVE, Strategy C — RESERVE JUGGLER

### Community 74 - "26. API REQUEST AND RESPONSE EXAMPLES"
Cohesion: 0.33
Nodes (6): 26. API REQUEST AND RESPONSE EXAMPLES, A. Create Simulation, B. Advance Simulation, C. Apply Scenario, D. Treasury Snapshot, E. Backtest Result

### Community 76 - "19. SIMULATION STEP EXECUTION"
Cohesion: 0.40
Nodes (5): 19. SIMULATION STEP EXECUTION, Idempotency, Important financial detail, Important policy detail, Required execution sequence

### Community 77 - "37. EARLY HANDOFF TO MEMBER 1"
Cohesion: 0.40
Nodes (5): 37. EARLY HANDOFF TO MEMBER 1, Configurable policy, Execution feedback, Historical data, Treasury context

### Community 78 - "Organizer historical data foundation"
Cohesion: 0.40
Nodes (4): Current source identity, Organizer historical data foundation, Read and validate, Schema, precision, and immutability

### Community 79 - "15. CHECKING ACCOUNT LEDGER"
Cohesion: 0.50
Nodes (4): 15. CHECKING ACCOUNT LEDGER, Concurrency safety, Financial correctness, Required ledger entry information

### Community 80 - "17. EARLY VAULT REDEMPTION"
Cohesion: 0.50
Nodes (4): 17. EARLY VAULT REDEMPTION, Configurable parameters, Early redemption sequence, Important rule

### Community 81 - "20. INTEGRATION WITH MEMBER 1"
Cohesion: 0.50
Nodes (4): 20. INTEGRATION WITH MEMBER 1, Create a treasury adapter, Fallback implementation, Final integration

### Community 82 - "28. BACKTEST IMPLEMENTATION DETAILS"
Cohesion: 0.50
Nodes (4): 28. BACKTEST IMPLEMENTATION DETAILS, Backtesting outputs, Fair comparison, No lookahead

### Community 83 - "29. FRONTEND INTEGRATION SUPPORT"
Cohesion: 0.50
Nodes (4): 29. FRONTEND INTEGRATION SUPPORT, Early deliverable, Integration strategy, Live dashboard updates

### Community 84 - "2. PROJECT PROBLEM STATEMENT"
Cohesion: 0.50
Nodes (4): 2. PROJECT PROBLEM STATEMENT, Checking Account, Financial Problem, Yield Vault

### Community 85 - "6. YOUR EXACT RESPONSIBILITIES"
Cohesion: 0.50
Nodes (4): 6. YOUR EXACT RESPONSIBILITIES, P0 — Mandatory Features, P1 — Competitive Enhancements, P2 — Only After P0 and P1 Are Stable

### Community 86 - "PULL_REQUEST_TEMPLATE.md"
Cohesion: 0.50
Nodes (3): 1. Workstream Area, 2. Changes Summary, 3. Verification Checklist

## Knowledge Gaps
- **247 isolated node(s):** `Authority and scope`, `Contract decisions requiring team review`, `Member 1 integration placeholder — NOT AN AGREED ENGINE CONTRACT`, `Shared financial and data conventions`, `Verification limits` (+242 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 609 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **21 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `main()` connect `README.md` to `test_four_tier_runtime.py`?**
  _High betweenness centrality (0.199) - this node is a cross-community bridge._
- **Why does `5. EXISTING PROJECT ENVIRONMENT` connect `README.md` to `MEMBER_2_SPEC.md`?**
  _High betweenness centrality (0.182) - this node is a cross-community bridge._
- **Why does `30. BACKEND TESTING REQUIREMENTS` connect `30. BACKEND TESTING REQUIREMENTS` to `MEMBER_2_SPEC.md`?**
  _High betweenness centrality (0.033) - this node is a cross-community bridge._
- **Are the 3 inferred relationships involving `Contract` (e.g. with `FourTierRecommendationRequest` and `OrganizerHourlyObservation`) actually correct?**
  _`Contract` has 3 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Authority and scope`, `Contract decisions requiring team review`, `Member 1 integration placeholder — NOT AN AGREED ENGINE CONTRACT` to the rest of the system?**
  _247 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `run_service.py` be split into smaller, more focused modules?**
  _Cohesion score 0.05219538000352671 - nodes in this community are weakly interconnected._
- **Should `portfolio.py` be split into smaller, more focused modules?**
  _Cohesion score 0.07138047138047138 - nodes in this community are weakly interconnected._