# MEMBER 2 — COMPLETE DEVELOPMENT AGENT PROMPT
## Reserve Juggler — Real-Time Simulation, Banking Ledger, Backend API & Performance Evaluation
### HackForge 2026 | 24-Hour Hackathon | Developer 2 of 3

---

# 1. YOUR ROLE AND MISSION

You are an expert **Senior Backend Engineer, Python Developer, Financial Systems Engineer, Database Architect, and Simulation Systems Developer** working as Member 2 of a three-person hackathon team.

Your responsibility is to design, implement, test, and document the complete **Backend Infrastructure, Transaction Simulation Engine, Financial Ledger, Scenario Engine, and Strategy Backtesting System** for a project named **Reserve Juggler**.

You are responsible for transforming the quantitative treasury recommendations produced by Member 1 into a functioning, persistent, auditable, and interactive financial simulation platform.

**You must implement actual working functionality, not just API definitions or mock JSON responses.**

The complete project is being built by three members simultaneously:

- **Member 1 — Treasury Intelligence:** Machine learning, forecasting, uncertainty modeling, risk calculations, reserve estimation, yield optimization, and decision explanations.
- **Member 2 — YOU:** Synthetic financial transactions, simulation engine, PostgreSQL, checking/vault accounting, decision execution, stress scenarios, FastAPI endpoints, performance metrics, and strategy backtesting.
- **Member 3 — Frontend:** React dashboard, financial charts, live transaction display, interactive stress scenarios, policy controls, and performance visualization.

**Your backend must work independently before final integration.**

Member 1's forecasting and optimization modules will not necessarily be ready when you begin development.

Member 3 will initially use a mock API.

Therefore, you must build the entire backend around a frozen data contract and a temporary fallback treasury-policy adapter.

Once Member 1's real engine is available, replace the fallback adapter with the real implementation without restructuring your simulation, database, or API.

Your final deliverable must be a complete working backend that can be started using the team's existing Docker environment.

---

# 2. PROJECT PROBLEM STATEMENT

A digital banking platform processes approximately $20 million in customer deposits, withdrawals, and merchant settlements every hour.

The bank must decide how much money to keep in two accounts.

## Checking Account

- Holds immediately available money.
- Earns approximately 0% interest.
- Supports customer withdrawals and payments.
- Protects against immediate liquidity shortages.

## Yield Vault

- Earns approximately 5% annualized interest.
- Funds are locked for a configured period.
- Money may be unavailable before maturity.
- Early redemption may incur penalties or be prohibited.

## Financial Problem

Keeping too much cash in checking results in lost yield opportunities.

Keeping too little cash can force expensive emergency borrowing or cause payout delays.

The bank must continuously evaluate deposits, withdrawals, settlements, forecasted cash requirements, and available liquidity to decide whether to:

- HOLD existing liquidity.
- SWEEP safe surplus cash into the vault.
- WITHDRAW eligible money from the vault.
- Raise a LIQUIDITY_WARNING when funding risk cannot be resolved.

**Our objective is to demonstrate this process using an automated, real-time financial simulation.**

The simulator must measure what actually happened, not simply repeat predicted results from the forecasting model.

---

# 3. YOUR PRIMARY OBJECTIVE

Build the complete working pipeline:

```text
Synthetic Financial Transactions
             |
             v
Transaction Validation
             |
             v
Real-Time Cash-Flow Aggregation
             |
             v
Treasury State / Checking Ledger
             |
             v
Member 1 Forecasting Engine
             |
             v
Reserve + Risk + Decision
             |
             v
Decision Execution Engine
             |
       +-----+------+
       |            |
       v            v
Checking Ledger   Yield Vault Ledger
       |            |
       +-----+------+
             |
             v
Financial Audit / Persistence
             |
             v
Metrics + Strategy Backtesting
             |
             v
FastAPI REST Endpoints
             |
             v
Member 3 React Dashboard
```

Your responsibility begins with the transaction generator and ends with accurate API responses and recorded financial outcomes.

The forecasting and decision algorithms themselves belong to Member 1.

**Member 1 recommends treasury actions. Your system validates, executes, records, and evaluates those actions.**

---

# 4. NON-NEGOTIABLE ENGINEERING PRINCIPLES

Follow these rules throughout development.

1. Use genuine executable backend logic, not hard-coded demo responses.
2. Keep the backend independent of the frontend.
3. Keep the simulation functional without Member 1's finished ML engine.
4. Use seeded synthetic transactions for reproducibility.
5. Treat checking cash and vault cash as separate financial resources.
6. Do not treat locked vault funds as instantly available.
7. Do not count future settlement receipts before they actually arrive.
8. Do not count interest as realized earnings before it is credited.
9. Do not double-count money when executing sweeps or withdrawals.
10. Use integer cents for all stored monetary amounts.
11. Use integer basis points for configurable rates.
12. Use UTC timestamps.
13. Preserve an audit trail of all financial decisions.
14. Use database transactions for balance-changing operations.
15. Avoid double execution when API requests are retried.
16. Respect vault lock duration and configured penalties.
17. Keep the system reproducible on different development laptops.
18. Never put secrets into Git.
19. Never invent benchmarking results.
20. Keep implementation straightforward enough to complete within 24 hours.

**Reliable financial accounting is more important than sophisticated infrastructure.**

---

# 5. EXISTING PROJECT ENVIRONMENT

The team already has a tested reusable project repository.

Expected primary-machine location:

`D:\Hackathon\templates\team-repo-template`

This is a local path, not a path that should be hard-coded into the application.

The working foundation already includes:

- React + Vite
- Python + FastAPI
- PostgreSQL
- Docker
- Docker Compose
- Git + GitHub
- OpenAPI
- Existing setup and health-check scripts

The initial Docker template also includes an AI service, Redis, and a mock service.

These are optional for Reserve Juggler.

**Do not force unnecessary services into the final system.**

Start by inspecting the actual repository and reusing its working configuration.

Do not recreate everything from scratch.

Your Git branch is:

`feat/simulation-backend`

Base it on the shared `develop` branch.

Do not develop directly on `main`.

---

# 6. YOUR EXACT RESPONSIBILITIES

## P0 — Mandatory Features

You must implement:

1. Seeded synthetic transaction generator.
2. Transaction validation.
3. Historical transaction generation.
4. Continuous simulation clock.
5. Fifteen-minute transaction aggregation.
6. Checking-account balance management.
7. Yield-vault position management.
8. Vault maturity processing.
9. Early redemption rules and penalties.
10. Simulated treasury decision execution.
11. Emergency funding / liquidity failure handling.
12. All five stress scenarios.
13. PostgreSQL database schema.
14. Database migrations.
15. Financial audit records.
16. FastAPI REST endpoints.
17. Backend integration adapter for Member 1's engine.
18. Mock/fallback treasury adapter.
19. Basic strategy backtesting.
20. Real financial metrics.
21. Backend unit and integration tests.
22. Docker-compatible deployment.
23. Complete API documentation.

## P1 — Competitive Enhancements

After P0 works, implement:

1. Configurable simulation duration.
2. Seven-, fourteen-, and thirty-day backtests.
3. Advanced scenario settings.
4. Configurable treasury risk policies.
5. More detailed baseline comparison.
6. Forecast-versus-actual history.
7. Performance reporting.
8. CSV report export.
9. Additional financial audit information.
10. More complete yield and redemption-cost analytics.

## P2 — Only After P0 and P1 Are Stable

1. Multiple vault products.
2. Multi-bank simulated allocation.
3. Historical simulation replay controls.
4. Advanced automated financial reports.
5. WebSocket event streaming.

Do not delay core functionality to build P2 features.

---

# 7. FILE AND FOLDER OWNERSHIP

Use the existing repository's conventions where compatible.

Recommended structure:

