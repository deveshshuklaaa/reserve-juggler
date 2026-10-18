# Graph Report - reserve-juggler  (2026-10-18)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 2160 nodes · 5948 edges · 123 communities (99 shown, 24 thin omitted)
- Extraction: 88% EXTRACTED · 12% INFERRED · 0% AMBIGUOUS · INFERRED: 722 edges (avg confidence: 0.94)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `43c275c3`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- typing
- treasury_adapter.py
- persistence/models.py
- os
- hourly_forecasting.py
- test_ml_forecasting.py
- test_checkpoint_verification.py
- Quantitative engine contract v1
- Independent checkpoint verification — dee0aae (2026-10-18)
- execute_hourly_step
- treasury_intelligence/__init__.py
- demo.py
- test_service.py
- four_tier.py
- optimizer.py
- test_runtime_persistence.py
- instrument_economics.py
- test_optimizer.py
- reports.py
- fixture
- test_hourly_forecasting.py
- test_instrument_economics.py
- service.py
- test_decisions.py
- package.json
- test_liquidity_risk.py
- monte_carlo_risk.py
- README.md
- protocol.py
- run_service.py
- test_persistence.py
- MEMBER_2_SPEC.md
- simulate_multi_asset_monte_carlo_risk
- v1_contracts.py
- test_forecasting.py
- 30. BACKEND TESTING REQUIREMENTS
- Contract
- repositories.py
- test_organizer_data.py
- test_financial_math.py
- test_execution_receipt_adapter.py
- reserve_juggler_v1.simulation_runs
- organizer.py
- TransactionGenerator
- OrganizerObservation
- runs.py
- test_four_tier_runtime.py
- Organizer historical data foundation
- treasury.py
- HourlyCashFlowBucket
- schemas.py
- TreasuryDecisionEngine
- CashFlowBucket
- test_strategy_dispatch_and_causality.py
- SimulationRun
- datetime
- RecommendedOrder
- treasury_intelligence/test_contracts.py
- recommend_four_tier_allocation
- 24. DATABASE DESIGN
- 42. FINAL DELIVERABLES
- test_api_versioning.py
- HourlyObservation
- Reserve Juggler backend and engine integration contract
- OrganizerDataset
- reserve_for_path
- Task Log
- Repository Audit & Workstream Specification — Member 1
- 31. FINANCIAL INVARIANTS
- 35. PARALLEL DEVELOPMENT RULES
- 40. JUDGE-READY TECHNICAL EXPLANATIONS
- TreasuryPolicy
- GRAPHIFY — MANDATORY PROJECT KNOWLEDGE GRAPH
- 21. STRESS SCENARIO ENGINE
- 34. MEMBER 2 DEVELOPMENT TIMELINE
- 41. DEFINITION OF DONE
- HourlyForecastResult
- http_error
- .net_flow_residual_usd
- advance_simulation_step
- 12. TRANSACTION DISTRIBUTION MODEL
- test_runs_runtime.py
- 23. FINANCIAL PERFORMANCE METRICS
- Core runtime release checkpoints
- load_organizer_dataset
- GRAPHIFY — MANDATORY PROJECT KNOWLEDGE GRAPH
- start_simulation
- 11. SYNTHETIC TRANSACTION GENERATOR
- 16. YIELD VAULT LEDGER
- 18. EMERGENCY LIQUIDITY AND PAYOUT FAILURES
- 22. STRATEGY BACKTESTING
- 26. API REQUEST AND RESPONSE EXAMPLES
- 19. SIMULATION STEP EXECUTION
- 37. EARLY HANDOFF TO MEMBER 1
- StepConflictError
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
- HourlyForecastConfig
- AssetRewardAssumption

## God Nodes (most connected - your core abstractions)
1. `execute_hourly_step()` - 64 edges
2. `SimulationRun` - 57 edges
3. `fixture()` - 53 edges
4. `OrganizerObservation` - 51 edges
5. `Contract` - 44 edges
6. `create_run()` - 39 edges
7. `request()` - 38 edges
8. `LedgerEntry` - 36 edges
9. `CashAccount` - 36 edges
10. `BondPosition` - 36 edges

## Surprising Connections (you probably didn't know these)
- `Schema, precision, and immutability` --references--> `HourlyObservation`  [INFERRED]
  docs/organizer-data.md → backend/app/data/organizer.py
- `Idempotency` --references--> `advance()`  [INFERRED]
  docs/MEMBER_2_SPEC.md → backend/app/routers/runs.py
- `RJ-M1-04 Treasury decisions` --references--> `VaultTerms`  [INFERRED]
  docs/member1/ENGINE_CONTRACT.md → treasury_intelligence/policy.py
- `Provenance and diagnostics` --references--> `DatasetValidationError`  [INFERRED]
  docs/organizer-data.md → backend/app/data/organizer.py
