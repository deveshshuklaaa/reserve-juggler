from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict

class HealthStatus(BaseModel):
    status: str
    database: str
    timestamp: datetime

class TransactionBase(BaseModel):
    timestamp: datetime
    type: str # DEPOSIT, WITHDRAWAL, MERCHANT_SETTLEMENT
    amount: float
    source: str
    scenario: Optional[str] = "baseline"

class TransactionCreate(TransactionBase):
    pass

class Transaction(TransactionBase):
    id: int
    model_config = ConfigDict(from_attributes=True)

class ForecastBase(BaseModel):
    timestamp: datetime
    horizon_minutes: int
    predicted_inflow: float
    predicted_outflow: float
    predicted_net_flow: float
    uncertainty: float
    model_version: str

class Forecast(ForecastBase):
    id: Optional[int] = None
    model_config = ConfigDict(from_attributes=True)

class LiquiditySnapshot(BaseModel):
    id: Optional[int] = None
    timestamp: datetime
    checking_balance: float
    vault_balance: float
    required_reserve: float
    deployable_cash: float
    model_config = ConfigDict(from_attributes=True)

class Decision(BaseModel):
    id: Optional[int] = None
    timestamp: datetime
    decision_type: str # HOLD, SWEEP, WITHDRAW, LIQUIDITY_WARNING
    amount: float
    required_reserve: float
    forecast_value: float
    forecast_uncertainty: float
    safety_buffer: float
    reason: str
    model_config = ConfigDict(from_attributes=True)

class TreasuryState(BaseModel):
    liquidity: LiquiditySnapshot
    latest_decision: Decision
    active_forecast: Forecast
    system_status: str = "operational"

class SimulationStartRequest(BaseModel):
    scenario: str = "baseline"
    duration_minutes: int = 60

class ScenarioConfigRequest(BaseModel):
    scenario: str
    intensity: float = 1.0

class SimulationRun(BaseModel):
    id: int
    scenario: str
    started_at: datetime
    ended_at: Optional[datetime] = None
    total_yield: float = 0.0
    reserve_breaches: int = 0
    emergency_events: int = 0
    model_config = ConfigDict(from_attributes=True)

class TreasuryMetrics(BaseModel):
    total_yield_earned: float
    idle_cash_ratio: float
    reserve_breach_count: int
    current_apy: float
