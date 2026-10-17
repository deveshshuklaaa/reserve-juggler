# Graph Report - reserve-juggler  (2026-10-17)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 729 nodes · 1254 edges · 63 communities (50 shown, 13 thin omitted)
- Extraction: 90% EXTRACTED · 10% INFERRED · 0% AMBIGUOUS · INFERRED: 125 edges (avg confidence: 0.95)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from the Milestone 2 working tree; committed together with its source.
- Pre-milestone base: `4ef8b773` (not the identity of the updated source).
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- TreasuryDecisionEngine
- treasury.py
- package.json
- runs.py
- README.md
- 30. BACKEND TESTING REQUIREMENTS
- test_organizer_data.py
- reserve_juggler_v1.simulation_runs
- main.py
- test_persistence.py
- RunScopedRepository
- persistence/models.py
- MEMBER_2_SPEC.md
- SimulationRun
- Base
- repositories.py
- 24. DATABASE DESIGN
- 42. FINAL DELIVERABLES
- HourlyObservation
- organizer.py
- 31. FINANCIAL INVARIANTS
- 35. PARALLEL DEVELOPMENT RULES
- 40. JUDGE-READY TECHNICAL EXPLANATIONS
- GRAPHIFY — MANDATORY PROJECT KNOWLEDGE GRAPH
- 21. STRESS SCENARIO ENGINE
- 34. MEMBER 2 DEVELOPMENT TIMELINE
- 41. DEFINITION OF DONE
- 12. TRANSACTION DISTRIBUTION MODEL
- 23. FINANCIAL PERFORMANCE METRICS
- GRAPHIFY — MANDATORY PROJECT KNOWLEDGE GRAPH
- Four-tier persistence foundation (Milestone 2)
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
- GIT MILESTONE RULE — MANDATORY
- TreasuryDecision
- 13. HISTORICAL DATA GENERATION
- Decimal
- 14. REAL-TIME TRANSACTION AGGREGATOR
- sync-persistence-graph.py
- OrganizerDataset
- MEMBER 2 — COMPLETE DEVELOPMENT AGENT PROMPT

## God Nodes (most connected - your core abstractions)
1. `30. BACKEND TESTING REQUIREMENTS` - 26 edges
2. `ContractModel` - 23 edges
3. `reserve_juggler_v1.simulation_runs` - 23 edges
4. `HourlyObservation` - 22 edges
5. `RunScopedRepository` - 17 edges
6. `reserve_juggler_v1.organizer_observations` - 16 edges
7. `003: four-tier persistence (storage only)` - 15 edges
8. `DatasetRepository` - 14 edges
9. `OrganizerDatasetSource` - 12 edges
10. `unavailable()` - 12 edges

## Surprising Connections (you probably didn't know these)
- `Schema, precision, and immutability` --references--> `HourlyObservation`  [INFERRED]
  docs/organizer-data.md → backend/app/data/organizer.py
- `Idempotency` --references--> `advance()`  [INFERRED]
  docs/MEMBER_2_SPEC.md → backend/app/routers/runs.py
- `Provenance and diagnostics` --references--> `DatasetValidationError`  [INFERRED]
  docs/organizer-data.md → backend/app/data/organizer.py
- `Organizer treasury CSV (authoritative hourly source)` --configured_source_for--> `OrganizerDatasetSource`  [EXTRACTED]
  treasury_4tier_dataset.csv → backend/app/data/organizer.py
- `Integrity and repository contract` --references--> `RunScopedRepository`  [INFERRED]
  docs/four-tier-persistence.md → backend/app/persistence/repositories.py

## Import Cycles
- None detected.

## Communities (63 total, 13 thin omitted)

### Community 0 - "TreasuryDecisionEngine"
Cohesion: 0.07
Nodes (14): TreasuryDecisionEngine, CashFlowForecaster, TransactionGenerator, test_hold_decision_in_corridor(), test_liquidity_warning_on_extreme_insolvency(), test_required_reserve_calculation(), test_sweep_decision_on_excess_cash(), test_withdraw_decision_on_liquidity_deficit() (+6 more)