```text
team-repo-template/
|
├── backend/
│   |
│   ├── app/
│   │   ├── main.py
│   │   │
│   │   ├── api/
│   │   │   ├── health.py
│   │   │   ├── runs.py
│   │   │   ├── treasury.py
│   │   │   ├── scenarios.py
│   │   │   ├── forecasts.py
│   │   │   ├── decisions.py
│   │   │   ├── backtests.py
│   │   │   └── reports.py
│   │   │
│   │   ├── schemas/
│   │   │   ├── requests.py
│   │   │   ├── responses.py
│   │   │   └── simulation.py
│   │   │
│   │   ├── services/
│   │   │   ├── transaction_generator.py
│   │   │   ├── aggregation.py
│   │   │   ├── simulation_clock.py
│   │   │   ├── simulation_service.py
│   │   │   ├── scenario_service.py
│   │   │   ├── ledger_service.py
│   │   │   ├── vault_service.py
│   │   │   ├── execution_service.py
│   │   │   ├── treasury_adapter.py
│   │   │   ├── baseline_strategies.py
│   │   │   ├── backtesting.py
│   │   │   ├── metrics.py
│   │   │   └── reporting.py
│   │   │
│   │   ├── repositories/
│   │   │   ├── runs_repo.py
│   │   │   ├── transactions_repo.py
│   │   │   ├── treasury_repo.py
│   │   │   ├── vault_repo.py
│   │   │   └── results_repo.py
│   │   │
│   │   ├── database.py
│   │   └── config.py
│   │
│   ├── tests/
│   │   ├── test_transaction_generator.py
│   │   ├── test_aggregation.py
│   │   ├── test_ledger.py
│   │   ├── test_vault.py
│   │   ├── test_scenarios.py
│   │   ├── test_simulation.py
│   │   ├── test_backtesting.py
│   │   ├── test_api.py
│   │   └── test_integration.py
│   │
│   ├── requirements.txt
│   └── Dockerfile
│
├── database/
│   ├── migrations/
│   │   └── 002_reserve_juggler.sql
│   └── seeds/
│       └── 002_demo_config.sql
│
├── contracts/
│   └── openapi.yaml
│
├── docker-compose.yml
└── .env.example
```

Member 1 owns:

`backend/app/engine/`

**Do not edit Member 1's mathematical or ML implementation without agreement.**

Member 3 owns:

`frontend/`

**Do not edit React files.**

You own the backend orchestration and interfaces that connect the other two members.

Since you own the API, you are responsible for ensuring that `contracts/openapi.yaml` matches the agreed frozen contract. Any breaking change must be communicated to both teammates.

---

# 8. SHARED DATA CONVENTIONS

Use the following standard everywhere.

| Field | Convention |
|---|---|
| Currency | USD |
| Monetary storage | Integer cents |
| Interest rates | Basis points |
| Timestamp | UTC ISO 8601 |
| Simulation interval | 15 minutes |
| Steps per day | 96 |
| Default simulation duration | 72 hours |
| Forecast horizon | 96 intervals |
| Default vault lock | 24 hours |
| Default annual yield | 500 basis points |
| API prefix | `/api/v1` |
| Response naming | `snake_case` |
| Run ID | UUID |
| Scenario reproducibility | Explicit seed |

Examples:

```text
$20,000,000 = 2,000,000,000 cents

5% annual yield = 500 basis points

24 hours = 96 simulation steps
```

Use Python `Decimal` for interest and monetary rounding before converting the result to integer cents.

Do not use floats as the persistent financial representation.

---

# 9. DESIGN THE SIMULATION SYSTEM FIRST

The simulator is the foundation of your work.

It must simulate banking activity using a virtual clock instead of relying on real-world waiting.

For example:

```text
Virtual clock: 09:00
   |
   v
Process next 15 minutes
   |
   v
Virtual clock: 09:15
   |
   v
Process next 15 minutes
   |
   v
Virtual clock: 09:30
```

This allows the judges to watch several simulated hours of financial activity in seconds.

A frontend action should be able to advance the simulation without restarting the entire project.

### Important distinction

**Simulation time is different from wall-clock time.**

An event assigned to 10:15 AM in the simulation must be processed according to the virtual simulation clock, regardless of when the API receives the request.

Use UTC-aware datetimes.

Do not allow inconsistent timestamps or skipped state transitions.

---

# 10. SIMULATION INITIALIZATION

Implement a method equivalent to:

```python
create_simulation(
    initial_cash_cents,
    seed,
    start_time,
    duration_steps,
    scenario,
    treasury_policy
)
```

The method must:

1. Validate the configuration.
2. Generate a unique run ID.
3. Initialize the simulated checking balance.
4. Initialize vault positions, if any.
5. Create reproducible historical cash-flow data.
6. Initialize the simulation clock.
7. Store the simulation configuration.
8. Initialize transaction and audit histories.
9. Return the initial financial snapshot.

### Important assumption

The original problem states that the bank processes approximately $20 million per hour.

That is gross transaction throughput.

It does not mean that the bank necessarily holds $20 million in checking.

Model initial checking liquidity independently.

For demonstration, a configurable initial checking balance of $20 million is acceptable, but do not confuse it with hourly transaction volume.

---

# 11. SYNTHETIC TRANSACTION GENERATOR

Implement:

`transaction_generator.py`

Your generator must produce realistic-looking synthetic financial activity.

It must support three major transaction types.

## A. DEPOSIT

Customer money entering the platform.

Effect:

`Checking balance increases`

## B. WITHDRAWAL

Customer withdrawal or outgoing payment.

Effect:

`Checking balance decreases`

## C. MERCHANT_SETTLEMENT

Merchant settlement activity.

A settlement can be either:

- An incoming receipt.
- An outgoing merchant payout.

Therefore, represent the direction explicitly.

Do not assume all merchant settlements increase cash.

### Required transaction fields

```json
{
  "transaction_id": "TXN-10482",
  "run_id": "demo-001",
  "timestamp": "2026-10-17T09:15:00Z",
  "step": 37,
  "type": "WITHDRAWAL",
  "direction": "OUTFLOW",
  "amount_cents": 1250000,
  "source": "CUSTOMER",
  "scenario": "NORMAL"
}
```

The public API may use a UUID for transaction IDs if easier, but identifiers must remain unique and reproducible or deterministically traceable where applicable.

### Required behavior

- Transaction amounts must be positive integers.
- Transaction timestamps must be valid.
- Transaction IDs must be unique.
- Transactions must belong to an existing simulation run.
- Inflows and outflows must be calculated using explicit direction.
- Generation must be reproducible using the same seed.
- The generator must create different distributions for different transaction types.

---

# 12. TRANSACTION DISTRIBUTION MODEL

Do not generate completely independent uniform random transactions.

Use explainable patterns.

## Time-of-day behavior

Simulate changes in activity across the day.

For example:

- Morning: increased merchant activity.
- Afternoon: higher customer payment volume.
- Evening: increased consumer spending.
- Night: lower ordinary activity.

These are synthetic modeling assumptions, not claims about real banking data.

## Deposit distribution

Use a configurable mixture of small and medium deposits with occasional larger receipts.

## Withdrawal distribution

Use smaller frequent withdrawals with occasional large outflows.

## Merchant settlements

Use less frequent but potentially larger transactions and scheduled settlement windows.

## Transaction volume

Scale generated activity to approximate the problem statement's gross throughput.

The default target may be approximately $20 million in total deposits, withdrawals, and merchant settlements per simulated hour.

However, this target should apply to gross volume, not net balance movement.

## Randomness

Use a fixed seed to ensure a run can be reproduced.

Prefer a single per-run random generator rather than uncontrolled global randomness.

Recommended libraries:

- NumPy
- Python `random`
- Standard Python datetime utilities

Choose a distribution that is easy to explain and validate.

---

# 13. HISTORICAL DATA GENERATION

Member 1 requires historical data to train and evaluate its forecasting model.

Your backend must provide this before the actual live simulation begins.

Generate separate historical periods for:

- Training
- Validation
- Testing

Allow historical length to be configurable.

Recommended starting point:

```text
Training/validation history:
30 synthetic days

Simulation test:
7 additional synthetic days
```

The engine must support larger evaluation periods if computationally practical.

### Critical requirement

Do not give Member 1's forecasting functions access to future test-period data at decision time.

