# Graph Report - reserve-juggler  (2026-10-17)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 747 nodes · 1446 edges · 53 communities (46 shown, 7 thin omitted)
- Extraction: 92% EXTRACTED · 8% INFERRED · 0% AMBIGUOUS · INFERRED: 119 edges (avg confidence: 0.95)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from the RJ-M1-06 working tree; committed together with its source.
- Pre-migration base: `c35da91c` (not the identity of the updated contracts).
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- treasury_intelligence/__init__.py
- treasury.py
- demo.py
- portfolio.py
- test_four_tier_contracts.py
- test_decisions.py
- README.md
- package.json
- test_forecasting.py
- 30. BACKEND TESTING REQUIREMENTS
- test_financial_math.py
- MEMBER_2_SPEC.md
- TreasuryDecisionEngine
- Quantitative engine contracts: legacy v1 and four-tier v1
- CashFlowForecaster
- 24. DATABASE DESIGN
- 42. FINAL DELIVERABLES
- Repository Audit & Workstream Specification — Member 1
- 31. FINANCIAL INVARIANTS
- 35. PARALLEL DEVELOPMENT RULES
- 40. JUDGE-READY TECHNICAL EXPLANATIONS
- TransactionGenerator
- 21. STRESS SCENARIO ENGINE
- 34. MEMBER 2 DEVELOPMENT TIMELINE
- 41. DEFINITION OF DONE
- Task Log
- 12. TRANSACTION DISTRIBUTION MODEL
- 23. FINANCIAL PERFORMANCE METRICS
- 11. SYNTHETIC TRANSACTION GENERATOR
- 16. YIELD VAULT LEDGER
- 18. EMERGENCY LIQUIDITY AND PAYOUT FAILURES
- 22. STRATEGY BACKTESTING
- 26. API REQUEST AND RESPONSE EXAMPLES
- 19. SIMULATION STEP EXECUTION
- 37. EARLY HANDOFF TO MEMBER 1
- 15. CHECKING ACCOUNT LEDGER
- 17. EARLY VAULT REDEMPTION
- 20. INTEGRATION WITH MEMBER 1
- 28. BACKTEST IMPLEMENTATION DETAILS
- 29. FRONTEND INTEGRATION SUPPORT
- 2. PROJECT PROBLEM STATEMENT
- 6. YOUR EXACT RESPONSIBILITIES
- PULL_REQUEST_TEMPLATE.md
- 13. HISTORICAL DATA GENERATION
- 14. REAL-TIME TRANSACTION AGGREGATOR
- MEMBER 2 — COMPLETE DEVELOPMENT AGENT PROMPT

## God Nodes (most connected - your core abstractions)
1. `decide()` - 30 edges
2. `CashFlowBucket` - 26 edges
3. `30. BACKEND TESTING REQUIREMENTS` - 26 edges
4. `ForecastResult` - 25 edges
5. `policy()` - 24 edges
6. `Contract` - 24 edges
7. `TreasuryContext` - 24 edges
8. `TreasuryPipelineResult` - 23 edges
9. `run_treasury_pipeline()` - 20 edges
10. `terms()` - 18 edges

## Surprising Connections (you probably didn't know these)
- `RJ-M1-04 Treasury decisions` --references--> `VaultTerms`  [INFERRED]
  docs/member1/ENGINE_CONTRACT.md → treasury_intelligence/policy.py
- `[RJ-M1-06] Four-Tier Contract Migration` --references--> `PortfolioState`  [INFERRED]
  docs/member1/PROGRESS.md → treasury_intelligence/portfolio.py
- `2. Repository Architecture & Component Inspection` --references--> `CashFlowForecaster`  [INFERRED]
  docs/member1/REPO_AUDIT.md → forecasting/forecaster.py
- `2. Repository Architecture & Component Inspection` --references--> `TransactionGenerator`  [INFERRED]
  docs/member1/REPO_AUDIT.md → simulation/generator.py
- `RJ-M1-03 Causal feature engineering and baseline forecasting` --references--> `forecast_cashflows()`  [INFERRED]
  docs/member1/ENGINE_CONTRACT.md → treasury_intelligence/api.py

## Import Cycles
- None detected.

## Communities (53 total, 7 thin omitted)