- `Organizer treasury CSV (authoritative hourly source)` --configured_source_for--> `OrganizerDatasetSource`  [EXTRACTED]
  treasury_4tier_dataset.csv → backend/app/data/organizer.py

## Import Cycles
- None detected.

## Communities (123 total, 24 thin omitted)

### Community 0 - "typing"
Cohesion: 0.13
Nodes (4): get_db(), root(), get_health(), get_recent_transactions()

### Community 1 - "treasury_adapter.py"
Cohesion: 0.07
Nodes (33): evaluate_liquidity_risk(), hydrate_portfolio_state(), recommend_four_tier_allocation_decision(), build_four_tier_policy(), evaluate_liquidity_risk(), generate_hourly_forecast_points(), get_information_cutoff(), hydrate_portfolio_state() (+25 more)

### Community 2 - "persistence/models.py"
Cohesion: 0.07
Nodes (42): execute_persisted_hour(), read_hour_receipt(), _rows(), RuntimeReceiptUnavailable, _state(), _valuation(), CashAccount, Cents (+34 more)

### Community 3 - "os"
Cohesion: 0.12
Nodes (3): Settings, main(), main()

### Community 4 - "hourly_forecasting.py"
Cohesion: 0.13
Nodes (9): [RJ-M1-07] Official Hourly Forecast Foundation, test_build_hourly_feature_matrix_shapes_and_values(), test_causal_rolling_features_and_volatility(), build_hourly_feature_matrix(), compute_hourly_lag_features(), compute_hourly_rolling_features(), _extract_amounts(), extract_hourly_calendar_features() (+1 more)

### Community 5 - "test_ml_forecasting.py"
Cohesion: 0.09
Nodes (21): Chronological Evaluation and Metrics Report, [RJ-M1-09] Hourly ML Forecasting and Evaluation, test_chronological_evaluation_framework_metrics(), test_comparison_of_two_lightweight_models(), test_extract_ml_features_timing_and_no_lookahead(), test_forecast_hourly_cashflows_with_ml_model(), test_hourly_ml_forecast_result_contract(), test_market_data_visibility_isolated_at_as_of() (+13 more)

### Community 6 - "test_checkpoint_verification.py"
Cohesion: 0.08
Nodes (24): HourReceipt, ScenarioSpec, DecisionFrame, ExecutionFrame, HourlyRun, RunSpec, make_shared_runtime_factory(), PersistedHourlyRun (+16 more)

### Community 7 - "Quantitative engine contract v1"
Cohesion: 0.04
Nodes (45): Pre-RJ-M1-10 canonical contract check, Public interface differences, Safe outcome and unresolved work, Verified Git state, Additive recommendation interface, Baseline Behavior and Fallback Governance, Bonds and equity, Canonical boundary and integration (+37 more)

### Community 8 - "Independent checkpoint verification — dee0aae (2026-10-18)"
Cohesion: 0.04
Nodes (47): 1. Integration contract: Conservative historical-data availability, 3. Verification evidence against exact checkpoint `43c275c3efaf7ed986d92d732c55583f096ccadf`, 4. Acceptance checklist and release gating, API and orchestration acceptance, Authorized runtime/API ownership checkpoint (2026-10-18), Calling interface, Canonical optimizer verification, Configure BACKTEST_TEST_DATABASE_URL with your local test credentials. (+39 more)

### Community 9 - "execute_hourly_step"
Cohesion: 0.11
Nodes (21): BondPosition, InvestmentMovement, LedgerEntry, TreasuryDecision, market_cost_basis(), paid_financing_costs(), repo_hourly_rates(), repo_interest_cents() (+13 more)

### Community 10 - "treasury_intelligence/__init__.py"
Cohesion: 0.12
Nodes (26): [RJ-M1-12] Multi-Asset Monte Carlo Risk, evaluate_allocation_candidates(), evaluate_forecasting_models(), generate_risk_scenarios(), early_redemption_penalty(), expected_net_economic_benefit(), _rate(), simple_annualized_vault_yield() (+18 more)

### Community 11 - "demo.py"
Cohesion: 0.13
Nodes (25): [RJ-M1-05] Standalone Treasury Decision Pipeline and Demo, test_pipeline_cli_demo_execution(), test_pipeline_deterministic_reproducibility(), test_pipeline_high_withdrawal_stress(), test_pipeline_json_serialization_roundtrip(), test_pipeline_locked_vault_insufficient_liquidity(), test_pipeline_normal_operation(), test_pipeline_successful_hold() (+17 more)

### Community 12 - "test_service.py"
Cohesion: 0.12
Nodes (33): BacktestRequest, journal(), ScriptedFactory, evaluate(), test_actual_reported_accounting_not_cash_profit(), test_average_rounding_is_metric_only_half_up(), hook(), test_bad_receipts_fail_and_close_resources() (+25 more)