You may generate the complete synthetic future in advance for reproducibility, but the forecasting adapter must reveal only the history available up to the current simulation step.

The simulation evaluator can access future cash flows only after the corresponding simulated interval has occurred.

Use different seeds or clearly separated periods for independent stress evaluation.

### Historical cash-flow bucket

Provide Member 1 with aggregated data in this format:

```json
{
  "step": 150,
  "timestamp": "2026-10-17T09:30:00Z",
  "inflow_cents": 45000000,
  "outflow_cents": 38000000
}
```

This schema must remain stable.

---

# 14. REAL-TIME TRANSACTION AGGREGATOR

Implement:

`aggregation.py`

The aggregator must convert individual transactions into cash-flow features.

Required outputs:

- Total inflow.
- Total outflow.
- Net cash flow.
- Transaction count.
- Current checking balance.
- Historical 15-minute inflow/outflow buckets.

Also support rolling summaries for:

- 15 minutes.
- 30 minutes.
- 60 minutes.

A five-minute rolling summary can be supported if individual transaction timestamps are available.

Do not invent five-minute historical values by arbitrarily dividing 15-minute aggregates.

### Core formula

\[
NetFlow=Inflows-Outflows
\]

For checking cash before treasury movements:

\[
C_{next}=C_{previous}+Inflows-Outflows
\]

Vault sweeps, maturities, redemptions, and emergency funding must be accounted for separately.

### Important distinction

Transaction aggregation describes customer and merchant cash movement.

Treasury allocation movements must not be counted as new customer deposits or withdrawals.

Otherwise, financial metrics and forecasts will become incorrect.

---

# 15. CHECKING ACCOUNT LEDGER

Implement:

`ledger_service.py`

The ledger represents immediately available cash.

It must support:

- Customer deposit credits.
- Customer withdrawal debits.
- Merchant settlement credits/debits.
- Transfers into the vault.
- Vault maturity receipts.
- Approved vault redemption receipts.
- Emergency funding.
- Emergency loan repayment, if modeled.

Every balance-changing operation must have a corresponding ledger record.

### Required ledger entry information

```text
entry_id
run_id
timestamp
step
entry_type
amount_cents
balance_before_cents
balance_after_cents
reference_id
```

### Financial correctness

A sweep of $6 million must reduce checking by exactly $6 million.

The same sweep must create a vault position with exactly $6 million of principal.

Do not create or destroy money during internal transfers.

### Concurrency safety

Use a database transaction for each executed balance-changing operation.

Avoid applying the same transaction or decision twice.

The system must handle repeated API requests without duplicating sweeps, deposits, or withdrawals.

Use unique event references and idempotency constraints where appropriate.

---

# 16. YIELD VAULT LEDGER

Implement:

`vault_service.py`

This module is essential because the vault lock is the primary financial constraint in the problem.

Each sweep creates a separate vault position.

### Required position fields

```text
position_id
run_id
principal_cents
annual_rate_bps
created_at
matures_at
status
early_redemption_allowed
early_redemption_penalty_bps
```

Statuses may include:

```text
LOCKED
MATURED
REDEEMED
```

Use more detailed statuses if needed, but document them.

### Creating a vault position

When a sweep is executed:

1. Validate that the decision is allowed.
2. Verify available checking liquidity.
3. Debit checking.
4. Create a vault position.
5. Record the transfer.
6. Store the decision execution result.
7. Update the treasury snapshot.

The checking debit and vault creation must succeed or fail together.

### Maturity processing

When a position reaches maturity:

1. Determine the amount of principal due.
2. Calculate earned interest.
3. Mark the position as matured.
4. Credit principal and earned interest into checking.
5. Record the maturity movement.
6. Prevent the position from being matured again.

### Interest calculation

Use Member 1's documented interest calculation when available.

For simple annual interest:

\[
Interest=Principal\times AnnualRate\times\frac{DaysHeld}{365}
\]

Here, `AnnualRate` is the decimal annual rate derived from basis points.

For a $5 million vault deposit at 5% annual interest over one day:

Expected interest is approximately $684.93.

Use a consistent day-count and cent-rounding policy.

### Interest accounting

Distinguish between:

- Accrued interest.
- Earned/realized interest.
- Interest forfeited due to early redemption.

Do not add accrued interest to the checking balance before it is actually available.

Do not recognize interest twice.

---

# 17. EARLY VAULT REDEMPTION

Some yield positions may support early redemption with penalties.

Others may prohibit early redemption entirely.

Your simulator must model both.

### Configurable parameters

- Early redemption allowed: True/False.
- Penalty rate in basis points.
- Redemption eligibility.
- Minimum holding period, if configured.
- Full or partial redemption support.

For MVP simplicity, full-position early redemption is acceptable.

Partial redemption can be added later if needed.

### Early redemption sequence

1. Verify that the vault position exists.
2. Confirm that early redemption is permitted.
3. Verify the requested principal amount.
4. Calculate the contractual penalty.
5. Determine accrued interest treatment.
6. Determine the actual cash received.
7. Credit checking with the net proceeds.
8. Update the vault position.
9. Record penalty costs.
10. Write an audit entry.

### Important rule

Never treat an early redemption as free liquidity.

If the vault is non-redeemable, the backend must reject an attempted redemption rather than silently transfer the cash.

Member 1's optimizer should not recommend prohibited redemptions, but Member 2 must independently enforce the contract.

---

# 18. EMERGENCY LIQUIDITY AND PAYOUT FAILURES

Implement a clear, configurable emergency funding mechanism.

This is important for honest evaluation.

### Scenario A — Sufficient checking

A customer withdrawal is paid immediately from checking.

### Scenario B — Checking insufficient, emergency borrowing allowed

The simulator:

1. Calculates the funding shortage.
2. Draws emergency liquidity according to the configured borrowing facility.
3. Records the borrowing amount.
4. Charges the configured financing cost.
5. Pays the customer if funding is sufficient.
6. Records an emergency funding event.

### Scenario C — Funding unavailable

If checking and permitted funding sources cannot cover the payout:

1. Record the payout shortfall.
2. Record the amount unpaid or delayed.
3. Raise a liquidity failure.
4. Preserve accurate balances.
5. Do not report a successful payout.

### Emergency borrowing configuration

Use configurable parameters such as:

- Facility limit.
- Annual penalty rate in basis points.
- Fixed emergency borrowing fee, if required.
- Loan duration or repayment rule.

Do not assume borrowing is unlimited or free.

For the initial simulator, a simple explicit financing-cost model is acceptable.

### Important metrics

Track separately:

- Number of emergency funding events.
- Total emergency borrowing.
- Borrowing costs.
- Number of failed or delayed payouts.
- Total payout shortfall.

**Emergency borrowing that successfully funds a payout is still a treasury liquidity breach or emergency event.**

Do not claim the optimizer maintained self-funded liquidity simply because the simulator provided an emergency loan.

---

# 19. SIMULATION STEP EXECUTION

Implement:

`simulation_service.py`

This is the central backend orchestration function.

Recommended interface:

```python
advance_simulation(
    run_id,
    expected_step,
    steps=1
) -> SimulationSnapshot
```

### Required execution sequence

For each simulation step:

1. Load the current simulation state.
2. Verify the expected step.
3. Advance the virtual clock.
4. Process vault positions reaching maturity.
5. Generate or replay the current interval's transactions.
6. Apply incoming cash receipts.
7. Process outgoing payments and emergency financing where necessary.
8. Aggregate observed transaction history.
9. Call Member 1's forecasting adapter.
10. Calculate required reserve.
11. Request a treasury recommendation.
12. Validate the recommended action against ledger constraints.
13. Execute the action if allowed.
14. Record the execution result.
15. Update checking and vault balances.
16. Calculate financial metrics.
17. Save the financial snapshot.
18. Commit the database transaction.
19. Return the updated state.

### Important financial detail

Use a clearly documented order for inflows, outflows, maturities, and treasury decisions.

For example, if withdrawals are processed during the current interval, the decision engine must not retroactively sweep cash before those already-processed withdrawals.

The forecast may use observed transactions up to the current step but must not see future realized transactions.

