"""V1 Simulation API router providing the hourly simulation step endpoint."""

from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.persistence.models import SimulationRun
from app.treasury.four_tier_adapter import step_simulation_hour

router = APIRouter(prefix="/api/v1/simulation", tags=["Four-Tier Simulation"])


class StepRequest(BaseModel):
    run_id: Optional[UUID] = Field(default=None, description="Simulation run ID to advance")


class StepResponse(BaseModel):
    run_id: str
    step: int
    timestamp: str
    tier0_cash_cents: int
    tier1_value_cents: int
    tier2_market_value_cents: int
    tier3_market_value_cents: int
    total_portfolio_value_cents: int
    liabilities_cents: int
    net_portfolio_value_cents: int
    required_reserve_cents: int
    available_liquidity_cents: int
    action_taken: str
    action_amount_cents: int
    breach_occurred: bool
    overdraft_borrowed_cents: int
    orders_executed: list[dict[str, Any]]


@router.post("/step", response_model=StepResponse)
def advance_simulation_step(
    req: Optional[StepRequest] = None,
    db: Session = Depends(get_db),
):
    """Advances the four-tier simulation by one hourly step."""
    run_id = req.run_id if req and req.run_id else None
    if run_id is None:
        # Find latest simulation run
        latest_run = db.scalar(select(SimulationRun).order_by(SimulationRun.created_at.desc()))
        if latest_run is None:
            raise HTTPException(
                status_code=404,
                detail="No simulation run found. Create a run before stepping.",
            )
        run_id = latest_run.id

    try:
        result = step_simulation_hour(db, run_id)
        db.commit()
        return result
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
