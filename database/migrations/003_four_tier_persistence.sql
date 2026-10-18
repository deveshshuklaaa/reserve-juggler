-- Additive four-tier persistence. Apply through app.persistence.migrations.

-- Source times are TIMESTAMP WITHOUT TIME ZONE; never attach a guessed zone.

-- Only relevant legacy NOT NULL constraints are relaxed; no data is rewritten.

CREATE TABLE reserve_juggler_v1.dataset_sources (
	dataset_id TEXT NOT NULL,
	dataset_name TEXT NOT NULL,
	source_type VARCHAR(32) NOT NULL,
	source_path TEXT NOT NULL,
	content_hash VARCHAR(64) NOT NULL,
	hash_algorithm VARCHAR(16) NOT NULL CHECK (hash_algorithm = 'sha256'),
	row_count INTEGER NOT NULL,
	first_timestamp TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	last_timestamp TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	native_interval_seconds INTEGER NOT NULL,
	timezone_status VARCHAR(32) NOT NULL,
	validation_status VARCHAR(40) NOT NULL,
	validation_json JSONB NOT NULL,
	PRIMARY KEY (dataset_id),
	UNIQUE (content_hash),
	UNIQUE (dataset_id, native_interval_seconds),
	CHECK (row_count > 0 AND native_interval_seconds > 0),
	CHECK (last_timestamp >= first_timestamp),
	CHECK (content_hash ~ '^[0-9a-f]{64}$'),
	CHECK (source_type = 'ORGANIZER_CSV' AND timezone_status = 'UNSPECIFIED'),
	CHECK (validation_status IN ('VALIDATED', 'VALIDATED_WITH_DIAGNOSTICS'))
);

CREATE TABLE reserve_juggler_v1.organizer_observations (
	dataset_id TEXT NOT NULL,
	timestamp TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	deposits_usd NUMERIC NOT NULL CHECK (deposits_usd NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)) CHECK (deposits_usd >= 0),
	withdrawals_usd NUMERIC NOT NULL CHECK (withdrawals_usd NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)) CHECK (withdrawals_usd >= 0),
	net_flow_usd NUMERIC NOT NULL CHECK (net_flow_usd NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)),
	repo_sweep_window_open BOOLEAN NOT NULL,
	repo_sweep_mature BOOLEAN NOT NULL,
	tier1_repo_rate_apy NUMERIC NOT NULL CHECK (tier1_repo_rate_apy NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)),
	tier2_bond_yield_pct NUMERIC NOT NULL CHECK (tier2_bond_yield_pct NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)),
	tier2_bond_price_index NUMERIC NOT NULL CHECK (tier2_bond_price_index NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)) CHECK (tier2_bond_price_index > 0),
	tier2_bond_mod_duration NUMERIC NOT NULL CHECK (tier2_bond_mod_duration > 0) CHECK (tier2_bond_mod_duration NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)),
	tier3_stock_index_price NUMERIC NOT NULL CHECK (tier3_stock_index_price > 0) CHECK (tier3_stock_index_price NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)),
	tier3_stock_volatility_pct NUMERIC NOT NULL CHECK (tier3_stock_volatility_pct >= 0) CHECK (tier3_stock_volatility_pct NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)),
	tier1_early_redemption_haircut_pct NUMERIC NOT NULL CHECK (tier1_early_redemption_haircut_pct >= 0) CHECK (tier1_early_redemption_haircut_pct <= 100) CHECK (tier1_early_redemption_haircut_pct NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)),
	tier2_bond_liquidation_haircut_pct NUMERIC NOT NULL CHECK (tier2_bond_liquidation_haircut_pct >= 0) CHECK (tier2_bond_liquidation_haircut_pct NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)) CHECK (tier2_bond_liquidation_haircut_pct <= 100),
	tier3_stock_liquidation_haircut_pct NUMERIC NOT NULL CHECK (tier3_stock_liquidation_haircut_pct <= 100) CHECK (tier3_stock_liquidation_haircut_pct NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)) CHECK (tier3_stock_liquidation_haircut_pct >= 0),
	emergency_overdraft_penalty_apr_pct NUMERIC NOT NULL CHECK (emergency_overdraft_penalty_apr_pct NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)) CHECK (emergency_overdraft_penalty_apr_pct >= 0),
	PRIMARY KEY (dataset_id, timestamp),
	FOREIGN KEY(dataset_id) REFERENCES reserve_juggler_v1.dataset_sources (dataset_id)
);

ALTER TABLE reserve_juggler_v1.simulation_runs ADD COLUMN source_type VARCHAR(32);

ALTER TABLE reserve_juggler_v1.simulation_runs ADD COLUMN dataset_id TEXT;

ALTER TABLE reserve_juggler_v1.simulation_runs ADD COLUMN source_start_timestamp TIMESTAMP WITHOUT TIME ZONE;