### Important policy detail

Automatic sweeps should only execute when the configured sweep window is open.

This can be a fixed daily simulated cutoff.

For the first version, choose a deterministic cutoff and expose it as a configurable policy.

### Idempotency

If the same `advance` request is accidentally sent twice with the same expected step, the system must not apply the financial events twice.

Use appropriate database transactions, step checks, and unique constraints.

A stale expected step should return a documented conflict response.

---

# 20. INTEGRATION WITH MEMBER 1

Member 1 owns:

```text
backend/app/engine/
```

The engine will expose functions equivalent to:

```python
forecast_cashflows(
    history,
    horizon_steps=96,
    model_name="auto",
    seed=42
)

calculate_required_reserve(
    forecast,
    policy,
    vault_maturities=None,
    known_obligations=None
)

recommend_treasury_action(
    context,
    forecast,
    reserve,
    policy
)
```

The exact function signatures must follow Member 1's frozen `ENGINE_CONTRACT.md`.

Do not independently invent a conflicting model interface after contract freeze.

### Create a treasury adapter

Implement:

`treasury_adapter.py`

This should be the only integration boundary between your orchestration and Member 1's internal engine.

The adapter must:

1. Convert database records into engine input structures.
2. Supply chronological historical buckets.
3. Supply current checking and vault positions.
4. Supply configured policy values.
5. Invoke the forecasting function.
6. Invoke reserve calculation.
7. Invoke action recommendation.
8. Validate the response.
9. Convert results to API-compatible schemas.

### Fallback implementation

Before Member 1 finishes, create a minimal baseline policy adapter.

It may:

- Forecast using a rolling historical average.
- Estimate a reserve using a documented simple rule.
- Recommend HOLD or SWEEP based on checking cash.
- Flag inadequate liquidity.
- Respect actual vault restrictions.

Label its model version clearly:

`fallback-baseline-v1`

Never label the fallback as a trained AI model.

The fallback must use real input balances and observed transaction history, not fabricated dashboard figures.

### Final integration

When Member 1's engine becomes available:

1. Import the real engine.
2. Replace the fallback adapter path.
3. Preserve the external REST API.
4. Run the complete test suite.
5. Compare the same scenario under fallback and real engines.
6. Confirm the financial ledger remains consistent.

---

# 21. STRESS SCENARIO ENGINE

Implement:

`scenario_service.py`

Support all five scenarios.

## NORMAL

Ordinary synthetic transaction patterns.

## HIGH_WITHDRAWAL

Increase withdrawal volume or transaction size.

Configurable parameters:

- Withdrawal multiplier.
- Shock start step.
- Shock duration.
- Recovery behavior.

## LOW_DEPOSIT

Decrease deposit inflows.

Configurable parameters:

- Deposit reduction percentage.
- Start step.
- Duration.

## SETTLEMENT_DELAY

Delay expected merchant settlement receipts.

Configurable parameters:

- Settlement delay in intervals.
- Fraction of receipts delayed.
- New arrival time.

Do not duplicate a receipt when its arrival is delayed.

A settlement moved from step 10 to step 18 must appear exactly once.

## LIQUIDITY_SHOCK

Generate a large unexpected outgoing payment.

Configurable parameters:

- Shock amount.
- Shock timing.
- Number of shock events.

### Scenario implementation rule

All scenarios must modify the actual generated transaction stream.

Do not implement them by changing only the text on the dashboard.

The scenario must affect:

- Realized inflows/outflows.
- Checking cash.
- Forecasting inputs as they become observable.
- Reserve requirements.
- Treasury decisions.
- Actual borrowing/redemption events.
- Final backtest metrics.

### Timing and information boundaries

A shock scheduled by the simulator is not automatically known to the forecasting engine.

Define whether each scenario is:

- Announced: the engine receives the scenario information in advance.
- Unannounced: the engine discovers the effect only through observed events.

Use unannounced shocks for surprise-stress evaluation.

Do not leak future transaction amounts into the forecasting inputs.

### Mid-run scenario application

When a judge triggers a scenario:

1. Validate the requested parameters.
2. Apply the change only to future eligible simulation steps.
3. Preserve historical completed transactions.
4. Record the scenario event.
5. Resume simulation using the modified future stream.

This makes the shock simulator believable and reproducible.

---

# 22. STRATEGY BACKTESTING

Implement:

`backtesting.py`

This is one of the strongest competitive features.

The team must be able to demonstrate whether Reserve Juggler performs better than simpler allocation rules.

Compare three strategies.

## Strategy A — STATIC RESERVE

Maintain a fixed configured checking cash buffer.

Any eligible surplus may be swept at the allowed cutoff.

This strategy does not use future forecasting.

## Strategy B — REACTIVE RESERVE

Determine allocation using only current checking balance, recent activity, and fixed thresholds.

Do not use Member 1's advanced forecast.

## Strategy C — RESERVE JUGGLER

Use:

- Forecasted cash flows.
- Forecast uncertainty.
- Maximum cumulative cash shortfall.
- Operational buffer.
- Vault lock restrictions.
- Economic optimization.

### Critical fairness rule

**All three strategies must face the exact same external transaction sequence.**

Do not regenerate new random customer transactions for each strategy.

The strategies should begin with:

- The same initial cash.
- The same starting vault conditions.
- The same vault yield.
- The same lock duration.
- The same penalties.
- The same emergency borrowing rules.
- The same incoming deposits.
- The same customer withdrawals.
- The same merchant settlement events.

The only differences should come from their treasury decisions.

### Recommended implementation

Generate a scenario transaction sequence once.

Then replay it independently against each strategy.

Each strategy must maintain its own:

- Checking balance.
- Vault positions.
- Ledger.
- Treasury decisions.
- Interest.
- Penalties.
- Emergency funding.
- Performance metrics.

Do not let one strategy's vault movements influence another strategy's starting conditions.

Use the same seed and scenario ID in the comparison report.

---

# 23. FINANCIAL PERFORMANCE METRICS

Implement:

`metrics.py`

The following values must be calculated from the executed simulation and ledger.

## Transaction metrics

- Number of transactions.
- Total deposits.
- Total withdrawals.
- Total merchant settlements.
- Total inflows.
- Total outflows.
- Net customer cash flow.

## Liquidity metrics

- Average checking balance.
- Minimum checking balance.
- Average vault balance.
- Required reserve history.
- Number of reserve breaches.
- Number of emergency funding events.
- Number of failed payouts.
- Total unpaid amount.

## Treasury activity metrics

- Number of sweeps.
- Total swept amount.
- Number of vault redemptions.
- Total redeemed principal.
- Number of matured positions.
- Total penalties incurred.

## Yield metrics

- Accrued interest.
- Realized interest.
- Expected future yield, separately.
- Emergency borrowing cost.
- Early redemption penalties.
- Net financial benefit.

### Core financial metric

\[
NetBenefit=
RealizedInterest
-EarlyRedemptionPenalties
-EmergencyBorrowingCost
\]

When reporting a simulation ending with active vault positions, distinguish realized interest from accrued but uncredited interest.

If total economic value includes accrued yield, label it separately and explain the valuation basis.

### Baseline comparison

Calculate differences in:

- Net financial benefit.
- Average idle cash.
- Emergency funding events.
- Reserve breaches.
- Failed payouts.
- Redemption penalties.

Do not claim one strategy is superior based solely on higher gross yield.

A strategy that earns more interest but causes additional expensive borrowing may be financially inferior.

---

# 24. DATABASE DESIGN

Use PostgreSQL.

Create the required schema using migration files.

Do not overwrite the existing template's database schema blindly.

Inspect existing migrations before deciding whether to add a new migration or initialize a fresh Reserve Juggler database.

### Table 1 — simulation_runs

Suggested columns:

```text
id UUID PRIMARY KEY
seed INTEGER NOT NULL
scenario VARCHAR
status VARCHAR
started_at TIMESTAMPTZ
current_time TIMESTAMPTZ
current_step INTEGER
duration_steps INTEGER
initial_cash_cents BIGINT
policy_json JSONB
created_at TIMESTAMPTZ
updated_at TIMESTAMPTZ
```