### Community 1 - "treasury.py"
Cohesion: 0.09
Nodes (30): get_db(), DecisionModel, ForecastModel, LiquiditySnapshotModel, SimulationRunModel, TransactionModel, get_health(), get_simulation_results() (+22 more)

### Community 2 - "package.json"
Cohesion: 0.10
Nodes (25): dependencies, react, react-dom, devDependencies, vite, @vitejs/plugin-react, name, private (+17 more)

### Community 3 - "runs.py"
Cohesion: 0.08
Nodes (44): advance(), backtest(), create_run(), decisions(), forecast(), history(), policy(), report() (+36 more)

### Community 4 - "README.md"
Cohesion: 0.06
Nodes (30): 1. Team Workstreams & Responsibilities, 2. Branching Strategy, 3. Engineering Philosophy & Guidelines, Feature Branch Lifecycle:, 1. Overview & Objective, 2.1. Expected Liquidity Requirement ($L_{req}$), 2.2. Forecast Uncertainty ($\sigma_{forecast}$), 2.3. Operational Safety Buffer ($B_{safety}$) (+22 more)

### Community 5 - "30. BACKEND TESTING REQUIREMENTS"
Cohesion: 0.08
Nodes (26): 30. BACKEND TESTING REQUIREMENTS, Test 10 — Emergency borrowing, Test 11 — Payout failure, Test 12 — Normal scenario, Test 13 — High withdrawal scenario, Test 14 — Low deposit scenario, Test 15 — Settlement delay, Test 16 — Liquidity shock (+18 more)

### Community 6 - "test_organizer_data.py"
Cohesion: 0.12
Nodes (15): DatasetValidationError, OrganizerDatasetSource, dataset(), raw_rows(), test_content_hash_changes_when_bytes_change(), test_dataset_validation_rejects_invalid_records(), test_exact_diagnostics_under_low_decimal_context(), test_fractional_bps_and_high_precision_are_preserved() (+7 more)

### Community 7 - "reserve_juggler_v1.simulation_runs"
Cohesion: 0.24
Nodes (23): 003: four-tier persistence (storage only), reserve_juggler_v1.backtest_results, reserve_juggler_v1.bond_positions, reserve_juggler_v1.cash_accounts, reserve_juggler_v1.dataset_sources, reserve_juggler_v1.equity_positions, reserve_juggler_v1.forecasts, reserve_juggler_v1.investment_movements (+15 more)

### Community 8 - "main.py"
Cohesion: 0.07
Nodes (7): http_error(), root(), unexpected_error(), validation_error(), test_contract_routes_return_honest_unimplemented_error(), test_create_request_rejects_incompatible_units_or_values(), test_spec_defaults_and_utc_normalization()

### Community 9 - "test_persistence.py"
Cohesion: 0.15
Nodes (12): apply_migrations(), clean_database(), dataset(), pg_engine(), pg_url(), session(), test_all_organizer_rows_round_trip_exactly(), test_dataset_store_detects_conflicting_existing_observation() (+4 more)

### Community 10 - "RunScopedRepository"
Cohesion: 0.22
Nodes (14): BondPosition, InvestmentMovement, LedgerEntry, RunScopedRepository, bond(), ledger(), linked(), test_bind_types_reject_precision_or_timezone_loss() (+6 more)

### Community 11 - "persistence/models.py"
Cohesion: 0.16
Nodes (12): Cents, exact(), ExactNumeric, market_args(), money(), position_args(), PositionLinked, PositionValuation (+4 more)

### Community 12 - "MEMBER_2_SPEC.md"
Cohesion: 0.11
Nodes (18): 10. SIMULATION INITIALIZATION, 1. YOUR ROLE AND MISSION, 25. FASTAPI CONTRACT, 27. API ERROR HANDLING, 32. DOCKER AND ENVIRONMENT MANAGEMENT, 33. PERFORMANCE REQUIREMENTS, 36. EARLY HANDOFF TO MEMBER 3, 38. BACKEND DEMONSTRATION REQUIREMENT (+10 more)

