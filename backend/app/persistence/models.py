"""Four-tier storage models. No valuation, trading, or interest calculations.

This metadata is deliberately separate from the legacy public-schema Base.
Only the migration runner creates/updates these tables.
"""

from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, Column, DateTime, ForeignKey,
    ForeignKeyConstraint, Index, Integer, Numeric, String, Text, UniqueConstraint,
    Uuid, func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base
from sqlalchemy.types import TypeDecorator


SCHEMA = "reserve_juggler_v1"
Base = declarative_base()


class ExactNumeric(TypeDecorator):
    impl = Numeric
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None and (not isinstance(value, Decimal) or not value.is_finite()):
            raise ValueError("Exact financial values must be finite Decimal objects")
        return value


class Cents(TypeDecorator):
    impl = BigInteger
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None and type(value) is not int:
            raise ValueError("Money must be integer cents")
        return value


class SourceTime(TypeDecorator):
    impl = DateTime(timezone=False)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None and (not isinstance(value, datetime) or value.tzinfo is not None):
            raise ValueError("Source time must be naive, with timezone status recorded on the source/run")
        return value


def money(name, nullable=False, signed=False):
    constraints = [] if signed else [CheckConstraint(f"{name} >= 0")]
    return Column(Cents(), *constraints, nullable=nullable)


def exact(name, nullable=False, positive=False, nonnegative=False, haircut=False):
    checks = [CheckConstraint(f"{name} NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)")]
    if positive:
        checks.append(CheckConstraint(f"{name} > 0"))
    if nonnegative or haircut:
        checks.append(CheckConstraint(f"{name} >= 0"))
    if haircut:
        checks.append(CheckConstraint(f"{name} <= 100"))
    return Column(ExactNumeric(), *checks, nullable=nullable)


class DatasetSource(Base):
    __tablename__ = "dataset_sources"
    __table_args__ = (
        UniqueConstraint("content_hash"),
        UniqueConstraint("dataset_id", "native_interval_seconds"),
        CheckConstraint("row_count > 0 AND native_interval_seconds > 0"),
        CheckConstraint("last_timestamp >= first_timestamp"),
        CheckConstraint("content_hash ~ '^[0-9a-f]{64}$'"),
        CheckConstraint("source_type = 'ORGANIZER_CSV' AND timezone_status = 'UNSPECIFIED'"),
        CheckConstraint("validation_status IN ('VALIDATED', 'VALIDATED_WITH_DIAGNOSTICS')"),
        {"schema": SCHEMA},
    )
    dataset_id = Column(Text, primary_key=True)
    dataset_name = Column(Text, nullable=False)
    source_type = Column(String(32), nullable=False)
    source_path = Column(Text, nullable=False)
    content_hash = Column(String(64), nullable=False)
    hash_algorithm = Column(String(16), CheckConstraint("hash_algorithm = 'sha256'"), nullable=False)
    row_count = Column(Integer, nullable=False)
    first_timestamp = Column(SourceTime(), nullable=False)
    last_timestamp = Column(SourceTime(), nullable=False)
    native_interval_seconds = Column(Integer, nullable=False)
    timezone_status = Column(String(32), nullable=False)
    validation_status = Column(String(40), nullable=False)
    validation_json = Column(JSONB, nullable=False)


class OrganizerObservation(Base):
    __tablename__ = "organizer_observations"
    __table_args__ = ({"schema": SCHEMA},)
    dataset_id = Column(Text, ForeignKey(f"{SCHEMA}.dataset_sources.dataset_id"), primary_key=True)
    timestamp = Column(SourceTime(), primary_key=True)
    deposits_usd = exact("deposits_usd", nonnegative=True)
    withdrawals_usd = exact("withdrawals_usd", nonnegative=True)
    net_flow_usd = exact("net_flow_usd")
    repo_sweep_window_open = Column(Boolean, nullable=False)
    repo_sweep_mature = Column(Boolean, nullable=False)
    tier1_repo_rate_apy = exact("tier1_repo_rate_apy")
    tier2_bond_yield_pct = exact("tier2_bond_yield_pct")
    tier2_bond_price_index = exact("tier2_bond_price_index", positive=True)
    tier2_bond_mod_duration = exact("tier2_bond_mod_duration", positive=True)
    tier3_stock_index_price = exact("tier3_stock_index_price", positive=True)
    tier3_stock_volatility_pct = exact("tier3_stock_volatility_pct", nonnegative=True)
    tier1_early_redemption_haircut_pct = exact("tier1_early_redemption_haircut_pct", haircut=True)
    tier2_bond_liquidation_haircut_pct = exact("tier2_bond_liquidation_haircut_pct", haircut=True)
    tier3_stock_liquidation_haircut_pct = exact("tier3_stock_liquidation_haircut_pct", haircut=True)
    emergency_overdraft_penalty_apr_pct = exact("emergency_overdraft_penalty_apr_pct", nonnegative=True)


