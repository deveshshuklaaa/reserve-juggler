-- ==============================================================================
-- Reserve Juggler: Initial Seed Data
-- Provides baseline demo data for transactions, liquidity snapshots, and decisions
-- ==============================================================================

-- Baseline Transactions
INSERT INTO transactions (timestamp, type, amount, source, scenario) VALUES
    (CURRENT_TIMESTAMP - INTERVAL '15 minutes', 'DEPOSIT', 150000.00, 'corporate_payroll', 'baseline'),
    (CURRENT_TIMESTAMP - INTERVAL '12 minutes', 'MERCHANT_SETTLEMENT', 85000.00, 'pos_batch_01', 'baseline'),
    (CURRENT_TIMESTAMP - INTERVAL '9 minutes', 'WITHDRAWAL', 42000.00, 'atm_network', 'baseline'),
    (CURRENT_TIMESTAMP - INTERVAL '5 minutes', 'WITHDRAWAL', 95000.00, 'wire_transfer_out', 'baseline'),
    (CURRENT_TIMESTAMP - INTERVAL '1 minute', 'DEPOSIT', 60000.00, 'ach_inbound', 'baseline');

-- Baseline Forecast
INSERT INTO forecasts (timestamp, horizon_minutes, predicted_inflow, predicted_outflow, predicted_net_flow, uncertainty, model_version) VALUES
    (CURRENT_TIMESTAMP, 60, 220000.00, 180000.00, 40000.00, 25000.00, 'v0.1-quantile-baseline');

-- Baseline Liquidity Snapshot
INSERT INTO liquidity_snapshots (timestamp, checking_balance, vault_balance, required_reserve, deployable_cash) VALUES
    (CURRENT_TIMESTAMP, 750000.00, 3250000.00, 520000.00, 230000.00);

-- Baseline Decisions Log
INSERT INTO decisions (timestamp, decision_type, amount, required_reserve, forecast_value, forecast_uncertainty, safety_buffer, reason) VALUES
    (CURRENT_TIMESTAMP - INTERVAL '30 minutes', 'HOLD', 0.00, 500000.00, 30000.00, 20000.00, 50000.00, 'Checking balance ($510k) within equilibrium corridor of required reserve ($500k).'),
    (CURRENT_TIMESTAMP - INTERVAL '10 minutes', 'SWEEP', 180000.00, 520000.00, 40000.00, 25000.00, 50000.00, 'Checking balance ($750k) significantly exceeds required reserve ($520k). Sweeping excess to yield vault.');

-- Baseline Simulation Run
INSERT INTO simulation_runs (scenario, started_at, ended_at, total_yield, reserve_breaches, emergency_events) VALUES
    ('baseline_24h_replay', CURRENT_TIMESTAMP - INTERVAL '2 hours', CURRENT_TIMESTAMP - INTERVAL '1 hour', 412.50, 0, 0);