ALTER TABLE reserve_juggler_v1.simulation_runs ADD COLUMN source_end_timestamp TIMESTAMP WITHOUT TIME ZONE;

ALTER TABLE reserve_juggler_v1.simulation_runs ADD COLUMN native_interval_seconds INTEGER;

ALTER TABLE reserve_juggler_v1.simulation_runs ADD COLUMN source_timezone_status VARCHAR(32);

ALTER TABLE reserve_juggler_v1.simulation_runs ADD COLUMN configuration_hash VARCHAR(64);

ALTER TABLE reserve_juggler_v1.simulation_runs ALTER COLUMN seed DROP NOT NULL;

ALTER TABLE reserve_juggler_v1.simulation_runs ALTER COLUMN started_at DROP NOT NULL;

ALTER TABLE reserve_juggler_v1.simulation_runs ALTER COLUMN "current_time" DROP NOT NULL;

ALTER TABLE reserve_juggler_v1.simulation_runs ADD CONSTRAINT uq_run_source_type UNIQUE(id,source_type);

ALTER TABLE reserve_juggler_v1.simulation_runs ADD CONSTRAINT uq_run_dataset UNIQUE(id,dataset_id);

ALTER TABLE reserve_juggler_v1.simulation_runs ADD CONSTRAINT ck_run_source CHECK (source_type IS NULL OR (
    configuration_hash IS NOT NULL AND configuration_hash ~ '^[0-9a-f]{64}$'
    AND native_interval_seconds IS NOT NULL AND native_interval_seconds > 0
    AND source_timezone_status IS NOT NULL AND (
      (source_type = 'ORGANIZER_HISTORICAL' AND dataset_id IS NOT NULL
       AND source_start_timestamp IS NOT NULL AND source_end_timestamp IS NOT NULL AND source_end_timestamp >= source_start_timestamp
       AND source_timezone_status = 'UNSPECIFIED' AND started_at IS NULL AND "current_time" IS NULL)
      OR (source_type = 'SYNTHETIC' AND dataset_id IS NULL AND source_start_timestamp IS NULL
          AND source_end_timestamp IS NULL AND source_timezone_status = 'UTC' AND seed IS NOT NULL))));

ALTER TABLE reserve_juggler_v1.simulation_runs ADD CONSTRAINT fk_run_dataset_interval FOREIGN KEY(dataset_id,native_interval_seconds) REFERENCES reserve_juggler_v1.dataset_sources(dataset_id,native_interval_seconds);

ALTER TABLE reserve_juggler_v1.simulation_runs ADD CONSTRAINT fk_run_first_observation FOREIGN KEY(dataset_id,source_start_timestamp) REFERENCES reserve_juggler_v1.organizer_observations(dataset_id,timestamp);

ALTER TABLE reserve_juggler_v1.simulation_runs ADD CONSTRAINT fk_run_last_observation FOREIGN KEY(dataset_id,source_end_timestamp) REFERENCES reserve_juggler_v1.organizer_observations(dataset_id,timestamp);

CREATE INDEX idx_run_dataset_source ON reserve_juggler_v1.simulation_runs(dataset_id,source_type);

ALTER TABLE reserve_juggler_v1.ledger_entries ADD COLUMN source_type VARCHAR(32);

ALTER TABLE reserve_juggler_v1.ledger_entries ADD COLUMN dataset_id TEXT;

ALTER TABLE reserve_juggler_v1.ledger_entries ADD COLUMN source_observation_timestamp TIMESTAMP WITHOUT TIME ZONE;

ALTER TABLE reserve_juggler_v1.ledger_entries ADD COLUMN event_at TIMESTAMP WITHOUT TIME ZONE;

ALTER TABLE reserve_juggler_v1.ledger_entries ALTER COLUMN timestamp DROP NOT NULL;

ALTER TABLE reserve_juggler_v1.ledger_entries ADD CONSTRAINT uq_ledger_run_id UNIQUE(run_id,id);

ALTER TABLE reserve_juggler_v1.treasury_decisions ADD COLUMN source_type VARCHAR(32);

ALTER TABLE reserve_juggler_v1.treasury_decisions ADD COLUMN dataset_id TEXT;

ALTER TABLE reserve_juggler_v1.treasury_decisions ADD COLUMN source_observation_timestamp TIMESTAMP WITHOUT TIME ZONE;

ALTER TABLE reserve_juggler_v1.treasury_decisions ADD COLUMN tier0_target_cents BIGINT CHECK (tier0_target_cents >= 0);

ALTER TABLE reserve_juggler_v1.treasury_decisions ADD COLUMN tier1_allocation_cents BIGINT CHECK (tier1_allocation_cents >= 0);