### Community 13 - "SimulationRun"
Cohesion: 0.22
Nodes (8): SimulationRun, configuration_identity(), RunRepository, Integrity and repository contract, test_internal_errors_use_safe_envelope(), historical_run(), runs(), test_run_source_and_configuration_contract()

### Community 14 - "Base"
Cohesion: 0.36
Nodes (11): CashAccount, EquityPosition, LiquidityBreach, MarketPosition, OverdraftLiability, OverdraftMovement, PortfolioValuation, RepoPosition (+3 more)

### Community 15 - "repositories.py"
Cohesion: 0.23
Nodes (3): DatasetSource, OrganizerObservation, DatasetRepository

### Community 16 - "24. DATABASE DESIGN"
Cohesion: 0.17
Nodes (12): 24. DATABASE DESIGN, Database requirements, Table 10 — backtest_results, Table 1 — simulation_runs, Table 2 — transactions, Table 3 — ledger_entries, Table 4 — vault_positions, Table 5 — vault_movements (+4 more)

### Community 17 - "42. FINAL DELIVERABLES"
Cohesion: 0.17
Nodes (12): 42. FINAL DELIVERABLES, A. Implementation summary, B. Database schema, C. Backend API documentation, D. Transaction simulator documentation, E. Ledger documentation, F. Backtesting documentation, G. Integration instructions for Member 1 (+4 more)

### Community 18 - "HourlyObservation"
Cohesion: 0.27
Nodes (5): HourlyObservation, test_invalid_boolean_flags(), test_invalid_financial_domains(), test_invalid_or_reinterpreted_timestamps(), test_invalid_source_numbers()

### Community 19 - "organizer.py"
Cohesion: 0.15
Nodes (8): _configured_path(), DatasetMetadata, DatasetValidation, _exact_total(), FrozenModel, ReconciliationSummary, ValidationIssue, Organizer treasury CSV (authoritative hourly source)

### Community 20 - "31. FINANCIAL INVARIANTS"
Cohesion: 0.18
Nodes (11): 31. FINANCIAL INVARIANTS, Invariant 10 — Strategy isolation, Invariant 1 — Principal conservation, Invariant 2 — Interest accounting, Invariant 3 — No double execution, Invariant 4 — No free liquidity, Invariant 5 — Honest payout status, Invariant 6 — Accurate borrowing costs (+3 more)

### Community 21 - "35. PARALLEL DEVELOPMENT RULES"
Cohesion: 0.18
Nodes (11): 35. PARALLEL DEVELOPMENT RULES, Rule 1, Rule 10, Rule 2, Rule 3, Rule 4, Rule 5, Rule 6 (+3 more)

### Community 22 - "40. JUDGE-READY TECHNICAL EXPLANATIONS"
Cohesion: 0.18
Nodes (11): 40. JUDGE-READY TECHNICAL EXPLANATIONS, Are these actual bank transactions?, How are transactions generated?, How do you compare against baselines?, How do you measure financial performance?, How do you prevent misleading results?, How does the system simulate real time?, How is a sweep executed? (+3 more)

### Community 23 - "GRAPHIFY — MANDATORY PROJECT KNOWLEDGE GRAPH"
Cohesion: 0.22
Nodes (8): GIT MILESTONE RULE — MANDATORY, Graphify accuracy rule, GRAPHIFY — MANDATORY PROJECT KNOWLEDGE GRAPH, Important, Initial setup, Milestone examples, Project Rules and Guidelines, Regular updates

### Community 24 - "21. STRESS SCENARIO ENGINE"
Cohesion: 0.22
Nodes (9): 21. STRESS SCENARIO ENGINE, HIGH_WITHDRAWAL, LIQUIDITY_SHOCK, LOW_DEPOSIT, Mid-run scenario application, NORMAL, Scenario implementation rule, SETTLEMENT_DELAY (+1 more)

### Community 25 - "34. MEMBER 2 DEVELOPMENT TIMELINE"
Cohesion: 0.22
Nodes (9): 34. MEMBER 2 DEVELOPMENT TIMELINE, Hours 0–1 — Contract and Repository Setup, Hours 10–14 — Backtesting and Member 1 Integration, Hours 14–18 — Advanced Metrics and Reliability, Hours 18–21 — Final Integration, Hours 1–4 — Transaction and Ledger Foundation, Hours 21–24 — Feature Freeze, Hours 4–7 — Simulation and API (+1 more)