### Community 13 - "four_tier.py"
Cohesion: 0.08
Nodes (22): _all_assets(), AllocationTarget, CostBreakdown, ExposureConstraint, ForecastRiskMetadata, FourTierContract, FourTierPortfolioState, FourTierRecommendationRequest (+14 more)

### Community 14 - "optimizer.py"
Cohesion: 0.19
Nodes (16): recommend(), CandidateAssessment, _ceil(), _fee(), _floor(), _search(), assess(), buy() (+8 more)

### Community 15 - "test_runtime_persistence.py"
Cohesion: 0.10
Nodes (25): apply_simulation_scenario(), ScenarioRequest, funded_market_position(), runtime_client(), test_repaid_principal_does_not_hide_unpaid_financing_liability(), test_backtest_rejects_rounded_duration_and_duplicate_selection(), test_canonical_optimizer_targets_ignore_unavailable_current_and_future_flows(), test_financing_cost_payment_is_not_a_second_expense() (+17 more)

### Community 16 - "instrument_economics.py"
Cohesion: 0.13
Nodes (27): Executed checks, AnnualRateFixing, calculate_bond_economics(), calculate_duration_sensitivity(), calculate_equity_economics(), calculate_equity_risk(), calculate_index_acquisition(), calculate_overdraft_economics() (+19 more)

### Community 17 - "test_optimizer.py"
Cohesion: 0.19
Nodes (38): asset(), optimize(), portfolio(), request(), test_all_four_tiers_can_be_recommended_in_one_constrained_plan(), test_bond_and_equity_exposure_caps_and_positive_quantities(), test_debt_repayment_is_compared_to_investing(), test_declared_bond_yield_never_automatically_becomes_a_coupon() (+30 more)

### Community 18 - "reports.py"
Cohesion: 0.11
Nodes (19): AccountingMetrics, AccountingTotals, HistoryPoint, BacktestReport, BacktestReportService, frontend_metrics(), FrontendFinancialMetrics, project_comparison() (+11 more)

### Community 19 - "fixture"
Cohesion: 0.10
Nodes (28): dataset(), make_shared_runtime_factory(), request_spec(), source(), load(), shared_factory(), fixture(), test_all_four_positions_and_overdraft_liability_are_separate() (+20 more)

### Community 20 - "test_hourly_forecasting.py"
Cohesion: 0.10
Nodes (24): ML Forecasting Contracts and Public API, RJ-M1-09 Hourly ML forecasting and chronological evaluation, Unified Hourly Dispatch, test_15_hour_overnight_repo_horizon(), test_24_hour_daily_cycle_horizon(), test_baseline_reproducibility(), test_correct_hourly_lag_alignment_and_named_aliases(), test_extract_hourly_calendar_features() (+16 more)

### Community 21 - "test_instrument_economics.py"
Cohesion: 0.12
Nodes (31): fixing(), portfolio(), repo(), round_trip(), test_actual_repo_maturity_and_fifteen_hour_interest(), test_bond_observed_price_gain_and_loss(), test_bond_yield_quote_and_duration_not_added_to_mark(), test_borrowed_cash_and_principal_liability_cancel_in_portfolio_value() (+23 more)

### Community 22 - "service.py"
Cohesion: 0.16
Nodes (5): ComparisonResult, StrategyMetrics, HourlyEngineFactory, rounded_mean(), test_actual_shared_engine_comparison()

### Community 23 - "test_decisions.py"
Cohesion: 0.18
Nodes (34): decide(), forecast(), policy(), terms(), test_action_precedence_deficit_before_window_minimum_or_investment(), test_aggregate_cover_requires_separate_multi_vault_plan(), test_capped_below_minimum(), test_delayed_withdrawal_cannot_meet_immediate_deficit() (+26 more)

### Community 25 - "package.json"
Cohesion: 0.10
Nodes (25): dependencies, react, react-dom, devDependencies, vite, @vitejs/plugin-react, name, private (+17 more)

### Community 26 - "test_liquidity_risk.py"
Cohesion: 0.23
Nodes (34): calculate(), path(), policy(), request(), state(), test_adverse_outflows_monotonically_increase_reserve(), test_bond_equity_stress_and_liquidation_penalties(), test_booked_maturity_not_counted_again_and_duplicate_rejected() (+26 more)

### Community 27 - "monte_carlo_risk.py"
Cohesion: 0.12
Nodes (22): _calculate(), calculate_four_tier_liquidity_risk(), collect(), _ceil(), CommittedObligation, _cost(), _events(), FourTierLiquidityRiskResult (+14 more)