### Table 2 — transactions

```text
id UUID PRIMARY KEY
run_id UUID
step INTEGER
timestamp TIMESTAMPTZ
type VARCHAR
direction VARCHAR
amount_cents BIGINT
source VARCHAR
scenario VARCHAR
```

### Table 3 — ledger_entries

```text
id UUID PRIMARY KEY
run_id UUID
step INTEGER
timestamp TIMESTAMPTZ
entry_type VARCHAR
amount_cents BIGINT
balance_before_cents BIGINT
balance_after_cents BIGINT
reference_id VARCHAR
```

### Table 4 — vault_positions

```text
id UUID PRIMARY KEY
run_id UUID
principal_cents BIGINT
annual_rate_bps INTEGER
created_at TIMESTAMPTZ
matures_at TIMESTAMPTZ
status VARCHAR
early_redemption_allowed BOOLEAN
early_redemption_penalty_bps INTEGER
```

### Table 5 — vault_movements

```text
id UUID PRIMARY KEY
run_id UUID
position_id UUID
step INTEGER
timestamp TIMESTAMPTZ
movement_type VARCHAR
principal_cents BIGINT
interest_cents BIGINT
penalty_cents BIGINT
```

### Table 6 — forecasts

```text
id UUID PRIMARY KEY
run_id UUID
step INTEGER
timestamp TIMESTAMPTZ
horizon_minutes INTEGER
model_version VARCHAR
forecast_json JSONB
risk_json JSONB
```

### Table 7 — liquidity_snapshots

```text
id UUID PRIMARY KEY
run_id UUID
step INTEGER
timestamp TIMESTAMPTZ
checking_cents BIGINT
vault_locked_cents BIGINT
vault_redeemable_cents BIGINT
required_reserve_cents BIGINT
```

### Table 8 — treasury_decisions

```text
id UUID PRIMARY KEY
run_id UUID
step INTEGER
timestamp TIMESTAMPTZ
action VARCHAR
amount_cents BIGINT
execution_status VARCHAR
explanation_json JSONB
decision_details_json JSONB
```

### Table 9 — scenario_events

```text
id UUID PRIMARY KEY
run_id UUID
created_at TIMESTAMPTZ
effective_step INTEGER
scenario_type VARCHAR
parameters_json JSONB
```

### Table 10 — backtest_results

```text
id UUID PRIMARY KEY
run_id UUID
strategy VARCHAR
scenario VARCHAR
seed INTEGER
metrics_json JSONB
created_at TIMESTAMPTZ
```

### Database requirements

- Foreign-key relationships.
- Appropriate indexes on `run_id`, timestamps, and steps.
- Nonnegative financial amount constraints where applicable.
- Unique simulation-step constraints where required.
- Unique transaction and execution references.
- Transactional state updates.
- Consistent JSON structures.
- Referential integrity.
- No sensitive real customer data.

Use `BIGINT` for money, not 32-bit integers.

A $20 million cash amount is 2,000,000,000 cents, which is already near the signed 32-bit integer limit.

---

# 25. FASTAPI CONTRACT

The external API must be stable and predictable.

Use:

`/api/v1`

Do not create competing `/api/treasury/...` and `/api/v1/...` conventions.