### Community 0 - "treasury_intelligence/__init__.py"
Cohesion: 0.08
Nodes (31): Compatibility decisions, RJ-M1-02 pure financial mathematics, evaluate_allocation_candidates(), evaluate_forecasting_models(), generate_risk_scenarios(), early_redemption_penalty(), expected_net_economic_benefit(), _rate() (+23 more)

### Community 1 - "treasury.py"
Cohesion: 0.07
Nodes (32): Settings, get_db(), root(), DecisionModel, ForecastModel, LiquiditySnapshotModel, SimulationRunModel, TransactionModel (+24 more)

### Community 2 - "demo.py"
Cohesion: 0.09
Nodes (31): [RJ-M1-03] Feature Engineering and Baseline Forecasts, [RJ-M1-05] Standalone Treasury Decision Pipeline and Demo, test_pipeline_cli_demo_execution(), test_pipeline_deterministic_reproducibility(), test_pipeline_high_withdrawal_stress(), test_pipeline_json_serialization_roundtrip(), test_pipeline_locked_vault_insufficient_liquidity(), test_pipeline_normal_operation() (+23 more)

### Community 3 - "portfolio.py"
Cohesion: 0.09
Nodes (21): RJ-M1-06 — Authoritative organizer four-tier contracts, Snapshot and recommendation semantics, Units, identity and time, Existing storage mapping (Member 2 commit 52e58bc), BondPosition, CashPosition, _check_times(), EquityPosition (+13 more)

### Community 4 - "test_four_tier_contracts.py"
Cohesion: 0.08
Nodes (18): test_all_financial_fields_reject_negative_values(), test_invalid_inputs(), test_json_round_trip_and_immutable_contract(), test_other_valid_recommendations(), test_public_functions_are_contract_only(), order(), reserve(), source() (+10 more)

### Community 5 - "test_decisions.py"
Cohesion: 0.18
Nodes (34): decide(), forecast(), policy(), terms(), test_action_precedence_deficit_before_window_minimum_or_investment(), test_aggregate_cover_requires_separate_multi_vault_plan(), test_capped_below_minimum(), test_delayed_withdrawal_cannot_meet_immediate_deficit() (+26 more)

### Community 6 - "README.md"
Cohesion: 0.06
Nodes (28): 1. Team Workstreams & Responsibilities, 2. Branching Strategy, 3. Engineering Philosophy & Guidelines, Feature Branch Lifecycle:, 1. Overview & Objective, 2.1. Expected Liquidity Requirement ($L_{req}$), 2.2. Forecast Uncertainty ($\sigma_{forecast}$), 2.3. Operational Safety Buffer ($B_{safety}$) (+20 more)

### Community 7 - "package.json"
Cohesion: 0.10
Nodes (25): dependencies, react, react-dom, devDependencies, vite, @vitejs/plugin-react, name, private (+17 more)

### Community 8 - "test_forecasting.py"
Cohesion: 0.11
Nodes (16): make_history(), test_calendar_features_causal(), test_causality_and_input_validation(), test_correct_lag_alignment(), test_feature_matrix_generation(), test_forecast_horizons_1_2_4_96(), test_json_serialization_roundtrip(), test_nonnegative_predicted_inflow_outflow() (+8 more)

### Community 9 - "30. BACKEND TESTING REQUIREMENTS"
Cohesion: 0.08
Nodes (26): 30. BACKEND TESTING REQUIREMENTS, Test 10 — Emergency borrowing, Test 11 — Payout failure, Test 12 — Normal scenario, Test 13 — High withdrawal scenario, Test 14 — Low deposit scenario, Test 15 — Settlement delay, Test 16 — Liquidity shock (+18 more)

### Community 10 - "test_financial_math.py"
Cohesion: 0.16
Nodes (16): context(), maturity(), path(), test_booked_maturity_is_not_counted_again(), test_fourteen_million_reserve(), test_frozen_reserve_api_rounds_up_and_uses_path(), test_invalid_maturity_schedule(), test_invalid_money() (+8 more)

