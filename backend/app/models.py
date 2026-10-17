from datetime import datetime
from sqlalchemy import Column, Integer, String, Numeric, DateTime, Text
from app.database import Base

class TransactionModel(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False, index=True)
    type = Column(String(50), nullable=False) # DEPOSIT, WITHDRAWAL, MERCHANT_SETTLEMENT
    amount = Column(Numeric(18, 4), nullable=False)
    source = Column(String(100), nullable=False)
    scenario = Column(String(100), default="baseline", index=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

class ForecastModel(Base):
    __tablename__ = "forecasts"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False, index=True)
    horizon_minutes = Column(Integer, nullable=False)
    predicted_inflow = Column(Numeric(18, 4), nullable=False)
    predicted_outflow = Column(Numeric(18, 4), nullable=False)
    predicted_net_flow = Column(Numeric(18, 4), nullable=False)
    uncertainty = Column(Numeric(18, 4), nullable=False)
    model_version = Column(String(50), nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

class LiquiditySnapshotModel(Base):
    __tablename__ = "liquidity_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False, index=True)
    checking_balance = Column(Numeric(18, 4), nullable=False)
    vault_balance = Column(Numeric(18, 4), nullable=False)
    required_reserve = Column(Numeric(18, 4), nullable=False)
    deployable_cash = Column(Numeric(18, 4), nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

class DecisionModel(Base):
    __tablename__ = "decisions"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False, index=True)
    decision_type = Column(String(50), nullable=False, index=True) # HOLD, SWEEP, WITHDRAW, LIQUIDITY_WARNING
    amount = Column(Numeric(18, 4), nullable=False)
    required_reserve = Column(Numeric(18, 4), nullable=False)
    forecast_value = Column(Numeric(18, 4), nullable=False)
    forecast_uncertainty = Column(Numeric(18, 4), nullable=False)
    safety_buffer = Column(Numeric(18, 4), nullable=False)
    reason = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

class SimulationRunModel(Base):
    __tablename__ = "simulation_runs"

    id = Column(Integer, primary_key=True, index=True)
    scenario = Column(String(100), nullable=False)
    started_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    total_yield = Column(Numeric(18, 4), default=0.0)
    reserve_breaches = Column(Integer, default=0)
    emergency_events = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