ALTER TABLE reserve_juggler_v1.treasury_decisions ADD COLUMN tier2_allocation_cents BIGINT CHECK (tier2_allocation_cents >= 0);

ALTER TABLE reserve_juggler_v1.treasury_decisions ADD COLUMN tier3_allocation_cents BIGINT CHECK (tier3_allocation_cents >= 0);

ALTER TABLE reserve_juggler_v1.treasury_decisions ADD COLUMN required_reserve_cents BIGINT CHECK (required_reserve_cents >= 0);

ALTER TABLE reserve_juggler_v1.treasury_decisions ADD COLUMN available_liquidity_cents BIGINT CHECK (available_liquidity_cents >= 0);

ALTER TABLE reserve_juggler_v1.treasury_decisions ADD COLUMN expected_inflow_cents BIGINT CHECK (expected_inflow_cents >= 0);

ALTER TABLE reserve_juggler_v1.treasury_decisions ADD COLUMN expected_outflow_cents BIGINT CHECK (expected_outflow_cents >= 0);

ALTER TABLE reserve_juggler_v1.treasury_decisions ADD COLUMN uncertainty_cents BIGINT CHECK (uncertainty_cents >= 0);

ALTER TABLE reserve_juggler_v1.treasury_decisions ALTER COLUMN timestamp DROP NOT NULL;

ALTER TABLE reserve_juggler_v1.treasury_decisions DROP CONSTRAINT IF EXISTS treasury_decisions_action_check;

ALTER TABLE reserve_juggler_v1.treasury_decisions ADD CONSTRAINT ck_decision_action CHECK(action IN ('HOLD','SWEEP','WITHDRAW','LIQUIDITY_WARNING','ALLOCATE'));

ALTER TABLE reserve_juggler_v1.ledger_entries ADD CONSTRAINT fk_ledger_entries_run_source FOREIGN KEY(run_id,source_type) REFERENCES reserve_juggler_v1.simulation_runs(id,source_type);

ALTER TABLE reserve_juggler_v1.ledger_entries ADD CONSTRAINT fk_ledger_entries_run_dataset FOREIGN KEY(run_id,dataset_id) REFERENCES reserve_juggler_v1.simulation_runs(id,dataset_id);

ALTER TABLE reserve_juggler_v1.ledger_entries ADD CONSTRAINT fk_ledger_entries_observation FOREIGN KEY(dataset_id,source_observation_timestamp) REFERENCES reserve_juggler_v1.organizer_observations(dataset_id,timestamp);

ALTER TABLE reserve_juggler_v1.ledger_entries ADD CONSTRAINT ck_ledger_entries_source CHECK ((source_type IS NULL AND dataset_id IS NULL AND source_observation_timestamp IS NULL) OR (source_type='ORGANIZER_HISTORICAL' AND dataset_id IS NOT NULL AND source_observation_timestamp IS NOT NULL AND timestamp IS NULL) OR (source_type='SYNTHETIC' AND dataset_id IS NULL AND source_observation_timestamp IS NULL));

ALTER TABLE reserve_juggler_v1.treasury_decisions ADD CONSTRAINT fk_treasury_decisions_run_source FOREIGN KEY(run_id,source_type) REFERENCES reserve_juggler_v1.simulation_runs(id,source_type);

ALTER TABLE reserve_juggler_v1.treasury_decisions ADD CONSTRAINT fk_treasury_decisions_run_dataset FOREIGN KEY(run_id,dataset_id) REFERENCES reserve_juggler_v1.simulation_runs(id,dataset_id);

ALTER TABLE reserve_juggler_v1.treasury_decisions ADD CONSTRAINT fk_treasury_decisions_observation FOREIGN KEY(dataset_id,source_observation_timestamp) REFERENCES reserve_juggler_v1.organizer_observations(dataset_id,timestamp);

ALTER TABLE reserve_juggler_v1.treasury_decisions ADD CONSTRAINT ck_treasury_decisions_source CHECK ((source_type IS NULL AND dataset_id IS NULL AND source_observation_timestamp IS NULL) OR (source_type='ORGANIZER_HISTORICAL' AND dataset_id IS NOT NULL AND source_observation_timestamp IS NOT NULL AND timestamp IS NULL) OR (source_type='SYNTHETIC' AND dataset_id IS NULL AND source_observation_timestamp IS NULL));

ALTER TABLE reserve_juggler_v1.ledger_entries ADD CONSTRAINT ck_ledger_source_time CHECK (source_type IS NULL OR event_at IS NOT NULL);