### Community 26 - "41. DEFINITION OF DONE"
Cohesion: 0.22
Nodes (9): 41. DEFINITION OF DONE, API, Database, Evaluation, Integration, Simulation engine, Stress testing, Transaction engine (+1 more)

### Community 27 - "12. TRANSACTION DISTRIBUTION MODEL"
Cohesion: 0.29
Nodes (7): 12. TRANSACTION DISTRIBUTION MODEL, Deposit distribution, Merchant settlements, Randomness, Time-of-day behavior, Transaction volume, Withdrawal distribution

### Community 28 - "23. FINANCIAL PERFORMANCE METRICS"
Cohesion: 0.29
Nodes (7): 23. FINANCIAL PERFORMANCE METRICS, Baseline comparison, Core financial metric, Liquidity metrics, Transaction metrics, Treasury activity metrics, Yield metrics

### Community 29 - "GRAPHIFY — MANDATORY PROJECT KNOWLEDGE GRAPH"
Cohesion: 0.33
Nodes (5): Graphify accuracy rule, GRAPHIFY — MANDATORY PROJECT KNOWLEDGE GRAPH, Important, Initial setup, Regular updates

### Community 30 - "Four-tier persistence foundation (Milestone 2)"
Cohesion: 0.33
Nodes (5): Applying and verifying migrations, Authoritative storage, Deliberate boundaries / remaining contracts, Four-tier persistence foundation (Milestone 2), Precision and time

### Community 31 - "11. SYNTHETIC TRANSACTION GENERATOR"
Cohesion: 0.33
Nodes (6): 11. SYNTHETIC TRANSACTION GENERATOR, A. DEPOSIT, B. WITHDRAWAL, C. MERCHANT_SETTLEMENT, Required behavior, Required transaction fields

### Community 32 - "16. YIELD VAULT LEDGER"
Cohesion: 0.33
Nodes (6): 16. YIELD VAULT LEDGER, Creating a vault position, Interest accounting, Interest calculation, Maturity processing, Required position fields

### Community 33 - "18. EMERGENCY LIQUIDITY AND PAYOUT FAILURES"
Cohesion: 0.33
Nodes (6): 18. EMERGENCY LIQUIDITY AND PAYOUT FAILURES, Emergency borrowing configuration, Important metrics, Scenario A — Sufficient checking, Scenario B — Checking insufficient, emergency borrowing allowed, Scenario C — Funding unavailable

### Community 34 - "22. STRATEGY BACKTESTING"
Cohesion: 0.33
Nodes (6): 22. STRATEGY BACKTESTING, Critical fairness rule, Recommended implementation, Strategy A — STATIC RESERVE, Strategy B — REACTIVE RESERVE, Strategy C — RESERVE JUGGLER

### Community 35 - "26. API REQUEST AND RESPONSE EXAMPLES"
Cohesion: 0.33
Nodes (6): 26. API REQUEST AND RESPONSE EXAMPLES, A. Create Simulation, B. Advance Simulation, C. Apply Scenario, D. Treasury Snapshot, E. Backtest Result

### Community 36 - "19. SIMULATION STEP EXECUTION"
Cohesion: 0.40
Nodes (5): 19. SIMULATION STEP EXECUTION, Idempotency, Important financial detail, Important policy detail, Required execution sequence

### Community 37 - "37. EARLY HANDOFF TO MEMBER 1"
Cohesion: 0.40
Nodes (5): 37. EARLY HANDOFF TO MEMBER 1, Configurable policy, Execution feedback, Historical data, Treasury context

### Community 38 - "15. CHECKING ACCOUNT LEDGER"
Cohesion: 0.50
Nodes (4): 15. CHECKING ACCOUNT LEDGER, Concurrency safety, Financial correctness, Required ledger entry information

