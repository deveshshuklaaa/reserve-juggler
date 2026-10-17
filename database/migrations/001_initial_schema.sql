-- ==============================================================================
-- Reserve Juggler: Initial Schema Migration
-- Defines core entities for transactions, forecasts, liquidity, and decisions
-- ==============================================================================

-- 1. Simulated transaction streams
CREATE TABLE IF NOT EXISTS transactions (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL,
    type VARCHAR(50) NOT NULL, -- DEPOSIT, WITHDRAWAL, MERCHANT_SETTLEMENT
    amount NUMERIC(18, 4) NOT NULL,
    source VARCHAR(100) NOT NULL,
    scenario VARCHAR(100) DEFAULT 'baseline',
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_transactions_timestamp ON transactions(timestamp);
CREATE INDEX IF NOT EXISTS idx_transactions_scenario ON transactions(scenario);

-- 2. Forecasting engine predictions and uncertainty bounds
CREATE TABLE IF NOT EXISTS forecasts (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL,
    horizon_minutes INT NOT NULL,
    predicted_inflow NUMERIC(18, 4) NOT NULL,
    predicted_outflow NUMERIC(18, 4) NOT NULL,
    predicted_net_flow NUMERIC(18, 4) NOT NULL,
    uncertainty NUMERIC(18, 4) NOT NULL,
    model_version VARCHAR(50) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_forecasts_timestamp ON forecasts(timestamp);

-- 3. Point-in-time treasury liquidity states
CREATE TABLE IF NOT EXISTS liquidity_snapshots (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL,
    checking_balance NUMERIC(18, 4) NOT NULL,
    vault_balance NUMERIC(18, 4) NOT NULL,
    required_reserve NUMERIC(18, 4) NOT NULL,
    deployable_cash NUMERIC(18, 4) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_liquidity_snapshots_timestamp ON liquidity_snapshots(timestamp);

-- 4. Treasury decision engine recommendation logs
CREATE TABLE IF NOT EXISTS decisions (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL,
    decision_type VARCHAR(50) NOT NULL, -- HOLD, SWEEP, WITHDRAW, LIQUIDITY_WARNING
    amount NUMERIC(18, 4) NOT NULL,
    required_reserve NUMERIC(18, 4) NOT NULL,
    forecast_value NUMERIC(18, 4) NOT NULL,
    forecast_uncertainty NUMERIC(18, 4) NOT NULL,
    safety_buffer NUMERIC(18, 4) NOT NULL,
    reason TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_decisions_timestamp ON decisions(timestamp);
CREATE INDEX IF NOT EXISTS idx_decisions_type ON decisions(decision_type);

-- 5. Stress test and simulation execution records
CREATE TABLE IF NOT EXISTS simulation_runs (
    id SERIAL PRIMARY KEY,
    scenario VARCHAR(100) NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ,
    total_yield NUMERIC(18, 4) DEFAULT 0.0000,
    reserve_breaches INT DEFAULT 0,
    emergency_events INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