CREATE TABLE reserve_juggler_v1.bond_positions (
	supplied_yield_pct NUMERIC NOT NULL CHECK (supplied_yield_pct NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)),
	modified_duration NUMERIC NOT NULL CHECK (modified_duration > 0) CHECK (modified_duration NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)),
	quantity NUMERIC NOT NULL,
	acquisition_price_index NUMERIC NOT NULL,
	acquired_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	current_market_price_index NUMERIC,
	current_market_value_cents BIGINT,
	realized_pnl_cents BIGINT,
	unrealized_pnl_cents BIGINT,
	liquidation_haircut_pct NUMERIC NOT NULL,
	liquidation_cost_cents BIGINT,
	liquidation_proceeds_cents BIGINT,
	market_observation_timestamp TIMESTAMP WITHOUT TIME ZONE,
	status VARCHAR(16) NOT NULL,
	id UUID NOT NULL,
	run_id UUID NOT NULL,
	source_type VARCHAR(32) NOT NULL,
	dataset_id TEXT,
	source_observation_timestamp TIMESTAMP WITHOUT TIME ZONE,
	recorded_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	PRIMARY KEY (id),
	CHECK (quantity > 0 AND acquisition_price_index > 0),
	CHECK (current_market_price_index > 0 AND current_market_value_cents >= 0),
	CHECK (liquidation_haircut_pct BETWEEN 0 AND 100),
	CHECK (liquidation_cost_cents >= 0 AND liquidation_proceeds_cents >= 0),
	CHECK (status IN ('OPEN', 'CLOSED')),
	CHECK (quantity NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)),
	CHECK (acquisition_price_index NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)),
	CHECK (current_market_price_index NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)),
	CHECK (liquidation_haircut_pct NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)),
	FOREIGN KEY(dataset_id, market_observation_timestamp) REFERENCES reserve_juggler_v1.organizer_observations (dataset_id, timestamp),
	FOREIGN KEY(run_id) REFERENCES reserve_juggler_v1.simulation_runs (id),
	FOREIGN KEY(run_id, source_type) REFERENCES reserve_juggler_v1.simulation_runs (id, source_type),
	FOREIGN KEY(run_id, dataset_id) REFERENCES reserve_juggler_v1.simulation_runs (id, dataset_id),
	FOREIGN KEY(dataset_id, source_observation_timestamp) REFERENCES reserve_juggler_v1.organizer_observations (dataset_id, timestamp),
	CHECK ((source_type = 'ORGANIZER_HISTORICAL' AND dataset_id IS NOT NULL AND source_observation_timestamp IS NOT NULL) OR (source_type = 'SYNTHETIC' AND dataset_id IS NULL AND source_observation_timestamp IS NULL)),
	UNIQUE (run_id, id)
);

CREATE INDEX ix_reserve_juggler_v1_bond_positions_run_id ON reserve_juggler_v1.bond_positions (run_id, source_observation_timestamp);

CREATE TABLE reserve_juggler_v1.equity_positions (
	supplied_volatility_pct NUMERIC NOT NULL CHECK (supplied_volatility_pct NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)) CHECK (supplied_volatility_pct >= 0),
	quantity NUMERIC NOT NULL,
	acquisition_price_index NUMERIC NOT NULL,
	acquired_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	current_market_price_index NUMERIC,
	current_market_value_cents BIGINT,
	realized_pnl_cents BIGINT,
	unrealized_pnl_cents BIGINT,
	liquidation_haircut_pct NUMERIC NOT NULL,
	liquidation_cost_cents BIGINT,
	liquidation_proceeds_cents BIGINT,
	market_observation_timestamp TIMESTAMP WITHOUT TIME ZONE,
	status VARCHAR(16) NOT NULL,
	id UUID NOT NULL,
	run_id UUID NOT NULL,
	source_type VARCHAR(32) NOT NULL,
	dataset_id TEXT,
	source_observation_timestamp TIMESTAMP WITHOUT TIME ZONE,
	recorded_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	PRIMARY KEY (id),
	CHECK (quantity > 0 AND acquisition_price_index > 0),
	CHECK (current_market_price_index > 0 AND current_market_value_cents >= 0),
	CHECK (liquidation_haircut_pct BETWEEN 0 AND 100),
	CHECK (liquidation_cost_cents >= 0 AND liquidation_proceeds_cents >= 0),
	CHECK (status IN ('OPEN', 'CLOSED')),
	CHECK (quantity NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)),
	CHECK (acquisition_price_index NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)),
	CHECK (current_market_price_index NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)),
	CHECK (liquidation_haircut_pct NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)),
	FOREIGN KEY(dataset_id, market_observation_timestamp) REFERENCES reserve_juggler_v1.organizer_observations (dataset_id, timestamp),
	FOREIGN KEY(run_id) REFERENCES reserve_juggler_v1.simulation_runs (id),
	FOREIGN KEY(run_id, source_type) REFERENCES reserve_juggler_v1.simulation_runs (id, source_type),
	FOREIGN KEY(run_id, dataset_id) REFERENCES reserve_juggler_v1.simulation_runs (id, dataset_id),
	FOREIGN KEY(dataset_id, source_observation_timestamp) REFERENCES reserve_juggler_v1.organizer_observations (dataset_id, timestamp),
	CHECK ((source_type = 'ORGANIZER_HISTORICAL' AND dataset_id IS NOT NULL AND source_observation_timestamp IS NOT NULL) OR (source_type = 'SYNTHETIC' AND dataset_id IS NULL AND source_observation_timestamp IS NULL)),
	UNIQUE (run_id, id)
);