### Community 39 - "17. EARLY VAULT REDEMPTION"
Cohesion: 0.50
Nodes (4): 17. EARLY VAULT REDEMPTION, Configurable parameters, Early redemption sequence, Important rule

### Community 40 - "20. INTEGRATION WITH MEMBER 1"
Cohesion: 0.50
Nodes (4): 20. INTEGRATION WITH MEMBER 1, Create a treasury adapter, Fallback implementation, Final integration

### Community 41 - "28. BACKTEST IMPLEMENTATION DETAILS"
Cohesion: 0.50
Nodes (4): 28. BACKTEST IMPLEMENTATION DETAILS, Backtesting outputs, Fair comparison, No lookahead

### Community 42 - "29. FRONTEND INTEGRATION SUPPORT"
Cohesion: 0.50
Nodes (4): 29. FRONTEND INTEGRATION SUPPORT, Early deliverable, Integration strategy, Live dashboard updates

### Community 43 - "2. PROJECT PROBLEM STATEMENT"
Cohesion: 0.50
Nodes (4): 2. PROJECT PROBLEM STATEMENT, Checking Account, Financial Problem, Yield Vault

### Community 44 - "6. YOUR EXACT RESPONSIBILITIES"
Cohesion: 0.50
Nodes (4): 6. YOUR EXACT RESPONSIBILITIES, P0 — Mandatory Features, P1 — Competitive Enhancements, P2 — Only After P0 and P1 Are Stable

### Community 45 - "PULL_REQUEST_TEMPLATE.md"
Cohesion: 0.50
Nodes (3): 1. Workstream Area, 2. Changes Summary, 3. Verification Checklist

### Community 48 - "13. HISTORICAL DATA GENERATION"
Cohesion: 0.67
Nodes (3): 13. HISTORICAL DATA GENERATION, Critical requirement, Historical cash-flow bucket

### Community 49 - "Decimal"
Cohesion: 0.24
Nodes (6): _exact_difference(), Current source identity, Organizer historical data foundation, Provenance and diagnostics, Read and validate, Schema, precision, and immutability

### Community 50 - "14. REAL-TIME TRANSACTION AGGREGATOR"
Cohesion: 0.67
Nodes (3): 14. REAL-TIME TRANSACTION AGGREGATOR, Core formula, Important distinction

### Community 53 - "MEMBER 2 — COMPLETE DEVELOPMENT AGENT PROMPT"
Cohesion: 0.67
Nodes (3): HackForge 2026 | 24-Hour Hackathon | Developer 2 of 3, MEMBER 2 — COMPLETE DEVELOPMENT AGENT PROMPT, Reserve Juggler — Real-Time Simulation, Banking Ledger, Backend API & Performance Evaluation

## Knowledge Gaps
- **247 isolated node(s):** `name`, `private`, `version`, `type`, `dev` (+242 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 363 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **13 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `main()` connect `README.md` to `sync-persistence-graph.py`?**
  _High betweenness centrality (0.321) - this node is a cross-community bridge._
- **Why does `5. EXISTING PROJECT ENVIRONMENT` connect `README.md` to `MEMBER_2_SPEC.md`?**
  _High betweenness centrality (0.270) - this node is a cross-community bridge._
- **Why does `19. SIMULATION STEP EXECUTION` connect `19. SIMULATION STEP EXECUTION` to `MEMBER_2_SPEC.md`?**
  _High betweenness centrality (0.097) - this node is a cross-community bridge._
- **Are the 8 inferred relationships involving `HourlyObservation` (e.g. with `DatasetRepository` and `Schema, precision, and immutability`) actually correct?**
  _`HourlyObservation` has 8 INFERRED edges - model-reasoned connections that need verification._
- **Are the 12 inferred relationships involving `RunScopedRepository` (e.g. with `SimulationRun` and `Integrity and repository contract`) actually correct?**
  _`RunScopedRepository` has 12 INFERRED edges - model-reasoned connections that need verification._
- **What connects `name`, `private`, `version` to the rest of the system?**
  _247 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `TreasuryDecisionEngine` be split into smaller, more focused modules?**
  _Cohesion score 0.07419712070874862 - nodes in this community are weakly interconnected._