### Community 28 - "README.md"
Cohesion: 0.06
Nodes (28): 1. Team Workstreams & Responsibilities, 2. Branching Strategy, 3. Engineering Philosophy & Guidelines, Feature Branch Lifecycle:, 1. Overview & Objective, 2.1. Expected Liquidity Requirement ($L_{req}$), 2.2. Forecast Uncertainty ($\sigma_{forecast}$), 2.3. Operational Safety Buffer ($B_{safety}$) (+20 more)

### Community 29 - "protocol.py"
Cohesion: 0.11
Nodes (16): EngineState, EngineCapabilities, ScriptedRun, state(), receipt(), test_asset_sum_must_also_be_safe(), test_balance_sheet_validation_including_copied_model(), test_configuration_is_exact_unambiguous_and_immutable() (+8 more)

### Community 30 - "run_service.py"
Cohesion: 0.14
Nodes (17): advance_simulation_run(), _get_or_load_dataset(), get_simulation_decisions(), get_simulation_forecast(), get_simulation_history(), get_simulation_snapshot(), get_simulation_transactions(), update_simulation_policy() (+9 more)

### Community 31 - "test_persistence.py"
Cohesion: 0.11
Nodes (26): apply_migrations(), RunScopedRepository, bond(), clean_database(), dataset(), ledger(), linked(), pg_engine() (+18 more)

### Community 32 - "MEMBER_2_SPEC.md"
Cohesion: 0.07
Nodes (28): 10. SIMULATION INITIALIZATION, 13. HISTORICAL DATA GENERATION, 14. REAL-TIME TRANSACTION AGGREGATOR, 1. YOUR ROLE AND MISSION, 25. FASTAPI CONTRACT, 27. API ERROR HANDLING, 32. DOCKER AND ENVIRONMENT MANAGEMENT, 33. PERFORMANCE REQUIREMENTS (+20 more)

### Community 33 - "simulate_multi_asset_monte_carlo_risk"
Cohesion: 0.17
Nodes (18): hourly_series_168(), make_forecast(), make_policy(), make_portfolio(), test_consistent_json_serialization(), test_correct_repo_cash_availability(), test_default_500_scenarios_and_runtime(), test_forced_liquidation_and_overdraft_costs() (+10 more)

### Community 34 - "v1_contracts.py"
Cohesion: 0.14
Nodes (20): AggregatesSnapshot, BacktestRequest, BacktestResult, CashFlowBucket, ContractModel, ErrorResponse, FinancialMetrics, LedgerEntry (+12 more)

### Community 35 - "test_forecasting.py"
Cohesion: 0.12
Nodes (16): make_history(), test_calendar_features_causal(), test_causality_and_input_validation(), test_correct_lag_alignment(), test_feature_matrix_generation(), test_forecast_horizons_1_2_4_96(), test_json_serialization_roundtrip(), test_nonnegative_predicted_inflow_outflow() (+8 more)

### Community 36 - "30. BACKEND TESTING REQUIREMENTS"
Cohesion: 0.08
Nodes (26): 30. BACKEND TESTING REQUIREMENTS, Test 10 — Emergency borrowing, Test 11 — Payout failure, Test 12 — Normal scenario, Test 13 — High withdrawal scenario, Test 14 — Low deposit scenario, Test 15 — Settlement delay, Test 16 — Liquidity shock (+18 more)

### Community 37 - "Contract"
Cohesion: 0.10
Nodes (10): canonical_config(), check(), Contract, FinancingReceipt, HourlyExecutionBundle, PartialSaleReceipt, PayoutReceipt, PurchaseReceipt (+2 more)

### Community 38 - "repositories.py"
Cohesion: 0.10
Nodes (14): DatasetSource, configuration_identity(), DatasetRepository, RunRepository, Applying and verifying migrations, Authoritative storage, Deliberate boundaries / remaining contracts, Four-tier persistence foundation (Milestone 2) (+6 more)

### Community 39 - "test_organizer_data.py"
Cohesion: 0.12
Nodes (16): DatasetValidationError, OrganizerDatasetSource, dataset(), raw_rows(), test_content_hash_changes_when_bytes_change(), test_dataset_validation_rejects_invalid_records(), test_environment_configuration(), test_exact_diagnostics_under_low_decimal_context() (+8 more)

### Community 40 - "test_financial_math.py"
Cohesion: 0.17
Nodes (16): context(), maturity(), path(), test_booked_maturity_is_not_counted_again(), test_fourteen_million_reserve(), test_frozen_reserve_api_rounds_up_and_uses_path(), test_invalid_maturity_schedule(), test_invalid_money() (+8 more)

### Community 41 - "test_execution_receipt_adapter.py"
Cohesion: 0.17
Nodes (10): ExecutionReceiptAdapter, make_order(), test_bundle_reconciles_positions_cash_debt_and_nav(), test_insufficient_funds_payout_and_overdraft_use(), test_partial_sale_receipt_preserves_fill_and_basis_reconciliation(), test_purchase_receipt_preserves_executed_details_and_reconciles(), recommend(), test_receipt_adapter_is_idempotent() (+2 more)