CREATE INDEX ix_reserve_juggler_v1_equity_positions_run_id ON reserve_juggler_v1.equity_positions (run_id, source_observation_timestamp);

CREATE TABLE reserve_juggler_v1.liquidity_breaches (
	occurred_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	shortfall_cents BIGINT NOT NULL CHECK (shortfall_cents >= 0),
	description TEXT NOT NULL,
	reference_id VARCHAR(200) NOT NULL,
	id UUID NOT NULL,
	run_id UUID NOT NULL,
	source_type VARCHAR(32) NOT NULL,
	dataset_id TEXT,
	source_observation_timestamp TIMESTAMP WITHOUT TIME ZONE,
	recorded_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (run_id, reference_id),
	FOREIGN KEY(run_id) REFERENCES reserve_juggler_v1.simulation_runs (id),
	FOREIGN KEY(run_id, source_type) REFERENCES reserve_juggler_v1.simulation_runs (id, source_type),
	FOREIGN KEY(run_id, dataset_id) REFERENCES reserve_juggler_v1.simulation_runs (id, dataset_id),
	FOREIGN KEY(dataset_id, source_observation_timestamp) REFERENCES reserve_juggler_v1.organizer_observations (dataset_id, timestamp),
	CHECK ((source_type = 'ORGANIZER_HISTORICAL' AND dataset_id IS NOT NULL AND source_observation_timestamp IS NOT NULL) OR (source_type = 'SYNTHETIC' AND dataset_id IS NULL AND source_observation_timestamp IS NULL)),
	UNIQUE (run_id, id)
);

CREATE INDEX ix_reserve_juggler_v1_liquidity_breaches_run_id ON reserve_juggler_v1.liquidity_breaches (run_id, source_observation_timestamp);

CREATE TABLE reserve_juggler_v1.portfolio_valuations (
	valued_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	tier0_cash_cents BIGINT NOT NULL CHECK (tier0_cash_cents >= 0),
	tier1_principal_cents BIGINT NOT NULL CHECK (tier1_principal_cents >= 0),
	tier1_value_cents BIGINT NOT NULL CHECK (tier1_value_cents >= 0),
	tier2_market_value_cents BIGINT NOT NULL CHECK (tier2_market_value_cents >= 0),
	tier3_market_value_cents BIGINT NOT NULL CHECK (tier3_market_value_cents >= 0),
	total_portfolio_value_cents BIGINT NOT NULL CHECK (total_portfolio_value_cents >= 0),
	immediately_available_cents BIGINT NOT NULL CHECK (immediately_available_cents >= 0),
	liquidatable_value_cents BIGINT NOT NULL CHECK (liquidatable_value_cents >= 0),
	restricted_value_cents BIGINT NOT NULL CHECK (restricted_value_cents >= 0),
	liabilities_cents BIGINT NOT NULL CHECK (liabilities_cents >= 0),
	net_portfolio_value_cents BIGINT NOT NULL,
	reference_id VARCHAR(200) NOT NULL,
	id UUID NOT NULL,
	run_id UUID NOT NULL,
	source_type VARCHAR(32) NOT NULL,
	dataset_id TEXT,
	source_observation_timestamp TIMESTAMP WITHOUT TIME ZONE,
	recorded_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (run_id, reference_id),
	CHECK (total_portfolio_value_cents = tier0_cash_cents + tier1_value_cents + tier2_market_value_cents + tier3_market_value_cents),
	CHECK (net_portfolio_value_cents = total_portfolio_value_cents - liabilities_cents),
	FOREIGN KEY(run_id) REFERENCES reserve_juggler_v1.simulation_runs (id),
	FOREIGN KEY(run_id, source_type) REFERENCES reserve_juggler_v1.simulation_runs (id, source_type),
	FOREIGN KEY(run_id, dataset_id) REFERENCES reserve_juggler_v1.simulation_runs (id, dataset_id),
	FOREIGN KEY(dataset_id, source_observation_timestamp) REFERENCES reserve_juggler_v1.organizer_observations (dataset_id, timestamp),
	CHECK ((source_type = 'ORGANIZER_HISTORICAL' AND dataset_id IS NOT NULL AND source_observation_timestamp IS NOT NULL) OR (source_type = 'SYNTHETIC' AND dataset_id IS NULL AND source_observation_timestamp IS NULL)),
	UNIQUE (run_id, id)
);

