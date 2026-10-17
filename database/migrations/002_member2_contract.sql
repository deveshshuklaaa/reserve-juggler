-- Member 2 persistence contract; no demo-data conversion or business operations.
-- Existing public.* tables remain legacy. v1 services must explicitly target
-- reserve_juggler_v1 so dollar-valued demo rows cannot be interpreted as cents.
CREATE SCHEMA IF NOT EXISTS reserve_juggler_v1;

CREATE TABLE IF NOT EXISTS reserve_juggler_v1.simulation_runs (
    id UUID PRIMARY KEY,
    seed INTEGER NOT NULL CHECK (seed >= 0),
    scenario VARCHAR(32) NOT NULL CHECK (scenario IN
        ('NORMAL', 'HIGH_WITHDRAWAL', 'LOW_DEPOSIT', 'SETTLEMENT_DELAY', 'LIQUIDITY_SHOCK')),
    status VARCHAR(32) NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    current_time TIMESTAMPTZ NOT NULL,
    current_step INTEGER NOT NULL DEFAULT 0 CHECK (current_step >= 0),
    duration_steps INTEGER NOT NULL CHECK (duration_steps > 0),
    initial_cash_cents BIGINT NOT NULL CHECK (initial_cash_cents >= 0),
    policy_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (current_step <= duration_steps),
    CHECK (current_time >= started_at)
);

CREATE TABLE IF NOT EXISTS reserve_juggler_v1.transactions (
    id UUID PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES reserve_juggler_v1.simulation_runs(id),
    step INTEGER NOT NULL CHECK (step >= 0),
    timestamp TIMESTAMPTZ NOT NULL,
    type VARCHAR(32) NOT NULL CHECK (type IN ('DEPOSIT', 'WITHDRAWAL', 'MERCHANT_SETTLEMENT')),
    direction VARCHAR(8) NOT NULL CHECK (direction IN ('INFLOW', 'OUTFLOW')),
    amount_cents BIGINT NOT NULL CHECK (amount_cents > 0),
    source VARCHAR(100) NOT NULL,
    scenario VARCHAR(32) NOT NULL CHECK (scenario IN
        ('NORMAL', 'HIGH_WITHDRAWAL', 'LOW_DEPOSIT', 'SETTLEMENT_DELAY', 'LIQUIDITY_SHOCK')),
    CHECK ((type = 'DEPOSIT' AND direction = 'INFLOW') OR
           (type = 'WITHDRAWAL' AND direction = 'OUTFLOW') OR type = 'MERCHANT_SETTLEMENT')
);
CREATE INDEX IF NOT EXISTS idx_v1_transactions_run_step ON reserve_juggler_v1.transactions(run_id, step);
CREATE INDEX IF NOT EXISTS idx_v1_transactions_run_time ON reserve_juggler_v1.transactions(run_id, timestamp);

CREATE TABLE IF NOT EXISTS reserve_juggler_v1.ledger_entries (
    id UUID PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES reserve_juggler_v1.simulation_runs(id),
    step INTEGER NOT NULL CHECK (step >= 0),
    timestamp TIMESTAMPTZ NOT NULL,
    entry_type VARCHAR(64) NOT NULL,
    amount_cents BIGINT NOT NULL CHECK (amount_cents >= 0),
    balance_before_cents BIGINT NOT NULL CHECK (balance_before_cents >= 0),
    balance_after_cents BIGINT NOT NULL CHECK (balance_after_cents >= 0),
    reference_id VARCHAR(200) NOT NULL,
    UNIQUE (run_id, reference_id)
);
CREATE INDEX IF NOT EXISTS idx_v1_ledger_run_step ON reserve_juggler_v1.ledger_entries(run_id, step);

CREATE TABLE IF NOT EXISTS reserve_juggler_v1.vault_positions (
    id UUID PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES reserve_juggler_v1.simulation_runs(id),
    principal_cents BIGINT NOT NULL CHECK (principal_cents > 0),
    annual_rate_bps INTEGER NOT NULL CHECK (annual_rate_bps BETWEEN 0 AND 10000),
    created_at TIMESTAMPTZ NOT NULL,
    matures_at TIMESTAMPTZ NOT NULL CHECK (matures_at > created_at),
    status VARCHAR(16) NOT NULL CHECK (status IN ('LOCKED', 'MATURED', 'REDEEMED')),
    early_redemption_allowed BOOLEAN NOT NULL,
    early_redemption_penalty_bps INTEGER NOT NULL CHECK (early_redemption_penalty_bps BETWEEN 0 AND 10000),
    UNIQUE (run_id, id)
);
CREATE INDEX IF NOT EXISTS idx_v1_vault_run_maturity ON reserve_juggler_v1.vault_positions(run_id, matures_at);