### Community 42 - "reserve_juggler_v1.simulation_runs"
Cohesion: 0.24
Nodes (23): 003: four-tier persistence (storage only), reserve_juggler_v1.backtest_results, reserve_juggler_v1.bond_positions, reserve_juggler_v1.cash_accounts, reserve_juggler_v1.dataset_sources, reserve_juggler_v1.equity_positions, reserve_juggler_v1.forecasts, reserve_juggler_v1.investment_movements (+15 more)

### Community 43 - "organizer.py"
Cohesion: 0.17
Nodes (7): _configured_path(), DatasetMetadata, DatasetValidation, FrozenModel, ReconciliationSummary, ValidationIssue, Organizer treasury CSV (authoritative hourly source)

### Community 44 - "TransactionGenerator"
Cohesion: 0.20
Nodes (4): TransactionGenerator, test_generator_baseline_event(), test_generator_deposit_run(), test_generator_payroll_spike()

### Community 45 - "OrganizerObservation"
Cohesion: 0.15
Nodes (11): OrganizerObservation, build_four_tier_policy(), get_hourly_forecasts_from_db(), get_information_cutoff(), get_published_observation(), hydrate_decision_portfolio(), test_publication_boundary_for_training_and_market_quotes(), test_risk_rejects_unpublished_market_inputs() (+3 more)

### Community 46 - "runs.py"
Cohesion: 0.25
Nodes (13): advance(), backtest(), _sanitize_json_for_config(), create_run(), decisions(), forecast(), history(), policy() (+5 more)

### Community 47 - "test_four_tier_runtime.py"
Cohesion: 0.12
Nodes (15): clean_database(), dataset(), pg_engine(), pg_url(), session(), test_api_endpoint_simulation_step(), test_repo_maturity(), execute() (+7 more)

### Community 48 - "Organizer historical data foundation"
Cohesion: 0.40
Nodes (4): Current source identity, Organizer historical data foundation, Read and validate, Schema, precision, and immutability

### Community 49 - "treasury.py"
Cohesion: 0.33
Nodes (11): DecisionModel, ForecastModel, LiquiditySnapshotModel, SimulationRunModel, TransactionModel, get_current_forecast(), get_current_liquidity(), get_decisions_history() (+3 more)

### Community 50 - "HourlyCashFlowBucket"
Cohesion: 0.17
Nodes (5): Core Contracts and Configuration, test_hourly_cashflow_bucket_from_observation(), test_hourly_cashflow_bucket_model(), OrganizerHourlyObservation, HourlyCashFlowBucket

### Community 51 - "schemas.py"
Cohesion: 0.25
Nodes (13): Decision, Forecast, ForecastBase, HealthStatus, LiquiditySnapshot, ScenarioConfigRequest, SimulationRun, SimulationStartRequest (+5 more)

### Community 52 - "TreasuryDecisionEngine"
Cohesion: 0.19
Nodes (6): TreasuryDecisionEngine, test_hold_decision_in_corridor(), test_liquidity_warning_on_extreme_insolvency(), test_required_reserve_calculation(), test_sweep_decision_on_excess_cash(), test_withdraw_decision_on_liquidity_deficit()

### Community 53 - "CashFlowBucket"
Cohesion: 0.30
Nodes (8): [RJ-M1-03] Feature Engineering and Baseline Forecasts, test_preservation_of_15_minute_synthetic_mode(), forecast_cashflows(), rolling_mean_forecast(), seasonal_naive_forecast(), validate_forecast_inputs(), CashFlowBucket, ForecastPoint

### Community 54 - "test_strategy_dispatch_and_causality.py"
Cohesion: 0.18
Nodes (9): _create_test_run(), dataset(), pg_engine(), pg_url(), session(), test_accounting_invariants_and_sweep_across_strategies(), test_strategy_dispatch_policy_paths(), test_strategy_id_normalization_and_acceptance() (+1 more)

### Community 55 - "SimulationRun"
Cohesion: 0.26
Nodes (10): SimulationRun, create_simulation_run(), CreateRunRequest, sim_state(), test_source_time_creation_does_not_invent_utc_and_allows_final_observation(), test_canonical_decisions_use_only_closed_market_hours(), capture(), test_first_source_hour_has_no_published_market_quote() (+2 more)

### Community 56 - "datetime"
Cohesion: 0.23
Nodes (4): CashFlowForecaster, test_forecaster_baseline(), test_forecaster_with_transactions(), test_end_to_end_pipeline()