CREATE INDEX ix_reserve_juggler_v1_portfolio_valuations_run_id ON reserve_juggler_v1.portfolio_valuations (run_id, source_observation_timestamp);

CREATE TABLE reserve_juggler_v1.repo_positions (
	principal_cents BIGINT NOT NULL CHECK (principal_cents >= 0),
	entered_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	scheduled_maturity_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	applicable_apy_pct NUMERIC NOT NULL CHECK (applicable_apy_pct NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)),
	status VARCHAR(16) NOT NULL,
	early_redemption_at TIMESTAMP WITHOUT TIME ZONE,
	early_redemption_haircut_pct NUMERIC NOT NULL CHECK (early_redemption_haircut_pct >= 0) CHECK (early_redemption_haircut_pct <= 100) CHECK (early_redemption_haircut_pct NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)),
	accrued_interest_cents BIGINT,
	realized_interest_cents BIGINT,
	early_redemption_cost_cents BIGINT CHECK (early_redemption_cost_cents >= 0),
	proceeds_returned_cents BIGINT CHECK (proceeds_returned_cents >= 0),
	id UUID NOT NULL,
	run_id UUID NOT NULL,
	source_type VARCHAR(32) NOT NULL,
	dataset_id TEXT,
	source_observation_timestamp TIMESTAMP WITHOUT TIME ZONE,
	recorded_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	PRIMARY KEY (id),
	CHECK (scheduled_maturity_at > entered_at),
	CHECK (status IN ('LOCKED', 'MATURED', 'REDEEMED')),
	FOREIGN KEY(run_id) REFERENCES reserve_juggler_v1.simulation_runs (id),
	FOREIGN KEY(run_id, source_type) REFERENCES reserve_juggler_v1.simulation_runs (id, source_type),
	FOREIGN KEY(run_id, dataset_id) REFERENCES reserve_juggler_v1.simulation_runs (id, dataset_id),
	FOREIGN KEY(dataset_id, source_observation_timestamp) REFERENCES reserve_juggler_v1.organizer_observations (dataset_id, timestamp),
	CHECK ((source_type = 'ORGANIZER_HISTORICAL' AND dataset_id IS NOT NULL AND source_observation_timestamp IS NOT NULL) OR (source_type = 'SYNTHETIC' AND dataset_id IS NULL AND source_observation_timestamp IS NULL)),
	UNIQUE (run_id, id)
);

CREATE INDEX ix_reserve_juggler_v1_repo_positions_run_id ON reserve_juggler_v1.repo_positions (run_id, source_observation_timestamp);

CREATE TABLE reserve_juggler_v1.cash_accounts (
	balance_cents BIGINT NOT NULL CHECK (balance_cents >= 0),
	last_ledger_entry_id UUID,
	id UUID NOT NULL,
	run_id UUID NOT NULL,
	source_type VARCHAR(32) NOT NULL,
	dataset_id TEXT,
	source_observation_timestamp TIMESTAMP WITHOUT TIME ZONE,
	recorded_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (run_id),
	FOREIGN KEY(run_id, last_ledger_entry_id) REFERENCES reserve_juggler_v1.ledger_entries (run_id, id),
	FOREIGN KEY(run_id) REFERENCES reserve_juggler_v1.simulation_runs (id),
	FOREIGN KEY(run_id, source_type) REFERENCES reserve_juggler_v1.simulation_runs (id, source_type),
	FOREIGN KEY(run_id, dataset_id) REFERENCES reserve_juggler_v1.simulation_runs (id, dataset_id),
	FOREIGN KEY(dataset_id, source_observation_timestamp) REFERENCES reserve_juggler_v1.organizer_observations (dataset_id, timestamp),
	CHECK ((source_type = 'ORGANIZER_HISTORICAL' AND dataset_id IS NOT NULL AND source_observation_timestamp IS NOT NULL) OR (source_type = 'SYNTHETIC' AND dataset_id IS NULL AND source_observation_timestamp IS NULL)),
	UNIQUE (run_id, id)
);

CREATE INDEX ix_reserve_juggler_v1_cash_accounts_run_id ON reserve_juggler_v1.cash_accounts (run_id, source_observation_timestamp);