### Community 11 - "MEMBER_2_SPEC.md"
Cohesion: 0.10
Nodes (19): 10. SIMULATION INITIALIZATION, 1. YOUR ROLE AND MISSION, 25. FASTAPI CONTRACT, 27. API ERROR HANDLING, 32. DOCKER AND ENVIRONMENT MANAGEMENT, 33. PERFORMANCE REQUIREMENTS, 36. EARLY HANDOFF TO MEMBER 3, 38. BACKEND DEMONSTRATION REQUIREMENT (+11 more)

### Community 12 - "TreasuryDecisionEngine"
Cohesion: 0.20
Nodes (6): TreasuryDecisionEngine, test_hold_decision_in_corridor(), test_liquidity_warning_on_extreme_insolvency(), test_required_reserve_calculation(), test_sweep_decision_on_excess_cash(), test_withdraw_decision_on_liquidity_deficit()

### Community 13 - "Quantitative engine contracts: legacy v1 and four-tier v1"
Cohesion: 0.14
Nodes (12): Executable Demo, Key Principles & Behavior, Pipeline Flow, Public signatures, Quantitative engine contracts: legacy v1 and four-tier v1, RJ-M1-03 Causal feature engineering and baseline forecasting, RJ-M1-04 Treasury decisions, RJ-M1-05 Standalone treasury pipeline demo (+4 more)

### Community 14 - "CashFlowForecaster"
Cohesion: 0.24
Nodes (4): CashFlowForecaster, test_forecaster_baseline(), test_forecaster_with_transactions(), test_end_to_end_pipeline()

### Community 15 - "24. DATABASE DESIGN"
Cohesion: 0.17
Nodes (12): 24. DATABASE DESIGN, Database requirements, Table 10 — backtest_results, Table 1 — simulation_runs, Table 2 — transactions, Table 3 — ledger_entries, Table 4 — vault_positions, Table 5 — vault_movements (+4 more)

### Community 16 - "42. FINAL DELIVERABLES"
Cohesion: 0.17
Nodes (12): 42. FINAL DELIVERABLES, A. Implementation summary, B. Database schema, C. Backend API documentation, D. Transaction simulator documentation, E. Ledger documentation, F. Backtesting documentation, G. Integration instructions for Member 1 (+4 more)

### Community 17 - "Repository Audit & Workstream Specification — Member 1"
Cohesion: 0.18
Nodes (10): 1. Executive Summary & Verification, 2. Repository Architecture & Component Inspection, 3. Mathematical & Quantitative Engine Placement, 4. File Ownership & Boundary Matrix, 5. Verification Commands & Test Harness, Baseline Test Results at Audit:, Chosen Location: `treasury_intelligence/` & `forecasting/`, Full Suite Run Command: (+2 more)

### Community 18 - "31. FINANCIAL INVARIANTS"
Cohesion: 0.18
Nodes (11): 31. FINANCIAL INVARIANTS, Invariant 10 — Strategy isolation, Invariant 1 — Principal conservation, Invariant 2 — Interest accounting, Invariant 3 — No double execution, Invariant 4 — No free liquidity, Invariant 5 — Honest payout status, Invariant 6 — Accurate borrowing costs (+3 more)

### Community 19 - "35. PARALLEL DEVELOPMENT RULES"
Cohesion: 0.18
Nodes (11): 35. PARALLEL DEVELOPMENT RULES, Rule 1, Rule 10, Rule 2, Rule 3, Rule 4, Rule 5, Rule 6 (+3 more)

### Community 20 - "40. JUDGE-READY TECHNICAL EXPLANATIONS"
Cohesion: 0.18
Nodes (11): 40. JUDGE-READY TECHNICAL EXPLANATIONS, Are these actual bank transactions?, How are transactions generated?, How do you compare against baselines?, How do you measure financial performance?, How do you prevent misleading results?, How does the system simulate real time?, How is a sweep executed? (+3 more)

### Community 21 - "TransactionGenerator"
Cohesion: 0.27
Nodes (4): TransactionGenerator, test_generator_baseline_event(), test_generator_deposit_run(), test_generator_payroll_spike()

### Community 22 - "21. STRESS SCENARIO ENGINE"
Cohesion: 0.22
Nodes (9): 21. STRESS SCENARIO ENGINE, HIGH_WITHDRAWAL, LIQUIDITY_SHOCK, LOW_DEPOSIT, Mid-run scenario application, NORMAL, Scenario implementation rule, SETTLEMENT_DELAY (+1 more)