### Community 58 - "treasury_intelligence/test_contracts.py"
Cohesion: 0.29
Nodes (5): test_all_financial_fields_reject_negative_values(), test_invalid_inputs(), test_json_round_trip_and_immutable_contract(), test_other_valid_recommendations(), test_public_functions_are_contract_only()

### Community 59 - "recommend_four_tier_allocation"
Cohesion: 0.18
Nodes (6): [RJ-M1-11] Four-Tier Treasury Optimizer, AllocationOptimizerResult, recommend_four_tier_allocation(), collect(), FourTierDecisionResult, recommend_portfolio_allocation()

### Community 60 - "24. DATABASE DESIGN"
Cohesion: 0.17
Nodes (12): 24. DATABASE DESIGN, Database requirements, Table 10 — backtest_results, Table 1 — simulation_runs, Table 2 — transactions, Table 3 — ledger_entries, Table 4 — vault_positions, Table 5 — vault_movements (+4 more)

### Community 61 - "42. FINAL DELIVERABLES"
Cohesion: 0.17
Nodes (12): 42. FINAL DELIVERABLES, A. Implementation summary, B. Database schema, C. Backend API documentation, D. Transaction simulator documentation, E. Ledger documentation, F. Backtesting documentation, G. Integration instructions for Member 1 (+4 more)

### Community 62 - "test_api_versioning.py"
Cohesion: 0.20
Nodes (5): test_backtest_routes_return_not_found_for_missing_run(), test_create_request_rejects_incompatible_units_or_values(), test_implemented_routes_return_not_found_for_missing_run(), test_spec_defaults_and_utc_normalization(), test_transaction_direction_and_vault_timing_validation()

### Community 63 - "HourlyObservation"
Cohesion: 0.27
Nodes (5): HourlyObservation, test_invalid_boolean_flags(), test_invalid_financial_domains(), test_invalid_or_reinterpreted_timestamps(), test_invalid_source_numbers()

### Community 64 - "Reserve Juggler backend and engine integration contract"
Cohesion: 0.18
Nodes (8): Scenario, Authority and scope, Confirmed incompatibilities in the initial repository, Contract decisions requiring team review, Member 1 integration placeholder — NOT AN AGREED ENGINE CONTRACT, Reserve Juggler backend and engine integration contract, Shared financial and data conventions, Verification limits

### Community 66 - "reserve_for_path"
Cohesion: 0.24
Nodes (5): RJ-M1-02 pure financial mathematics, known_vault_maturities(), maximum_cumulative_shortfall(), reserve_for_path(), VaultMaturity

### Community 68 - "Task Log"
Cohesion: 0.18
Nodes (10): Member 1 Progress Tracker — Reserve Juggler, [Pre-RJ-M1-10] Canonical Contract Compatibility Check, [RJ-M1-00] Repository Audit and Branch Setup, [RJ-M1-01] Quantitative Engine Contracts, [RJ-M1-02] Financial Mathematics, [RJ-M1-04] Treasury Decisions and Explanations, [RJ-M1-06] Four-Tier Contract Migration, [RJ-M1-08] Four-Tier Financial Mathematics (+2 more)

### Community 69 - "Repository Audit & Workstream Specification — Member 1"
Cohesion: 0.18
Nodes (10): 1. Executive Summary & Verification, 2. Repository Architecture & Component Inspection, 3. Mathematical & Quantitative Engine Placement, 4. File Ownership & Boundary Matrix, 5. Verification Commands & Test Harness, Baseline Test Results at Audit:, Chosen Location: `treasury_intelligence/` & `forecasting/`, Full Suite Run Command: (+2 more)

### Community 70 - "31. FINANCIAL INVARIANTS"
Cohesion: 0.18
Nodes (11): 31. FINANCIAL INVARIANTS, Invariant 10 — Strategy isolation, Invariant 1 — Principal conservation, Invariant 2 — Interest accounting, Invariant 3 — No double execution, Invariant 4 — No free liquidity, Invariant 5 — Honest payout status, Invariant 6 — Accurate borrowing costs (+3 more)

### Community 71 - "35. PARALLEL DEVELOPMENT RULES"
Cohesion: 0.18
Nodes (11): 35. PARALLEL DEVELOPMENT RULES, Rule 1, Rule 10, Rule 2, Rule 3, Rule 4, Rule 5, Rule 6 (+3 more)

### Community 72 - "40. JUDGE-READY TECHNICAL EXPLANATIONS"
Cohesion: 0.18
Nodes (11): 40. JUDGE-READY TECHNICAL EXPLANATIONS, Are these actual bank transactions?, How are transactions generated?, How do you compare against baselines?, How do you measure financial performance?, How do you prevent misleading results?, How does the system simulate real time?, How is a sweep executed? (+3 more)

### Community 73 - "TreasuryPolicy"
Cohesion: 0.27
Nodes (3): PolicyPatch, TreasuryPolicy, VaultPosition