CREATE TABLE reserve_juggler_v1.investment_movements (
	kind VARCHAR(32) NOT NULL,
	occurred_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	cash_delta_cents BIGINT NOT NULL,
	principal_cents BIGINT CHECK (principal_cents >= 0),
	interest_cents BIGINT,
	haircut_cost_cents BIGINT CHECK (haircut_cost_cents >= 0),
	ledger_entry_id UUID,
	reference_id VARCHAR(200) NOT NULL,
	tier INTEGER NOT NULL,
	repo_position_id UUID,
	bond_position_id UUID,
	equity_position_id UUID,
	id UUID NOT NULL,
	run_id UUID NOT NULL,
	source_type VARCHAR(32) NOT NULL,
	dataset_id TEXT,
	source_observation_timestamp TIMESTAMP WITHOUT TIME ZONE,
	recorded_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (run_id, reference_id),
	FOREIGN KEY(run_id, ledger_entry_id) REFERENCES reserve_juggler_v1.ledger_entries (run_id, id),
	CHECK (kind IN ('INVESTMENT', 'REDEMPTION', 'LIQUIDATION', 'MATURITY', 'INTEREST', 'HAIRCUT', 'VALUATION')),
	CHECK (cash_delta_cents = 0 OR ledger_entry_id IS NOT NULL),
	FOREIGN KEY(run_id, repo_position_id) REFERENCES reserve_juggler_v1.repo_positions (run_id, id),
	FOREIGN KEY(run_id, bond_position_id) REFERENCES reserve_juggler_v1.bond_positions (run_id, id),
	FOREIGN KEY(run_id, equity_position_id) REFERENCES reserve_juggler_v1.equity_positions (run_id, id),
	CHECK ((tier=1 AND repo_position_id IS NOT NULL AND bond_position_id IS NULL AND equity_position_id IS NULL) OR (tier=2 AND repo_position_id IS NULL AND bond_position_id IS NOT NULL AND equity_position_id IS NULL) OR (tier=3 AND repo_position_id IS NULL AND bond_position_id IS NULL AND equity_position_id IS NOT NULL)),
	FOREIGN KEY(run_id) REFERENCES reserve_juggler_v1.simulation_runs (id),
	FOREIGN KEY(run_id, source_type) REFERENCES reserve_juggler_v1.simulation_runs (id, source_type),
	FOREIGN KEY(run_id, dataset_id) REFERENCES reserve_juggler_v1.simulation_runs (id, dataset_id),
	FOREIGN KEY(dataset_id, source_observation_timestamp) REFERENCES reserve_juggler_v1.organizer_observations (dataset_id, timestamp),
	CHECK ((source_type = 'ORGANIZER_HISTORICAL' AND dataset_id IS NOT NULL AND source_observation_timestamp IS NOT NULL) OR (source_type = 'SYNTHETIC' AND dataset_id IS NULL AND source_observation_timestamp IS NULL)),
	UNIQUE (run_id, id)
);

CREATE INDEX ix_reserve_juggler_v1_investment_movements_run_id ON reserve_juggler_v1.investment_movements (run_id, source_observation_timestamp);

CREATE TABLE reserve_juggler_v1.overdraft_liabilities (
	borrowed_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	borrowed_cents BIGINT NOT NULL CHECK (borrowed_cents >= 0),
	outstanding_principal_cents BIGINT NOT NULL CHECK (outstanding_principal_cents >= 0),
	repaid_principal_cents BIGINT NOT NULL CHECK (repaid_principal_cents >= 0),
	apr_pct NUMERIC NOT NULL CHECK (apr_pct >= 0) CHECK (apr_pct NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)),
	financing_cost_cents BIGINT CHECK (financing_cost_cents >= 0),
	breach_id UUID NOT NULL,
	reference_id VARCHAR(200) NOT NULL,
	id UUID NOT NULL,
	run_id UUID NOT NULL,
	source_type VARCHAR(32) NOT NULL,
	dataset_id TEXT,
	source_observation_timestamp TIMESTAMP WITHOUT TIME ZONE,
	recorded_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(run_id, breach_id) REFERENCES reserve_juggler_v1.liquidity_breaches (run_id, id),
	UNIQUE (run_id, reference_id),
	CHECK (outstanding_principal_cents + repaid_principal_cents = borrowed_cents),
	FOREIGN KEY(run_id) REFERENCES reserve_juggler_v1.simulation_runs (id),
	FOREIGN KEY(run_id, source_type) REFERENCES reserve_juggler_v1.simulation_runs (id, source_type),
	FOREIGN KEY(run_id, dataset_id) REFERENCES reserve_juggler_v1.simulation_runs (id, dataset_id),
	FOREIGN KEY(dataset_id, source_observation_timestamp) REFERENCES reserve_juggler_v1.organizer_observations (dataset_id, timestamp),
	CHECK ((source_type = 'ORGANIZER_HISTORICAL' AND dataset_id IS NOT NULL AND source_observation_timestamp IS NOT NULL) OR (source_type = 'SYNTHETIC' AND dataset_id IS NULL AND source_observation_timestamp IS NULL)),
	UNIQUE (run_id, id)
);

CREATE INDEX ix_reserve_juggler_v1_overdraft_liabilities_run_id ON reserve_juggler_v1.overdraft_liabilities (run_id, source_observation_timestamp);

