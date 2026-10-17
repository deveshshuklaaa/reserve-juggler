# Graph Report - reserve-juggler  (2026-10-17)

## Corpus Check
- Corpus is ~8,882 words - fits in a single context window. You may not need a graph.

## Summary
- 151 nodes · 279 edges · 15 communities (7 shown, 8 thin omitted)
- Extraction: 95% EXTRACTED · 5% INFERRED · 0% AMBIGUOUS · INFERRED: 15 edges (avg confidence: 0.95)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- engine.py / datetime
- database.py / get_db()
- package.json / dependencies
- models.py / DecisionModel
- schemas.py / Decision
- Any / Expected Liquidity Requirement + Forecast Uncertainty + Operational Safety…
- client.js / fetchHealth()
- config.py / Settings
- get_recent_transactions() / get

## God Nodes (most connected - your core abstractions)
1. `TreasuryDecisionEngine` - 12 edges
2. `TransactionGenerator` - 12 edges
3. `CashFlowForecaster` - 10 edges
4. `App()` - 8 edges
5. `get_treasury_state()` - 6 edges
6. `get_db()` - 5 edges
7. `DecisionModel` - 5 edges
8. `SimulationRunModel` - 5 edges
9. `start_simulation()` - 5 edges
10. `get_current_liquidity()` - 5 edges

## Surprising Connections (you probably didn't know these)
- `test_hold_decision_in_corridor()` --uses--> `TreasuryDecisionEngine`  [INFERRED]
  tests/backend/test_decision_engine.py → backend/app/treasury/engine.py
- `test_liquidity_warning_on_extreme_insolvency()` --uses--> `TreasuryDecisionEngine`  [INFERRED]
  tests/backend/test_decision_engine.py → backend/app/treasury/engine.py
- `test_required_reserve_calculation()` --uses--> `TreasuryDecisionEngine`  [INFERRED]
  tests/backend/test_decision_engine.py → backend/app/treasury/engine.py
- `test_sweep_decision_on_excess_cash()` --uses--> `TreasuryDecisionEngine`  [INFERRED]
  tests/backend/test_decision_engine.py → backend/app/treasury/engine.py
- `test_withdraw_decision_on_liquidity_deficit()` --uses--> `TreasuryDecisionEngine`  [INFERRED]
  tests/backend/test_decision_engine.py → backend/app/treasury/engine.py

## Import Cycles
- None detected.

## Communities (15 total, 8 thin omitted)

### Community 0 - "engine.py / datetime"
Cohesion: 0.11
Nodes (8): CashFlowForecaster, TransactionGenerator, test_forecaster_baseline(), test_forecaster_with_transactions(), test_end_to_end_pipeline(), test_generator_baseline_event(), test_generator_deposit_run(), test_generator_payroll_spike()

### Community 1 - "database.py / get_db()"
Cohesion: 0.14
Nodes (6): get_db(), root(), get_health(), get_simulation_results(), start_simulation(), update_scenario()

### Community 2 - "package.json / dependencies"
Cohesion: 0.12
Nodes (16): dependencies, react, react-dom, devDependencies, vite, @vitejs/plugin-react, name, private (+8 more)

### Community 3 - "models.py / DecisionModel"
Cohesion: 0.33
Nodes (11): DecisionModel, ForecastModel, LiquiditySnapshotModel, SimulationRunModel, TransactionModel, get_current_forecast(), get_current_liquidity(), get_decisions_history() (+3 more)

### Community 4 - "schemas.py / Decision"
Cohesion: 0.23
Nodes (13): Decision, Forecast, ForecastBase, HealthStatus, LiquiditySnapshot, ScenarioConfigRequest, SimulationRun, SimulationStartRequest (+5 more)

### Community 5 - "Any / Expected Liquidity Requirement + Forecast Uncertainty + Operational Safety…"
Cohesion: 0.20
Nodes (6): TreasuryDecisionEngine, test_hold_decision_in_corridor(), test_liquidity_warning_on_extreme_insolvency(), test_required_reserve_calculation(), test_sweep_decision_on_excess_cash(), test_withdraw_decision_on_liquidity_deficit()

### Community 6 - "client.js / fetchHealth()"
Cohesion: 0.36
Nodes (9): fetchHealth(), fetchMetrics(), fetchRecentTransactions(), fetchTreasuryState(), setSimulationScenario(), App(), loadData(), react (+1 more)

## Knowledge Gaps
- **11 isolated node(s):** `name`, `private`, `version`, `type`, `dev` (+6 more)
  These have ≤1 connection - possible missing edges. (Counts symbols only; 50 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **8 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `TreasuryDecisionEngine` connect `Any / Expected Liquidity Requirement + Forecast Uncertainty + Operational Safety…` to `engine.py / datetime`, `models.py / DecisionModel`?**
  _High betweenness centrality (0.119) - this node is a cross-community bridge._
- **Are the 6 inferred relationships involving `TreasuryDecisionEngine` (e.g. with `test_hold_decision_in_corridor()` and `test_liquidity_warning_on_extreme_insolvency()`) actually correct?**
  _`TreasuryDecisionEngine` has 6 INFERRED edges - model-reasoned connections that need verification._
- **What connects `name`, `private`, `version` to the rest of the system?**
  _11 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `engine.py / datetime` be split into smaller, more focused modules?**
  _Cohesion score 0.1103448275862069 - nodes in this community are weakly interconnected._
- **Should `database.py / get_db()` be split into smaller, more focused modules?**
  _Cohesion score 0.13768115942028986 - nodes in this community are weakly interconnected._
- **Should `package.json / dependencies` be split into smaller, more focused modules?**
  _Cohesion score 0.11764705882352941 - nodes in this community are weakly interconnected._