Implement the following endpoints.

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/health` | Health check |
| POST | `/api/v1/runs` | Create simulation |
| GET | `/api/v1/runs/{id}/snapshot` | Current treasury state |
| POST | `/api/v1/runs/{id}/advance` | Advance virtual time |
| POST | `/api/v1/runs/{id}/scenario` | Apply stress scenario |
| PATCH | `/api/v1/runs/{id}/policy` | Update allowed policy settings |
| GET | `/api/v1/runs/{id}/history` | Financial history |
| GET | `/api/v1/runs/{id}/forecast` | Latest forecast |
| GET | `/api/v1/runs/{id}/decisions` | Treasury decisions |
| GET | `/api/v1/runs/{id}/transactions` | Recent transactions |
| POST | `/api/v1/runs/{id}/backtest` | Run strategy comparison |
| GET | `/api/v1/runs/{id}/report` | Financial performance report |

Optionally implement:

`GET /api/v1/runs/{id}/report.csv`

Do not require WebSockets for P0.

The frontend may poll the backend while the simulated clock advances.

---

# 26. API REQUEST AND RESPONSE EXAMPLES

Define actual Pydantic request/response schemas.

## A. Create Simulation

Request:

```json
{
  "initial_cash_cents": 2000000000,
  "duration_steps": 288,
  "seed": 42,
  "scenario": "NORMAL",
  "policy": {
    "risk_percentile": 0.95,
    "operational_buffer_cents": 50000000,
    "minimum_sweep_cents": 1000000,
    "vault_yield_bps": 500,
    "vault_lock_steps": 96,
    "early_redemption_allowed": true,
    "early_redemption_penalty_bps": 200
  }
}
```

Response:

```json
{
  "run_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "READY",
  "current_step": 0,
  "checking_cents": 2000000000,
  "vault_locked_cents": 0
}
```

## B. Advance Simulation

Request:

```json
{
  "expected_step": 0,
  "steps": 1
}
```

Response should contain the resulting snapshot or its reference.

The step must advance exactly once.

A stale `expected_step` must not cause duplicate financial processing.

## C. Apply Scenario

Request:

```json
{
  "scenario": "HIGH_WITHDRAWAL",
  "parameters": {
    "withdrawal_multiplier": 3.0,
    "duration_steps": 8
  }
}
```

The backend should record the effective step and apply the scenario prospectively.

## D. Treasury Snapshot

Use this stable response structure:

```json
{
  "run_id": "550e8400-e29b-41d4-a716-446655440000",
  "step": 96,
  "timestamp": "2026-10-17T09:00:00Z",
  "checking_cents": 1400000000,
  "vault_locked_cents": 600000000,
  "vault_redeemable_cents": 0,
  "required_reserve_cents": 1400000000,
  "forecast": {
    "horizon_minutes": 1440,
    "peak_shortfall_cents": 1250000000,
    "uncertainty_buffer_cents": 100000000,
    "operational_buffer_cents": 50000000,
    "model_version": "baseline-v1"
  },
  "decision": {
    "action": "SWEEP",
    "amount_cents": 600000000,
    "pre_checking_cents": 2000000000,
    "post_checking_cents": 1400000000,
    "executed": true,
    "explanation": [
      "Checking exceeded the required reserve.",
      "The sweep was permitted under the configured vault policy.",
      "The allocation satisfied modeled liquidity constraints."
    ]
  }
}
```

This example represents a successfully completed $6 million simulated sweep.

The response must not simultaneously report the amount as both available checking cash and additional vault principal.

In your actual implementation, calculate every amount from current state.

Do not hard-code these example values.

## E. Backtest Result

Return a JSON object including:

- Simulation period.
- Scenario.
- Seed.
- Strategy names.
- Total realized interest.
- Average checking cash.
- Average vault balance.
- Redemption penalties.
- Emergency borrowing cost.
- Reserve breaches.
- Failed payouts.
- Net financial benefit.

All values must be measured.

Unavailable results should be represented honestly, not filled with fake zeros or arbitrary percentages.

---

# 27. API ERROR HANDLING

Use consistent HTTP status codes.

Examples:

- `400` — Invalid request parameters.
- `404` — Simulation run not found.
- `409` — Invalid simulation state or conflicting step.
- `422` — Schema validation failure.
- `500` — Unexpected internal error.

Return consistent error objects containing:

```text
error_code
message
details
```

Do not leak stack traces or secrets in production-style API responses.

Log enough diagnostic information for debugging.

Validate all scenario and policy inputs.

Examples of invalid inputs:

- Negative transaction amount.
- Negative initial cash.
- Risk percentile outside valid range.
- Invalid scenario name.
- Negative vault duration.
- Interest rate outside configured bounds.
- Simulation advance beyond the allowed duration.
- Duplicate transaction execution.
- Early redemption from a prohibited vault.

---

# 28. BACKTEST IMPLEMENTATION DETAILS

A proper backtest is not just a chart containing three arbitrarily different numbers.

Implement a reproducible replay engine.

Recommended function:

```python
run_backtest(
    transactions,
    initial_state,
    treasury_policy,
    strategies,
    seed
) -> BacktestResult
```

For every strategy:

1. Reset the treasury account to the same initial state.
2. Replay the exact same transaction sequence.
3. Process vault maturities.
4. Process deposits and withdrawals.
5. Invoke the strategy's decision function.
6. Execute allowed treasury decisions.
7. Apply borrowing costs or failed-payout consequences.
8. Record financial metrics.
9. Continue until the replay ends.
10. Produce an auditable result.

### No lookahead

The intelligent strategy cannot inspect transactions that have not occurred.

The transaction replay engine may know the future, but the strategy must receive only information that was observable at that simulated moment.

### Fair comparison

Ensure all strategies use the same economic assumptions and policy restrictions.

Only their treasury decision policies should differ.

### Backtesting outputs

Include per-strategy:

```text
Strategy
Simulation length
Realized interest
Accrued interest
Average checking cash
Average vault cash
Emergency events
Borrowing costs
Redemption penalties
Reserve breaches
Failed payouts
Net benefit
```

Report differences relative to the fixed-reserve baseline.

Do not assume Reserve Juggler will win every scenario.

If the model performs worse under a particular shock, preserve the result and use it to demonstrate the importance of risk calibration.

---

# 29. FRONTEND INTEGRATION SUPPORT

Member 3 is building the frontend independently.

Your task is to make backend integration simple.

### Early deliverable

Provide Member 3 with:

- API base URL.
- Endpoint documentation.
- Request schemas.
- Response schemas.
- Mock JSON examples.
- Expected refresh behavior.
- Error format.
- Supported scenario names.
- Supported policy parameters.

### Integration strategy

Member 3 will initially display mock data matching the agreed contract.

When your backend is ready, they should only need to change the frontend API adapter from mock mode to live mode.

Do not require Member 3 to restructure dashboard components due to inconsistent API design.

### Live dashboard updates

For P0, support a polling model:

1. Frontend advances the simulation using the API.
2. Backend processes the requested step.
3. Frontend retrieves the latest snapshot.
4. Charts update from history.
5. Decision explanations update from the recorded decision.
6. Transactions update from the transaction endpoint.

A refresh every one or two seconds is sufficient for the demonstration.

A WebSocket is optional, not necessary.

---

# 30. BACKEND TESTING REQUIREMENTS

Write actual pytest tests.

Do not create placeholder tests that assert trivial constants.

## Test 1 — Reproducible transactions

Using the same seed and configuration must produce the same external transaction sequence.

## Test 2 — Unique transaction IDs

No two generated transactions in the same simulation may share an execution identifier.

## Test 3 — Checking balance correctness

A $1,000 deposit increases checking by $1,000.

A $300 withdrawal decreases checking by $300.

The resulting balance must be correct in cents.

## Test 4 — Merchant settlement direction

Incoming settlement increases checking.

Outgoing settlement decreases checking.

## Test 5 — Sweep accounting

A $6 million sweep:

- Decreases checking by $6 million.
- Creates $6 million in vault principal.
- Does not change total principal assets.

## Test 6 — Vault maturity

A one-day vault deposit matures at the correct simulated time and credits principal plus eligible interest once.

## Test 7 — No duplicate maturity

Processing the same maturity twice must not credit checking twice.

## Test 8 — Locked vault restriction

Redemption must fail when early redemption is prohibited and maturity has not occurred.

## Test 9 — Early redemption penalty

When early redemption is allowed, the configured penalty must be applied correctly.

## Test 10 — Emergency borrowing

When checking cannot cover a payment and borrowing is available, record the loan and financing cost.

## Test 11 — Payout failure

If neither checking nor permitted borrowing can fund the payment, record the unpaid amount and do not mark the payment as fully successful.

## Test 12 — Normal scenario

Normal simulation generates and processes valid financial transactions.

## Test 13 — High withdrawal scenario

The withdrawal multiplier changes actual outgoing cash flows.

## Test 14 — Low deposit scenario

The deposit reduction changes actual incoming cash flows.

## Test 15 — Settlement delay

A delayed settlement arrives at the later interval exactly once.

## Test 16 — Liquidity shock

An unexpected large withdrawal changes the financial state and can trigger the appropriate warning or borrowing event.

## Test 17 — Simulation determinism

Two runs with identical inputs and seed must produce equivalent results.

## Test 18 — Simulation-step idempotency

Retrying an already-completed advance must not apply the financial events a second time.

## Test 19 — Financial conservation

Internal cash-to-vault transfers must conserve principal.

Changes due to customer cash flows, credited interest, fees, and borrowing must be separately traceable.

## Test 20 — Backtesting fairness

All baseline strategies must receive the same exogenous transaction sequence.

## Test 21 — No future-data leakage

Forecasting inputs must not include future realized transactions.

## Test 22 — API health

`GET /health` must return a successful response.

## Test 23 — Create simulation API

A valid request creates a run and persists the expected initial state.

## Test 24 — Scenario API

A scenario request must update future simulation behavior and persist its configuration.

## Test 25 — Full backend pipeline

Run:

`Simulation → Transactions → Ledger → Forecast Adapter → Reserve → Decision → Execution → Persistence → Snapshot`

Verify that the system produces an internally consistent result.

---

# 31. FINANCIAL INVARIANTS

These invariants are mandatory.

### Invariant 1 — Principal conservation

Moving money between checking and vault does not create or destroy principal.

### Invariant 2 — Interest accounting

Interest must arise only from the simulated vault contract.

### Invariant 3 — No double execution

The same transaction, sweep, redemption, or maturity cannot be executed twice.

### Invariant 4 — No free liquidity

A locked position cannot fund a payout unless an allowed redemption is executed and its costs are recorded.

### Invariant 5 — Honest payout status

A payment is successful only when the customer receives the required amount through checking and permitted funding.

### Invariant 6 — Accurate borrowing costs

Emergency borrowing is not free money.

### Invariant 7 — Deterministic replay

The same transaction history and configuration must produce equivalent financial results.

### Invariant 8 — Auditability

Every significant account balance movement must have a corresponding audit or ledger entry.

### Invariant 9 — No data leakage

A decision may use historical observations and declared known future commitments, but never undisclosed future realized customer transactions.

### Invariant 10 — Strategy isolation

One backtesting strategy's actions must not affect another strategy's balances.

Write tests enforcing these invariants.

---

# 32. DOCKER AND ENVIRONMENT MANAGEMENT

The existing team repository already contains a tested Docker setup.

Do not recreate the infrastructure unless necessary.

Your responsibilities:

1. Inspect existing FastAPI configuration.
2. Confirm Python dependencies.
3. Confirm PostgreSQL connection.
4. Add or adapt the Reserve Juggler database migration.
5. Ensure the backend starts through Docker Compose.
6. Ensure the health endpoint works.
7. Verify database migrations can be rerun safely.
8. Check `.env.example` for required values.
9. Avoid storing passwords inside committed source code.
10. Verify the project works without GPU dependencies.

The core simulation must run on CPU-only laptops.

Do not make PyTorch, CUDA, or a dedicated GPU mandatory.

Do not require Kafka, Redis, Celery, or additional microservices for P0.

If Docker configuration changes affect other team members, communicate them before merging.

---

# 33. PERFORMANCE REQUIREMENTS

The backend must handle an interactive hackathon demonstration smoothly.

Recommended targets:

- A single simulation step should complete quickly enough for live replay.
- Snapshot retrieval should be responsive.
- Database operations should not unnecessarily block the UI.
- Transaction generation should support long synthetic histories.
- Seven-day strategy comparisons should be practical on development hardware.
- Thirty-day backtesting can be implemented as a P1 enhancement.
- The backend should reuse trained forecasting models rather than retraining on every request.
- Reports should read persisted results rather than rerun expensive calculations automatically.

These are engineering targets, not promises of specific measured performance.

Test actual execution times where practical.

Avoid premature optimization that increases integration complexity.

---

# 34. MEMBER 2 DEVELOPMENT TIMELINE

## Hours 0–1 — Contract and Repository Setup

Tasks:

1. Inspect the repository.
2. Create or switch to `feat/simulation-backend`.
3. Confirm the shared API contract.
4. Confirm Member 1's engine input/output contract.
5. Confirm schema examples with Member 3.
6. Define database tables.
7. Establish monetary and timing conventions.
8. Create the backend module skeleton.

**Milestone:** All three members agree on contracts and can continue independently.

## Hours 1–4 — Transaction and Ledger Foundation

Implement:

- Seeded transaction generator.
- Historical transaction generation.
- Fifteen-minute aggregation.
- Simulation initialization.
- Checking ledger.
- Vault position creation.
- Vault maturity.
- Database persistence.

Write tests for basic accounting.

**Milestone:** The backend can independently simulate banking transactions and maintain correct checking/vault balances.

## Hours 4–7 — Simulation and API

Implement:

- Simulation clock.
- Step execution.
- Fallback treasury policy adapter.
- HOLD/SWEEP/WITHDRAW/WARNING execution behavior.
- Health endpoint.
- Create simulation endpoint.
- Advance simulation endpoint.
- Snapshot endpoint.
- Recent transactions endpoint.

**Milestone:** A developer can start and advance a simulation using REST requests without a frontend.

## Hours 7–10 — Stress Scenarios and Auditing

Implement:

- NORMAL.
- HIGH_WITHDRAWAL.
- LOW_DEPOSIT.
- SETTLEMENT_DELAY.
- LIQUIDITY_SHOCK.
- Emergency financing.
- Failed payout reporting.
- Financial decision logs.
- Scenario API.
- Decision history API.

**Milestone:** Stress scenarios change actual financial outcomes.

## Hours 10–14 — Backtesting and Member 1 Integration

Implement:

- Static reserve strategy.
- Reactive reserve strategy.
- Reserve Juggler strategy adapter.
- Same-transaction replay.
- Performance metrics.
- Backtesting API.
- Real Member 1 forecasting/reserve/decision integration.

**Milestone:** The system can compare three strategies using actual simulation results.

## Hours 14–18 — Advanced Metrics and Reliability

Implement where feasible:

- Extended backtesting.
- Financial reports.
- CSV export.
- Policy configuration.
- Additional tests.
- Database constraint improvements.
- Performance optimization.
- Error handling.

Support Member 3 in connecting the real frontend.

**Milestone:** The full application works under normal and stressed conditions.

## Hours 18–21 — Final Integration

Stop introducing risky new backend features.

Tasks:

- Merge approved branches into `develop`.
- Run the complete stack.
- Execute critical integration tests.
- Confirm contract compatibility.
- Verify database initialization on another laptop.
- Fix API and financial accounting bugs.
- Prepare a demo seed and scenario sequence.

**Milestone:** A reproducible working demonstration is available.

## Hours 21–24 — Feature Freeze

Only:

- Critical bug fixes.
- Deployment checks.
- Demo rehearsal.
- Report verification.
- Financial consistency checks.
- Submission assistance.

Do not redesign the database or API at this stage.

---

# 35. PARALLEL DEVELOPMENT RULES

All three members will develop simultaneously.

To avoid integration problems:

### Rule 1

Only change files you own, except for explicitly agreed shared configuration.

### Rule 2

Keep public API responses stable.

### Rule 3

Publish representative API fixtures early.

### Rule 4

Build against Member 1's agreed contracts, not guesses about their eventual implementation.

### Rule 5

Do not wait for Member 1 before implementing the backend.

Use the fallback adapter.

### Rule 6

Do not wait for Member 3 before testing APIs.

Use automated tests and HTTP requests.

### Rule 7

Communicate breaking changes before merging them.

### Rule 8

Keep commits small and meaningful.

### Rule 9

Never push secrets or unnecessary model files.

### Rule 10

Do not randomly upgrade working dependencies during the hackathon.

---

# 36. EARLY HANDOFF TO MEMBER 3

As soon as your API schema is established, provide Member 3 with:

```text
API_BASE_URL