CREATE TABLE reserve_juggler_v1.position_valuations (
	valued_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	market_price_index NUMERIC CHECK (market_price_index NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)) CHECK (market_price_index > 0),
	market_value_cents BIGINT NOT NULL CHECK (market_value_cents >= 0),
	realized_pnl_cents BIGINT,
	unrealized_pnl_cents BIGINT,
	reference_id VARCHAR(200) NOT NULL,
	tier INTEGER NOT NULL,
	repo_position_id UUID,
	bond_position_id UUID,
	equity_position_id UUID,
	id UUID NOT NULL,
	run_id UUID NOT NULL,
	source_type VARCHAR(32) NOT NULL,
	dataset_id TEXT,
	source_observation_timestamp TIMESTAMP WITHOUT TIME ZONE,
	recorded_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (run_id, reference_id),
	FOREIGN KEY(run_id, repo_position_id) REFERENCES reserve_juggler_v1.repo_positions (run_id, id),
	FOREIGN KEY(run_id, bond_position_id) REFERENCES reserve_juggler_v1.bond_positions (run_id, id),
	FOREIGN KEY(run_id, equity_position_id) REFERENCES reserve_juggler_v1.equity_positions (run_id, id),
	CHECK ((tier=1 AND repo_position_id IS NOT NULL AND bond_position_id IS NULL AND equity_position_id IS NULL) OR (tier=2 AND repo_position_id IS NULL AND bond_position_id IS NOT NULL AND equity_position_id IS NULL) OR (tier=3 AND repo_position_id IS NULL AND bond_position_id IS NULL AND equity_position_id IS NOT NULL)),
	FOREIGN KEY(run_id) REFERENCES reserve_juggler_v1.simulation_runs (id),
	FOREIGN KEY(run_id, source_type) REFERENCES reserve_juggler_v1.simulation_runs (id, source_type),
	FOREIGN KEY(run_id, dataset_id) REFERENCES reserve_juggler_v1.simulation_runs (id, dataset_id),
	FOREIGN KEY(dataset_id, source_observation_timestamp) REFERENCES reserve_juggler_v1.organizer_observations (dataset_id, timestamp),
	CHECK ((source_type = 'ORGANIZER_HISTORICAL' AND dataset_id IS NOT NULL AND source_observation_timestamp IS NOT NULL) OR (source_type = 'SYNTHETIC' AND dataset_id IS NULL AND source_observation_timestamp IS NULL)),
	UNIQUE (run_id, id)
);

CREATE INDEX ix_reserve_juggler_v1_position_valuations_run_id ON reserve_juggler_v1.position_valuations (run_id, source_observation_timestamp);

CREATE TABLE reserve_juggler_v1.overdraft_movements (
	liability_id UUID NOT NULL,
	occurred_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	kind VARCHAR(32) NOT NULL,
	principal_cents BIGINT NOT NULL CHECK (principal_cents >= 0),
	financing_cost_cents BIGINT NOT NULL CHECK (financing_cost_cents >= 0),
	cash_delta_cents BIGINT NOT NULL,
	ledger_entry_id UUID,
	reference_id VARCHAR(200) NOT NULL,
	id UUID NOT NULL,
	run_id UUID NOT NULL,
	source_type VARCHAR(32) NOT NULL,
	dataset_id TEXT,
	source_observation_timestamp TIMESTAMP WITHOUT TIME ZONE,
	recorded_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(run_id, liability_id) REFERENCES reserve_juggler_v1.overdraft_liabilities (run_id, id),
	FOREIGN KEY(run_id, ledger_entry_id) REFERENCES reserve_juggler_v1.ledger_entries (run_id, id),
	UNIQUE (run_id, reference_id),
	CHECK (kind IN ('BORROW', 'REPAYMENT', 'FINANCING_COST')),
	CHECK (cash_delta_cents = 0 OR ledger_entry_id IS NOT NULL),
	FOREIGN KEY(run_id) REFERENCES reserve_juggler_v1.simulation_runs (id),
	FOREIGN KEY(run_id, source_type) REFERENCES reserve_juggler_v1.simulation_runs (id, source_type),
	FOREIGN KEY(run_id, dataset_id) REFERENCES reserve_juggler_v1.simulation_runs (id, dataset_id),
	FOREIGN KEY(dataset_id, source_observation_timestamp) REFERENCES reserve_juggler_v1.organizer_observations (dataset_id, timestamp),
	CHECK ((source_type = 'ORGANIZER_HISTORICAL' AND dataset_id IS NOT NULL AND source_observation_timestamp IS NOT NULL) OR (source_type = 'SYNTHETIC' AND dataset_id IS NULL AND source_observation_timestamp IS NULL)),
	UNIQUE (run_id, id)
);

CREATE INDEX ix_reserve_juggler_v1_overdraft_movements_run_id ON reserve_juggler_v1.overdraft_movements (run_id, source_observation_timestamp);