RUN_SOURCE_CHECK = """source_type IS NULL OR (
    configuration_hash IS NOT NULL AND configuration_hash ~ '^[0-9a-f]{64}$'
    AND native_interval_seconds IS NOT NULL AND native_interval_seconds > 0
    AND source_timezone_status IS NOT NULL AND (
      (source_type = 'ORGANIZER_HISTORICAL' AND dataset_id IS NOT NULL
       AND source_start_timestamp IS NOT NULL AND source_end_timestamp IS NOT NULL AND source_end_timestamp >= source_start_timestamp
       AND source_timezone_status = 'UNSPECIFIED' AND started_at IS NULL AND "current_time" IS NULL)
      OR (source_type = 'SYNTHETIC' AND dataset_id IS NULL AND source_start_timestamp IS NULL
          AND source_end_timestamp IS NULL AND source_timezone_status = 'UTC' AND seed IS NOT NULL)))"""


class SimulationRun(Base):
    """Extends migration 002; NULL source_type identifies unmigrated legacy rows."""
    __tablename__ = "simulation_runs"
    __table_args__ = (
        UniqueConstraint("id", "source_type", name="uq_run_source_type"),
        UniqueConstraint("id", "dataset_id", name="uq_run_dataset"),
        ForeignKeyConstraint(["dataset_id", "native_interval_seconds"],
                             [f"{SCHEMA}.dataset_sources.dataset_id", f"{SCHEMA}.dataset_sources.native_interval_seconds"]),
        ForeignKeyConstraint(["dataset_id", "source_start_timestamp"],
                             [f"{SCHEMA}.organizer_observations.dataset_id", f"{SCHEMA}.organizer_observations.timestamp"]),
        ForeignKeyConstraint(["dataset_id", "source_end_timestamp"],
                             [f"{SCHEMA}.organizer_observations.dataset_id", f"{SCHEMA}.organizer_observations.timestamp"]),
        CheckConstraint(RUN_SOURCE_CHECK, name="ck_run_source"),
        {"schema": SCHEMA},
    )
    id = Column(Uuid, primary_key=True, default=uuid4)
    seed = Column(Integer, nullable=True)
    scenario = Column(String(32), nullable=False)
    status = Column(String(32), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    current_time = Column(DateTime(timezone=True), nullable=True)
    current_step = Column(Integer, nullable=False, server_default="0")
    duration_steps = Column(Integer, nullable=False)
    initial_cash_cents = money("initial_cash_cents")
    policy_json = Column(JSONB, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.current_timestamp(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.current_timestamp(), nullable=False)
    source_type = Column(String(32))
    dataset_id = Column(Text)
    source_start_timestamp = Column(SourceTime())
    source_end_timestamp = Column(SourceTime())
    native_interval_seconds = Column(Integer)
    source_timezone_status = Column(String(32))
    configuration_hash = Column(String(64))


class LedgerEntry(Base):
    """Maps the existing migration-002 ledger; no posting/calculation methods."""
    __tablename__ = "ledger_entries"
    __table_args__ = (UniqueConstraint("run_id", "id", name="uq_ledger_run_id"), {"schema": SCHEMA})
    id = Column(Uuid, primary_key=True, default=uuid4)
    run_id = Column(Uuid, ForeignKey(f"{SCHEMA}.simulation_runs.id"), nullable=False)
    step = Column(Integer, nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=True)
    entry_type = Column(String(64), nullable=False)
    amount_cents = money("amount_cents")
    balance_before_cents = money("balance_before_cents")
    balance_after_cents = money("balance_after_cents")
    reference_id = Column(String(200), nullable=False)
    source_type = Column(String(32))
    dataset_id = Column(Text)
    source_observation_timestamp = Column(SourceTime())
    event_at = Column(SourceTime())


def source_constraints():
    return (
        ForeignKeyConstraint(["run_id"], [f"{SCHEMA}.simulation_runs.id"]),
        ForeignKeyConstraint(["run_id", "source_type"],
                             [f"{SCHEMA}.simulation_runs.id", f"{SCHEMA}.simulation_runs.source_type"]),
        ForeignKeyConstraint(["run_id", "dataset_id"],
                             [f"{SCHEMA}.simulation_runs.id", f"{SCHEMA}.simulation_runs.dataset_id"]),
        ForeignKeyConstraint(["dataset_id", "source_observation_timestamp"],
                             [f"{SCHEMA}.organizer_observations.dataset_id", f"{SCHEMA}.organizer_observations.timestamp"]),
        CheckConstraint("(source_type = 'ORGANIZER_HISTORICAL' AND dataset_id IS NOT NULL AND source_observation_timestamp IS NOT NULL) OR (source_type = 'SYNTHETIC' AND dataset_id IS NULL AND source_observation_timestamp IS NULL)"),
    )


def same_run_fk(column, table):
    return ForeignKeyConstraint(["run_id", column], [f"{SCHEMA}.{table}.run_id", f"{SCHEMA}.{table}.id"])


def record_args(*constraints):
    return (*source_constraints(), UniqueConstraint("run_id", "id"),
            Index(None, "run_id", "source_observation_timestamp"), *constraints, {"schema": SCHEMA})


class SourceLinked:
    id = Column(Uuid, primary_key=True, default=uuid4)
    run_id = Column(Uuid, nullable=False)
    source_type = Column(String(32), nullable=False)
    dataset_id = Column(Text)
    source_observation_timestamp = Column(SourceTime())
    recorded_at = Column(DateTime(timezone=True), nullable=False, server_default=func.current_timestamp())


class CashAccount(SourceLinked, Base):
    __tablename__ = "cash_accounts"
    __table_args__ = record_args(UniqueConstraint("run_id"), same_run_fk("last_ledger_entry_id", "ledger_entries"))
    balance_cents = money("balance_cents")
    last_ledger_entry_id = Column(Uuid)


class RepoPosition(SourceLinked, Base):
    __tablename__ = "repo_positions"
    __table_args__ = record_args(CheckConstraint("scheduled_maturity_at > entered_at"),
                                CheckConstraint("status IN ('LOCKED', 'MATURED', 'REDEEMED')"))
    principal_cents = money("principal_cents")
    entered_at = Column(SourceTime(), nullable=False)
    scheduled_maturity_at = Column(SourceTime(), nullable=False)
    applicable_apy_pct = exact("applicable_apy_pct")
    status = Column(String(16), nullable=False)
    early_redemption_at = Column(SourceTime())
    early_redemption_haircut_pct = exact("early_redemption_haircut_pct", haircut=True)
    accrued_interest_cents = money("accrued_interest_cents", nullable=True, signed=True)
    realized_interest_cents = money("realized_interest_cents", nullable=True, signed=True)
    early_redemption_cost_cents = money("early_redemption_cost_cents", nullable=True)
    proceeds_returned_cents = money("proceeds_returned_cents", nullable=True)


class MarketPosition(SourceLinked):
    quantity = Column(ExactNumeric(), nullable=False)
    acquisition_price_index = Column(ExactNumeric(), nullable=False)
    acquired_at = Column(SourceTime(), nullable=False)
    current_market_price_index = Column(ExactNumeric())
    current_market_value_cents = Column(Cents())
    realized_pnl_cents = Column(Cents())
    unrealized_pnl_cents = Column(Cents())
    liquidation_haircut_pct = Column(ExactNumeric(), nullable=False)
    liquidation_cost_cents = Column(Cents())
    liquidation_proceeds_cents = Column(Cents())
    market_observation_timestamp = Column(SourceTime())
    status = Column(String(16), nullable=False)


def market_args(*constraints):
    return record_args(
        CheckConstraint("quantity > 0 AND acquisition_price_index > 0"),
        CheckConstraint("current_market_price_index > 0 AND current_market_value_cents >= 0"),
        CheckConstraint("liquidation_haircut_pct BETWEEN 0 AND 100"),
        CheckConstraint("liquidation_cost_cents >= 0 AND liquidation_proceeds_cents >= 0"),
        CheckConstraint("status IN ('OPEN', 'CLOSED')"),
        *[CheckConstraint(f"{name} NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)")
          for name in ("quantity", "acquisition_price_index", "current_market_price_index", "liquidation_haircut_pct")],
        ForeignKeyConstraint(["dataset_id", "market_observation_timestamp"],
                             [f"{SCHEMA}.organizer_observations.dataset_id", f"{SCHEMA}.organizer_observations.timestamp"]),
        *constraints,
    )


class BondPosition(MarketPosition, Base):
    __tablename__ = "bond_positions"
    __table_args__ = market_args()
    supplied_yield_pct = exact("supplied_yield_pct")
    modified_duration = exact("modified_duration", positive=True)


class EquityPosition(MarketPosition, Base):
    __tablename__ = "equity_positions"
    __table_args__ = market_args()
    supplied_volatility_pct = exact("supplied_volatility_pct", nonnegative=True)


class PositionLinked(SourceLinked):
    tier = Column(Integer, nullable=False)
    repo_position_id = Column(Uuid)
    bond_position_id = Column(Uuid)
    equity_position_id = Column(Uuid)


def position_args(*constraints):
    return record_args(
        same_run_fk("repo_position_id", "repo_positions"),
        same_run_fk("bond_position_id", "bond_positions"),
        same_run_fk("equity_position_id", "equity_positions"),
        CheckConstraint("(tier=1 AND repo_position_id IS NOT NULL AND bond_position_id IS NULL AND equity_position_id IS NULL) OR (tier=2 AND repo_position_id IS NULL AND bond_position_id IS NOT NULL AND equity_position_id IS NULL) OR (tier=3 AND repo_position_id IS NULL AND bond_position_id IS NULL AND equity_position_id IS NOT NULL)"),
        *constraints,
    )


class PositionValuation(PositionLinked, Base):
    __tablename__ = "position_valuations"
    __table_args__ = position_args(UniqueConstraint("run_id", "reference_id"))
    valued_at = Column(SourceTime(), nullable=False)
    market_price_index = exact("market_price_index", nullable=True, positive=True)
    market_value_cents = money("market_value_cents")
    realized_pnl_cents = money("realized_pnl_cents", nullable=True, signed=True)
    unrealized_pnl_cents = money("unrealized_pnl_cents", nullable=True, signed=True)
    reference_id = Column(String(200), nullable=False)


class InvestmentMovement(PositionLinked, Base):
    __tablename__ = "investment_movements"
    __table_args__ = position_args(
        UniqueConstraint("run_id", "reference_id"), same_run_fk("ledger_entry_id", "ledger_entries"),
        CheckConstraint("kind IN ('INVESTMENT', 'REDEMPTION', 'LIQUIDATION', 'MATURITY', 'INTEREST', 'HAIRCUT', 'VALUATION')"),
        CheckConstraint("cash_delta_cents = 0 OR ledger_entry_id IS NOT NULL"),
    )
    kind = Column(String(32), nullable=False)
    occurred_at = Column(SourceTime(), nullable=False)
    cash_delta_cents = money("cash_delta_cents", signed=True)
    principal_cents = money("principal_cents", nullable=True)
    interest_cents = money("interest_cents", nullable=True, signed=True)
    haircut_cost_cents = money("haircut_cost_cents", nullable=True)
    ledger_entry_id = Column(Uuid)
    reference_id = Column(String(200), nullable=False)


class PortfolioValuation(SourceLinked, Base):
    __tablename__ = "portfolio_valuations"
    __table_args__ = record_args(
        UniqueConstraint("run_id", "reference_id"),
        CheckConstraint("total_portfolio_value_cents = tier0_cash_cents + tier1_value_cents + tier2_market_value_cents + tier3_market_value_cents"),
        CheckConstraint("net_portfolio_value_cents = total_portfolio_value_cents - liabilities_cents"),
    )
    valued_at = Column(SourceTime(), nullable=False)
    tier0_cash_cents = money("tier0_cash_cents")
    tier1_principal_cents = money("tier1_principal_cents")
    tier1_value_cents = money("tier1_value_cents")
    tier2_market_value_cents = money("tier2_market_value_cents")
    tier3_market_value_cents = money("tier3_market_value_cents")
    total_portfolio_value_cents = money("total_portfolio_value_cents")
    immediately_available_cents = money("immediately_available_cents")
    liquidatable_value_cents = money("liquidatable_value_cents")
    restricted_value_cents = money("restricted_value_cents")
    liabilities_cents = money("liabilities_cents")
    net_portfolio_value_cents = money("net_portfolio_value_cents", signed=True)
    reference_id = Column(String(200), nullable=False)


class LiquidityBreach(SourceLinked, Base):
    __tablename__ = "liquidity_breaches"
    __table_args__ = record_args(UniqueConstraint("run_id", "reference_id"))
    occurred_at = Column(SourceTime(), nullable=False)
    shortfall_cents = money("shortfall_cents")
    description = Column(Text, nullable=False)
    reference_id = Column(String(200), nullable=False)


class OverdraftLiability(SourceLinked, Base):
    __tablename__ = "overdraft_liabilities"
    __table_args__ = record_args(
        same_run_fk("breach_id", "liquidity_breaches"), UniqueConstraint("run_id", "reference_id"),
        CheckConstraint("outstanding_principal_cents + repaid_principal_cents = borrowed_cents"),
    )
    borrowed_at = Column(SourceTime(), nullable=False)
    borrowed_cents = money("borrowed_cents")
    outstanding_principal_cents = money("outstanding_principal_cents")
    repaid_principal_cents = money("repaid_principal_cents")
    apr_pct = exact("apr_pct", nonnegative=True)
    financing_cost_cents = money("financing_cost_cents", nullable=True)
    breach_id = Column(Uuid, nullable=False)
    reference_id = Column(String(200), nullable=False)


class OverdraftMovement(SourceLinked, Base):
    __tablename__ = "overdraft_movements"
    __table_args__ = record_args(
        same_run_fk("liability_id", "overdraft_liabilities"), same_run_fk("ledger_entry_id", "ledger_entries"),
        UniqueConstraint("run_id", "reference_id"),
        CheckConstraint("kind IN ('BORROW', 'REPAYMENT', 'FINANCING_COST')"),
        CheckConstraint("cash_delta_cents = 0 OR ledger_entry_id IS NOT NULL"),
    )
    liability_id = Column(Uuid, nullable=False)
    occurred_at = Column(SourceTime(), nullable=False)
    kind = Column(String(32), nullable=False)
    principal_cents = money("principal_cents")
    financing_cost_cents = money("financing_cost_cents")
    cash_delta_cents = money("cash_delta_cents", signed=True)
    ledger_entry_id = Column(Uuid)
    reference_id = Column(String(200), nullable=False)


class TreasuryDecision(Base):
    """Existing table, extended with allocation targets rather than fake executions."""
    __tablename__ = "treasury_decisions"
    __table_args__ = ({"schema": SCHEMA},)
    id = Column(Uuid, primary_key=True, default=uuid4)
    run_id = Column(Uuid, ForeignKey(f"{SCHEMA}.simulation_runs.id"), nullable=False)
    step = Column(Integer, nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=True)
    action = Column(String(32), nullable=False)
    amount_cents = money("amount_cents")
    execution_status = Column(String(32), nullable=False)
    explanation_json = Column(JSONB, nullable=False)
    decision_details_json = Column(JSONB, nullable=False)
    dataset_id = Column(Text)
    source_type = Column(String(32))
    source_observation_timestamp = Column(SourceTime())
    tier0_target_cents = money("tier0_target_cents", nullable=True)
    tier1_allocation_cents = money("tier1_allocation_cents", nullable=True)
    tier2_allocation_cents = money("tier2_allocation_cents", nullable=True)
    tier3_allocation_cents = money("tier3_allocation_cents", nullable=True)
    required_reserve_cents = money("required_reserve_cents", nullable=True)
    available_liquidity_cents = money("available_liquidity_cents", nullable=True)
    expected_inflow_cents = money("expected_inflow_cents", nullable=True)
    expected_outflow_cents = money("expected_outflow_cents", nullable=True)
    uncertainty_cents = money("uncertainty_cents", nullable=True)