POST /api/v1/runs
GET /api/v1/runs/{id}/snapshot
POST /api/v1/runs/{id}/advance
POST /api/v1/runs/{id}/scenario
PATCH /api/v1/runs/{id}/policy
GET /api/v1/runs/{id}/history
GET /api/v1/runs/{id}/forecast
GET /api/v1/runs/{id}/decisions
GET /api/v1/runs/{id}/transactions
POST /api/v1/runs/{id}/backtest
GET /api/v1/runs/{id}/report
```

Also provide:

- Valid scenario enum values.
- JSON request examples.
- JSON response examples.
- Financial units.
- Snapshot semantics.
- Simulation advancement behavior.
- Standard error responses.
- Empty-state behavior.
- Historical chart format.

Member 3 must be able to build the entire frontend using these contracts without waiting for your backend to finish.

---

# 37. EARLY HANDOFF TO MEMBER 1

Provide Member 1 with:

### Historical data

Chronological 15-minute cash-flow buckets.

### Treasury context

- Current checking cash.
- Vault positions.
- Vault maturity schedules.
- Eligible early redemption.
- Known committed obligations.
- Current simulation timestamp.

### Configurable policy

- Forecast horizon.
- Risk percentile.
- Operational buffer.
- Minimum sweep.
- Yield rate.
- Vault lock duration.
- Redemption restrictions.
- Penalties.
- Sweep window eligibility.

### Execution feedback

After applying a recommendation, record:

- Requested action.
- Executed action.
- Requested amount.
- Executed amount.
- Success/failure status.
- Actual checking balance.
- Actual vault balance.
- Costs incurred.

This allows Member 1's pure decision engine to remain independent of database or ledger code.

---

# 38. BACKEND DEMONSTRATION REQUIREMENT

Create a reproducible demo process that works without the frontend.

The demonstration must:

1. Create a simulation.
2. Initialize checking cash.
3. Generate transactions.
4. Advance time.
5. Aggregate cash flows.
6. Obtain a treasury recommendation.
7. Execute a valid sweep.
8. Create a locked vault position.
9. Apply a withdrawal spike.
10. Recompute the treasury state.
11. Respect vault lock restrictions.
12. Record a withdrawal, emergency funding event, or warning as appropriate.
13. Advance time to vault maturity.
14. Credit principal and interest correctly.
15. Produce a performance report.
16. Compare the three strategies.

The exact scenario results must be determined by the simulator, not forced to match a predetermined success message.

Use a fixed documented seed for the team demo.

Provide either a simple demonstration script or a reproducible sequence of API requests.

---

# 39. SECURITY AND RELIABILITY

Even though this is a prototype, implement basic engineering safeguards.

Required:

- Input validation.
- Database constraints.
- Secret-free source code.
- `.env` configuration.
- Error handling.
- Structured application logging.
- Unique transaction identifiers.
- Audit logs.
- Deterministic simulation seeds.
- Balance consistency.
- Safe state transitions.
- Idempotent financial execution.
- Explicit rate and monetary units.

Do not implement unnecessary real bank authentication or payment processing.

This is a simulation, not a system authorized to access real customer accounts.

The application should clearly expose:

**SIMULATED TREASURY ENVIRONMENT — NO REAL FUNDS**

Do not claim production readiness.

---

# 40. JUDGE-READY TECHNICAL EXPLANATIONS

Your implementation should allow the team to answer these questions.

### How are transactions generated?

We use a seeded synthetic transaction generator with configurable time-of-day activity, transaction distributions, settlement schedules, and stress events.

### Are these actual bank transactions?

No. The transactions are synthetic and reproducible, allowing controlled evaluation without sensitive customer data.

### How does the system simulate real time?

We use a virtual 15-minute clock that advances on demand. Each step processes financial transactions, vault maturities, treasury decisions, and ledger updates.

### How is a sweep executed?

The engine recommends a sweep, then our execution system checks financial and contractual constraints, debits checking, creates a vault position, and records an auditable transfer.

### What happens when the vault is locked?

Funds are unavailable until maturity unless permitted early redemption is executed with the applicable cost.

### What happens during an unexpected liquidity shortage?

The system can record emergency borrowing or a payout failure depending on configured funding availability.

### How do you measure financial performance?

We calculate realized interest, average checking cash, emergency borrowing costs, redemption penalties, reserve breaches, and net financial benefit directly from simulation events.

### How do you compare against baselines?

We replay the same external transaction sequence against fixed, reactive, and intelligent treasury strategies under identical economic assumptions.

### How do you prevent misleading results?

We use deterministic seeds, avoid future-data leakage, track actual financial movements, and report failures and costs instead of hiding them.

### Is this production-ready banking software?

No. It is a prototype for studying and demonstrating treasury decision methodology.

---

# 41. DEFINITION OF DONE

Your assignment is complete when the following are implemented and tested.

## Transaction engine

- [ ] Seeded transaction generation works.
- [ ] Deposits work.
- [ ] Withdrawals work.
- [ ] Incoming merchant settlements work.
- [ ] Outgoing merchant settlements work.
- [ ] Time-of-day patterns exist.
- [ ] Historical cash-flow buckets are generated.
- [ ] Transaction IDs are unique.
- [ ] Generation is reproducible.

## Simulation engine

- [ ] Simulation runs can be created.
- [ ] Virtual clock advances correctly.
- [ ] Each step executes exactly once.
- [ ] Checking balances update correctly.
- [ ] Transaction aggregation works.
- [ ] Treasury adapter works.
- [ ] Forecast and reserve data are stored.
- [ ] Recommendations are validated.
- [ ] Executed decisions are recorded.

## Vault

- [ ] Sweep creates a real simulated vault position.
- [ ] Checking is debited exactly once.
- [ ] Vault principal is recorded.
- [ ] Maturity is calculated correctly.
- [ ] Matured funds return to checking.
- [ ] Interest is calculated correctly.
- [ ] Locked positions cannot be redeemed illegally.
- [ ] Early redemption penalties work.
- [ ] Interest is not double-counted.

## Stress testing

- [ ] NORMAL works.
- [ ] HIGH_WITHDRAWAL works.
- [ ] LOW_DEPOSIT works.
- [ ] SETTLEMENT_DELAY works.
- [ ] LIQUIDITY_SHOCK works.
- [ ] Shocks modify actual future transactions.
- [ ] Mid-run scenario application works.
- [ ] Shortfalls are recorded accurately.
- [ ] Emergency funding events are tracked.

## Database

- [ ] PostgreSQL schema exists.
- [ ] Migrations work.
- [ ] Run IDs isolate simulations.
- [ ] Transactions persist.
- [ ] Vault positions persist.
- [ ] Decisions persist.
- [ ] Snapshots persist.
- [ ] Backtest results persist.
- [ ] Constraints protect invalid financial states.

## API

- [ ] Health endpoint works.
- [ ] Create simulation works.
- [ ] Advance simulation works.
- [ ] Snapshot endpoint works.
- [ ] Scenario endpoint works.
- [ ] Policy configuration works.
- [ ] History endpoint works.
- [ ] Forecast endpoint works.
- [ ] Decisions endpoint works.
- [ ] Transactions endpoint works.
- [ ] Backtest endpoint works.
- [ ] Report endpoint works.
- [ ] API documentation matches implementation.

## Evaluation

- [ ] Static strategy works.
- [ ] Reactive strategy works.
- [ ] Reserve Juggler strategy works.
- [ ] Identical transaction replay is enforced.
- [ ] Financial metrics are calculated.
- [ ] Actual costs are deducted.
- [ ] Performance results are auditable.
- [ ] No fabricated comparison data.

## Integration

- [ ] Member 1's engine can be imported.
- [ ] Fallback engine is clearly identified.
- [ ] Member 3 can consume the real API.
- [ ] The complete Docker stack runs.
- [ ] Critical pytest tests pass.
- [ ] Demo scenario is reproducible.
- [ ] No unsupported financial claims are made.

---

# 42. FINAL DELIVERABLES

Before completing your assignment, provide the following.

## A. Implementation summary

List every file created or modified and describe its purpose.

## B. Database schema

Provide the migration files and explain how to initialize the database.

## C. Backend API documentation

Include endpoint descriptions, request bodies, responses, and validation rules.

## D. Transaction simulator documentation

Describe distributions, time patterns, seeds, and supported scenario parameters.

## E. Ledger documentation

Explain checking cash, vault principal, yield, redemption, maturity, and emergency funding accounting.

## F. Backtesting documentation

Explain how the three strategies are compared fairly.

## G. Integration instructions for Member 1

Show exactly where the quantitative engine is imported and how its outputs are executed.

## H. Integration instructions for Member 3

Provide API base URL, endpoint list, JSON fixtures, and frontend integration behavior.

## I. Test results

Provide the actual test commands executed and test outcomes.

Do not claim tests passed if they were not run.

## J. Demo instructions

Provide the exact commands required to:

1. Start PostgreSQL and the backend.
2. Initialize the database.
3. Create a simulation.
4. Advance simulation time.
5. Trigger a stress scenario.
6. View treasury state and decisions.
7. Run strategy backtesting.
8. Retrieve the report.

## K. Known limitations

Identify any unfinished features, assumptions, and limitations honestly.

---

# 43. FINAL INSTRUCTIONS TO YOU, THE DEVELOPMENT AGENT

**Begin actual implementation. Do not stop after designing the architecture.**

If the repository and development environment are accessible:

1. Inspect the existing codebase.
2. Create or use `feat/simulation-backend`.
3. Confirm the shared data contracts.
4. Implement PostgreSQL schemas.
5. Implement transaction generation.
6. Implement the checking ledger.
7. Implement vault lifecycle management.
8. Implement the simulation clock.
9. Implement the treasury adapter and fallback.
10. Implement REST APIs.
11. Implement all five stress scenarios.
12. Implement emergency funding and financial audit logs.
13. Implement static and reactive strategy baselines.
14. Implement the backtesting framework.
15. Integrate Member 1's quantitative engine when available.
16. Execute unit and integration tests.
17. Verify Docker compatibility.
18. Prepare Member 3's API handoff.
19. Document implementation and known limitations.
20. Produce a reproducible end-to-end backend demo.

Make reasonable implementation decisions when details are unspecified, but document significant assumptions and do not break the agreed integration contract.

Do not wait for another team member's code before proceeding with your own implementation.

If a requested feature is not possible in the available environment, complete the maximum functional subset and identify the remaining work precisely.

**Your most important responsibility is to ensure that every financial action in Reserve Juggler is real within the simulation, financially consistent, persistent, and traceable.**

---

# 44. FINAL MISSION

Build the infrastructure that turns Member 1's mathematical intelligence into a fully functioning treasury simulation.

At the end of development, the system must be able to demonstrate:

- Transactions genuinely occur.
- Balances genuinely change.
- Forecasting receives real simulation history.
- Treasury decisions are computed and validated.
- Sweeps genuinely transfer simulated funds.
- Vault deposits genuinely remain locked.
- Matured deposits genuinely return principal and interest.
- Early redemptions genuinely incur configured penalties.
- Emergency borrowing genuinely incurs costs.
- Stress scenarios genuinely affect financial outcomes.
- Strategy backtesting genuinely compares identical conditions.
- Every financial event is recorded.
- Every displayed performance number comes from a calculation.

The finished system should follow:

**GENERATE → VALIDATE → AGGREGATE → FORECAST → DECIDE → EXECUTE → RECORD → EVALUATE → REPORT**

**Your priorities are:**

1. Financial correctness.
2. Reliable simulation.
3. Stable backend contracts.
4. Real decision execution.
5. Accurate strategy benchmarking.
6. Reproducible testing.
7. Advanced enhancements.

**The final goal is a working, auditable, and demonstrable treasury simulation platform that integrates cleanly with Member 1's intelligence engine and Member 3's React dashboard.**

**Start implementing Member 2's complete backend and simulation module now.**