### Community 74 - "GRAPHIFY — MANDATORY PROJECT KNOWLEDGE GRAPH"
Cohesion: 0.22
Nodes (8): GIT MILESTONE RULE — MANDATORY, Graphify accuracy rule, GRAPHIFY — MANDATORY PROJECT KNOWLEDGE GRAPH, Important, Initial setup, Milestone examples, Project Rules and Guidelines, Regular updates

### Community 75 - "21. STRESS SCENARIO ENGINE"
Cohesion: 0.22
Nodes (9): 21. STRESS SCENARIO ENGINE, HIGH_WITHDRAWAL, LIQUIDITY_SHOCK, LOW_DEPOSIT, Mid-run scenario application, NORMAL, Scenario implementation rule, SETTLEMENT_DELAY (+1 more)

### Community 76 - "34. MEMBER 2 DEVELOPMENT TIMELINE"
Cohesion: 0.22
Nodes (9): 34. MEMBER 2 DEVELOPMENT TIMELINE, Hours 0–1 — Contract and Repository Setup, Hours 10–14 — Backtesting and Member 1 Integration, Hours 14–18 — Advanced Metrics and Reliability, Hours 18–21 — Final Integration, Hours 1–4 — Transaction and Ledger Foundation, Hours 21–24 — Feature Freeze, Hours 4–7 — Simulation and API (+1 more)

### Community 77 - "41. DEFINITION OF DONE"
Cohesion: 0.22
Nodes (9): 41. DEFINITION OF DONE, API, Database, Evaluation, Integration, Simulation engine, Stress testing, Transaction engine (+1 more)

### Community 79 - "http_error"
Cohesion: 0.32
Nodes (3): http_error(), unexpected_error(), validation_error()

### Community 81 - ".net_flow_residual_usd"
Cohesion: 0.43
Nodes (3): _exact_difference(), _exact_total(), Provenance and diagnostics

### Community 82 - "advance_simulation_step"
Cohesion: 0.29
Nodes (3): advance_simulation_step(), StepRequest, StepResponse

### Community 83 - "12. TRANSACTION DISTRIBUTION MODEL"
Cohesion: 0.29
Nodes (7): 12. TRANSACTION DISTRIBUTION MODEL, Deposit distribution, Merchant settlements, Randomness, Time-of-day behavior, Transaction volume, Withdrawal distribution

### Community 84 - "test_runs_runtime.py"
Cohesion: 0.06
Nodes (15): client(), override_get_db(), dataset(), pg_engine(), pg_url(), test_accounting_identities(), test_all_five_scenarios_scheduling(), test_enveloped_collections_responses() (+7 more)

### Community 85 - "23. FINANCIAL PERFORMANCE METRICS"
Cohesion: 0.29
Nodes (7): 23. FINANCIAL PERFORMANCE METRICS, Baseline comparison, Core financial metric, Liquidity metrics, Transaction metrics, Treasury activity metrics, Yield metrics

### Community 86 - "Core runtime release checkpoints"
Cohesion: 0.29
Nodes (6): Capped financing and payout receipt v1, Confirmed publication and delayed repo convention, Core runtime release checkpoints, Market execution receipt v1, Verification and remaining gates, test_public_backtest_retains_fields_and_honors_requested_subset()

### Community 87 - "load_organizer_dataset"
Cohesion: 0.29
Nodes (3): test_load_organizer_dataset_from_fixture_and_limits(), test_full_dataset_ml_evaluation_if_present(), load_organizer_dataset()

### Community 88 - "GRAPHIFY — MANDATORY PROJECT KNOWLEDGE GRAPH"
Cohesion: 0.33
Nodes (5): Graphify accuracy rule, GRAPHIFY — MANDATORY PROJECT KNOWLEDGE GRAPH, Important, Initial setup, Regular updates

### Community 89 - "start_simulation"
Cohesion: 0.33
Nodes (3): get_simulation_results(), start_simulation(), update_scenario()

### Community 90 - "11. SYNTHETIC TRANSACTION GENERATOR"
Cohesion: 0.33
Nodes (6): 11. SYNTHETIC TRANSACTION GENERATOR, A. DEPOSIT, B. WITHDRAWAL, C. MERCHANT_SETTLEMENT, Required behavior, Required transaction fields

### Community 91 - "16. YIELD VAULT LEDGER"
Cohesion: 0.33
Nodes (6): 16. YIELD VAULT LEDGER, Creating a vault position, Interest accounting, Interest calculation, Maturity processing, Required position fields

### Community 92 - "18. EMERGENCY LIQUIDITY AND PAYOUT FAILURES"
Cohesion: 0.33
Nodes (6): 18. EMERGENCY LIQUIDITY AND PAYOUT FAILURES, Emergency borrowing configuration, Important metrics, Scenario A — Sufficient checking, Scenario B — Checking insufficient, emergency borrowing allowed, Scenario C — Funding unavailable