### Community 23 - "34. MEMBER 2 DEVELOPMENT TIMELINE"
Cohesion: 0.22
Nodes (9): 34. MEMBER 2 DEVELOPMENT TIMELINE, Hours 0–1 — Contract and Repository Setup, Hours 10–14 — Backtesting and Member 1 Integration, Hours 14–18 — Advanced Metrics and Reliability, Hours 18–21 — Final Integration, Hours 1–4 — Transaction and Ledger Foundation, Hours 21–24 — Feature Freeze, Hours 4–7 — Simulation and API (+1 more)

### Community 24 - "41. DEFINITION OF DONE"
Cohesion: 0.22
Nodes (9): 41. DEFINITION OF DONE, API, Database, Evaluation, Integration, Simulation engine, Stress testing, Transaction engine (+1 more)

### Community 25 - "Task Log"
Cohesion: 0.25
Nodes (7): Member 1 Progress Tracker — Reserve Juggler, [RJ-M1-00] Repository Audit and Branch Setup, [RJ-M1-01] Quantitative Engine Contracts, [RJ-M1-02] Financial Mathematics, [RJ-M1-04] Treasury Decisions and Explanations, [RJ-M1-06] Four-Tier Contract Migration, Task Log

### Community 26 - "12. TRANSACTION DISTRIBUTION MODEL"
Cohesion: 0.29
Nodes (7): 12. TRANSACTION DISTRIBUTION MODEL, Deposit distribution, Merchant settlements, Randomness, Time-of-day behavior, Transaction volume, Withdrawal distribution

### Community 27 - "23. FINANCIAL PERFORMANCE METRICS"
Cohesion: 0.29
Nodes (7): 23. FINANCIAL PERFORMANCE METRICS, Baseline comparison, Core financial metric, Liquidity metrics, Transaction metrics, Treasury activity metrics, Yield metrics

### Community 28 - "11. SYNTHETIC TRANSACTION GENERATOR"
Cohesion: 0.33
Nodes (6): 11. SYNTHETIC TRANSACTION GENERATOR, A. DEPOSIT, B. WITHDRAWAL, C. MERCHANT_SETTLEMENT, Required behavior, Required transaction fields

### Community 29 - "16. YIELD VAULT LEDGER"
Cohesion: 0.33
Nodes (6): 16. YIELD VAULT LEDGER, Creating a vault position, Interest accounting, Interest calculation, Maturity processing, Required position fields

### Community 30 - "18. EMERGENCY LIQUIDITY AND PAYOUT FAILURES"
Cohesion: 0.33
Nodes (6): 18. EMERGENCY LIQUIDITY AND PAYOUT FAILURES, Emergency borrowing configuration, Important metrics, Scenario A — Sufficient checking, Scenario B — Checking insufficient, emergency borrowing allowed, Scenario C — Funding unavailable

### Community 31 - "22. STRATEGY BACKTESTING"
Cohesion: 0.33
Nodes (6): 22. STRATEGY BACKTESTING, Critical fairness rule, Recommended implementation, Strategy A — STATIC RESERVE, Strategy B — REACTIVE RESERVE, Strategy C — RESERVE JUGGLER

### Community 32 - "26. API REQUEST AND RESPONSE EXAMPLES"
Cohesion: 0.33
Nodes (6): 26. API REQUEST AND RESPONSE EXAMPLES, A. Create Simulation, B. Advance Simulation, C. Apply Scenario, D. Treasury Snapshot, E. Backtest Result

### Community 33 - "19. SIMULATION STEP EXECUTION"
Cohesion: 0.40
Nodes (5): 19. SIMULATION STEP EXECUTION, Idempotency, Important financial detail, Important policy detail, Required execution sequence

### Community 34 - "37. EARLY HANDOFF TO MEMBER 1"
Cohesion: 0.40
Nodes (5): 37. EARLY HANDOFF TO MEMBER 1, Configurable policy, Execution feedback, Historical data, Treasury context

### Community 36 - "15. CHECKING ACCOUNT LEDGER"
Cohesion: 0.50
Nodes (4): 15. CHECKING ACCOUNT LEDGER, Concurrency safety, Financial correctness, Required ledger entry information