CREATE TABLE IF NOT EXISTS reserve_juggler_v1.vault_movements (
    id UUID PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES reserve_juggler_v1.simulation_runs(id),
    position_id UUID NOT NULL,
    step INTEGER NOT NULL CHECK (step >= 0),
    timestamp TIMESTAMPTZ NOT NULL,
    movement_type VARCHAR(32) NOT NULL,
    principal_cents BIGINT NOT NULL CHECK (principal_cents >= 0),
    interest_cents BIGINT NOT NULL CHECK (interest_cents >= 0),
    penalty_cents BIGINT NOT NULL CHECK (penalty_cents >= 0),
    FOREIGN KEY (run_id, position_id) REFERENCES reserve_juggler_v1.vault_positions(run_id, id),
    UNIQUE (run_id, position_id, movement_type)
);
CREATE INDEX IF NOT EXISTS idx_v1_movements_run_step ON reserve_juggler_v1.vault_movements(run_id, step);

CREATE TABLE IF NOT EXISTS reserve_juggler_v1.forecasts (
    id UUID PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES reserve_juggler_v1.simulation_runs(id),
    step INTEGER NOT NULL CHECK (step >= 0),
    timestamp TIMESTAMPTZ NOT NULL,
    horizon_minutes INTEGER NOT NULL CHECK (horizon_minutes > 0 AND horizon_minutes % 15 = 0),
    model_version VARCHAR(100) NOT NULL,
    forecast_json JSONB NOT NULL,
    risk_json JSONB NOT NULL,
    UNIQUE (run_id, step)
);

CREATE TABLE IF NOT EXISTS reserve_juggler_v1.liquidity_snapshots (
    id UUID PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES reserve_juggler_v1.simulation_runs(id),
    step INTEGER NOT NULL CHECK (step >= 0),
    timestamp TIMESTAMPTZ NOT NULL,
    checking_cents BIGINT NOT NULL CHECK (checking_cents >= 0),
    vault_locked_cents BIGINT NOT NULL CHECK (vault_locked_cents >= 0),
    vault_redeemable_cents BIGINT NOT NULL CHECK (vault_redeemable_cents >= 0),
    required_reserve_cents BIGINT CHECK (required_reserve_cents >= 0),
    UNIQUE (run_id, step)
);

CREATE TABLE IF NOT EXISTS reserve_juggler_v1.treasury_decisions (
    id UUID PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES reserve_juggler_v1.simulation_runs(id),
    step INTEGER NOT NULL CHECK (step >= 0),
    timestamp TIMESTAMPTZ NOT NULL,
    action VARCHAR(32) NOT NULL CHECK (action IN ('HOLD', 'SWEEP', 'WITHDRAW', 'LIQUIDITY_WARNING')),
    amount_cents BIGINT NOT NULL CHECK (amount_cents >= 0),
    execution_status VARCHAR(32) NOT NULL,
    explanation_json JSONB NOT NULL,
    decision_details_json JSONB NOT NULL,
    UNIQUE (run_id, step)
);

CREATE TABLE IF NOT EXISTS reserve_juggler_v1.scenario_events (
    id UUID PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES reserve_juggler_v1.simulation_runs(id),
    created_at TIMESTAMPTZ NOT NULL,
    effective_step INTEGER NOT NULL CHECK (effective_step >= 0),
    scenario_type VARCHAR(32) NOT NULL CHECK (scenario_type IN
        ('NORMAL', 'HIGH_WITHDRAWAL', 'LOW_DEPOSIT', 'SETTLEMENT_DELAY', 'LIQUIDITY_SHOCK')),
    parameters_json JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_v1_scenarios_run_step ON reserve_juggler_v1.scenario_events(run_id, effective_step);

CREATE TABLE IF NOT EXISTS reserve_juggler_v1.backtest_results (
    id UUID PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES reserve_juggler_v1.simulation_runs(id),
    strategy VARCHAR(32) NOT NULL CHECK (strategy IN ('STATIC_RESERVE', 'REACTIVE_RESERVE', 'RESERVE_JUGGLER')),
    scenario VARCHAR(32) NOT NULL CHECK (scenario IN
        ('NORMAL', 'HIGH_WITHDRAWAL', 'LOW_DEPOSIT', 'SETTLEMENT_DELAY', 'LIQUIDITY_SHOCK')),
    seed INTEGER NOT NULL CHECK (seed >= 0),
    metrics_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_v1_backtests_run ON reserve_juggler_v1.backtest_results(run_id);
