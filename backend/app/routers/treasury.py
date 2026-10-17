from datetime import datetime
from typing import List
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import LiquiditySnapshotModel, DecisionModel, ForecastModel
from app.schemas import LiquiditySnapshot, Decision, Forecast, TreasuryState, TreasuryMetrics
from app.treasury.engine import TreasuryDecisionEngine
from app.config import settings

router = APIRouter(prefix="/api", tags=["Treasury"])
engine = TreasuryDecisionEngine(
    base_safety_buffer=settings.BASE_SAFETY_BUFFER,
    uncertainty_multiplier=settings.UNCERTAINTY_MULTIPLIER,
    min_sweep_threshold=settings.MIN_SWEEP_THRESHOLD
)

@router.get("/liquidity/current", response_model=LiquiditySnapshot)
def get_current_liquidity(db: Session = Depends(get_db)):
    snapshot = db.query(LiquiditySnapshotModel).order_by(LiquiditySnapshotModel.timestamp.desc()).first()
    if not snapshot:
        # Fallback baseline
        return {
            "id": 1,
            "timestamp": datetime.utcnow(),
            "checking_balance": 750000.0,
            "vault_balance": 3250000.0,
            "required_reserve": 520000.0,
            "deployable_cash": 230000.0
        }
    return snapshot

@router.get("/forecast/current", response_model=Forecast)
def get_current_forecast(db: Session = Depends(get_db)):
    fc = db.query(ForecastModel).order_by(ForecastModel.timestamp.desc()).first()
    if not fc:
        return {
            "id": 1,
            "timestamp": datetime.utcnow(),
            "horizon_minutes": 60,
            "predicted_inflow": 220000.0,
            "predicted_outflow": 180000.0,
            "predicted_net_flow": 40000.0,
            "uncertainty": 25000.0,
            "model_version": "v0.1-quantile-baseline"
        }
    return fc

@router.get("/decisions/latest", response_model=Decision)
def get_latest_decision(db: Session = Depends(get_db)):
    dec = db.query(DecisionModel).order_by(DecisionModel.timestamp.desc()).first()
    if not dec:
        return {
            "id": 1,
            "timestamp": datetime.utcnow(),
            "decision_type": "SWEEP",
            "amount": 180000.0,
            "required_reserve": 520000.0,
            "forecast_value": 40000.0,
            "forecast_uncertainty": 25000.0,
            "safety_buffer": 50000.0,
            "reason": "Baseline sweep decision: checking exceeds reserve requirement."
        }
    return dec

@router.get("/decisions/history", response_model=List[Decision])
def get_decisions_history(limit: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)):
    return db.query(DecisionModel).order_by(DecisionModel.timestamp.desc()).limit(limit).all()

@router.get("/treasury/state", response_model=TreasuryState)
def get_treasury_state(db: Session = Depends(get_db)):
    liquidity = get_current_liquidity(db)
    decision = get_latest_decision(db)
    forecast = get_current_forecast(db)
    return {
        "liquidity": liquidity,
        "latest_decision": decision,
        "active_forecast": forecast,
        "system_status": "operational"
    }

@router.get("/metrics", response_model=TreasuryMetrics)
def get_treasury_metrics(db: Session = Depends(get_db)):
    return {
        "total_yield_earned": 1428.60,
        "idle_cash_ratio": 0.187,
        "reserve_breach_count": 0,
        "current_apy": 0.0485
    }