### Community 37 - "17. EARLY VAULT REDEMPTION"
Cohesion: 0.50
Nodes (4): 17. EARLY VAULT REDEMPTION, Configurable parameters, Early redemption sequence, Important rule

### Community 38 - "20. INTEGRATION WITH MEMBER 1"
Cohesion: 0.50
Nodes (4): 20. INTEGRATION WITH MEMBER 1, Create a treasury adapter, Fallback implementation, Final integration

### Community 39 - "28. BACKTEST IMPLEMENTATION DETAILS"
Cohesion: 0.50
Nodes (4): 28. BACKTEST IMPLEMENTATION DETAILS, Backtesting outputs, Fair comparison, No lookahead

### Community 40 - "29. FRONTEND INTEGRATION SUPPORT"
Cohesion: 0.50
Nodes (4): 29. FRONTEND INTEGRATION SUPPORT, Early deliverable, Integration strategy, Live dashboard updates

### Community 41 - "2. PROJECT PROBLEM STATEMENT"
Cohesion: 0.50
Nodes (4): 2. PROJECT PROBLEM STATEMENT, Checking Account, Financial Problem, Yield Vault

### Community 42 - "6. YOUR EXACT RESPONSIBILITIES"
Cohesion: 0.50
Nodes (4): 6. YOUR EXACT RESPONSIBILITIES, P0 — Mandatory Features, P1 — Competitive Enhancements, P2 — Only After P0 and P1 Are Stable

### Community 43 - "PULL_REQUEST_TEMPLATE.md"
Cohesion: 0.50
Nodes (3): 1. Workstream Area, 2. Changes Summary, 3. Verification Checklist

### Community 44 - "13. HISTORICAL DATA GENERATION"
Cohesion: 0.67
Nodes (3): 13. HISTORICAL DATA GENERATION, Critical requirement, Historical cash-flow bucket

### Community 45 - "14. REAL-TIME TRANSACTION AGGREGATOR"
Cohesion: 0.67
Nodes (3): 14. REAL-TIME TRANSACTION AGGREGATOR, Core formula, Important distinction

### Community 46 - "MEMBER 2 — COMPLETE DEVELOPMENT AGENT PROMPT"
Cohesion: 0.67
Nodes (3): HackForge 2026 | 24-Hour Hackathon | Developer 2 of 3, MEMBER 2 — COMPLETE DEVELOPMENT AGENT PROMPT, Reserve Juggler — Real-Time Simulation, Banking Ledger, Backend API & Performance Evaluation

## Knowledge Gaps
- **239 isolated node(s):** `name`, `private`, `version`, `type`, `dev` (+234 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 355 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **7 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `TransactionGenerator` connect `TransactionGenerator` to `.generate_event`, `Repository Audit & Workstream Specification — Member 1`, `CashFlowForecaster`?**
  _High betweenness centrality (0.020) - this node is a cross-community bridge._
- **Why does `30. BACKEND TESTING REQUIREMENTS` connect `30. BACKEND TESTING REQUIREMENTS` to `MEMBER_2_SPEC.md`?**
  _High betweenness centrality (0.019) - this node is a cross-community bridge._
- **Why does `2. Repository Architecture & Component Inspection` connect `Repository Audit & Workstream Specification — Member 1` to `TransactionGenerator`, `CashFlowForecaster`?**
  _High betweenness centrality (0.016) - this node is a cross-community bridge._
- **Are the 15 inferred relationships involving `CashFlowBucket` (e.g. with `Units, identity and time` and `evaluate_forecasting_models()`) actually correct?**
  _`CashFlowBucket` has 15 INFERRED edges - model-reasoned connections that need verification._
- **Are the 10 inferred relationships involving `ForecastResult` (e.g. with `Units, identity and time` and `evaluate_allocation_candidates()`) actually correct?**
  _`ForecastResult` has 10 INFERRED edges - model-reasoned connections that need verification._
- **What connects `name`, `private`, `version` to the rest of the system?**
  _239 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `treasury_intelligence/__init__.py` be split into smaller, more focused modules?**
  _Cohesion score 0.07531531531531531 - nodes in this community are weakly interconnected._