### Community 93 - "22. STRATEGY BACKTESTING"
Cohesion: 0.33
Nodes (6): 22. STRATEGY BACKTESTING, Critical fairness rule, Recommended implementation, Strategy A — STATIC RESERVE, Strategy B — REACTIVE RESERVE, Strategy C — RESERVE JUGGLER

### Community 94 - "26. API REQUEST AND RESPONSE EXAMPLES"
Cohesion: 0.33
Nodes (6): 26. API REQUEST AND RESPONSE EXAMPLES, A. Create Simulation, B. Advance Simulation, C. Apply Scenario, D. Treasury Snapshot, E. Backtest Result

### Community 95 - "19. SIMULATION STEP EXECUTION"
Cohesion: 0.40
Nodes (5): 19. SIMULATION STEP EXECUTION, Idempotency, Important financial detail, Important policy detail, Required execution sequence

### Community 96 - "37. EARLY HANDOFF TO MEMBER 1"
Cohesion: 0.40
Nodes (5): 37. EARLY HANDOFF TO MEMBER 1, Configurable policy, Execution feedback, Historical data, Treasury context

### Community 98 - "15. CHECKING ACCOUNT LEDGER"
Cohesion: 0.50
Nodes (4): 15. CHECKING ACCOUNT LEDGER, Concurrency safety, Financial correctness, Required ledger entry information

### Community 99 - "17. EARLY VAULT REDEMPTION"
Cohesion: 0.50
Nodes (4): 17. EARLY VAULT REDEMPTION, Configurable parameters, Early redemption sequence, Important rule

### Community 100 - "20. INTEGRATION WITH MEMBER 1"
Cohesion: 0.50
Nodes (4): 20. INTEGRATION WITH MEMBER 1, Create a treasury adapter, Fallback implementation, Final integration

### Community 101 - "28. BACKTEST IMPLEMENTATION DETAILS"
Cohesion: 0.50
Nodes (4): 28. BACKTEST IMPLEMENTATION DETAILS, Backtesting outputs, Fair comparison, No lookahead

### Community 102 - "29. FRONTEND INTEGRATION SUPPORT"
Cohesion: 0.50
Nodes (4): 29. FRONTEND INTEGRATION SUPPORT, Early deliverable, Integration strategy, Live dashboard updates

### Community 103 - "2. PROJECT PROBLEM STATEMENT"
Cohesion: 0.50
Nodes (4): 2. PROJECT PROBLEM STATEMENT, Checking Account, Financial Problem, Yield Vault

### Community 104 - "6. YOUR EXACT RESPONSIBILITIES"
Cohesion: 0.50
Nodes (4): 6. YOUR EXACT RESPONSIBILITIES, P0 — Mandatory Features, P1 — Competitive Enhancements, P2 — Only After P0 and P1 Are Stable

### Community 105 - "PULL_REQUEST_TEMPLATE.md"
Cohesion: 0.50
Nodes (3): 1. Workstream Area, 2. Changes Summary, 3. Verification Checklist

## Knowledge Gaps
- **333 isolated node(s):** `name`, `private`, `version`, `type`, `dev` (+328 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 765 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **24 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `advance()` connect `runs.py` to `StepConflictError`, `run_service.py`, `19. SIMULATION STEP EXECUTION`?**
  _High betweenness centrality (0.147) - this node is a cross-community bridge._
- **Why does `Idempotency` connect `19. SIMULATION STEP EXECUTION` to `runs.py`?**
  _High betweenness centrality (0.146) - this node is a cross-community bridge._
- **Why does `19. SIMULATION STEP EXECUTION` connect `19. SIMULATION STEP EXECUTION` to `MEMBER_2_SPEC.md`?**
  _High betweenness centrality (0.146) - this node is a cross-community bridge._
- **Are the 5 inferred relationships involving `execute_hourly_step()` (e.g. with `BondPosition` and `EquityPosition`) actually correct?**
  _`execute_hourly_step()` has 5 INFERRED edges - model-reasoned connections that need verification._
- **Are the 41 inferred relationships involving `SimulationRun` (e.g. with `ExecutionReceiptAdapter` and `BacktestReportService`) actually correct?**
  _`SimulationRun` has 41 INFERRED edges - model-reasoned connections that need verification._
- **Are the 40 inferred relationships involving `OrganizerObservation` (e.g. with `read_hour_receipt()` and `DatasetRepository`) actually correct?**
  _`OrganizerObservation` has 40 INFERRED edges - model-reasoned connections that need verification._
- **What connects `name`, `private`, `version` to the rest of the system?**
  _333 weakly-connected nodes found - possible documentation gaps or missing edges._