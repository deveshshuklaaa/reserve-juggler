from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import SimulationRunModel
from app.schemas import SimulationRun, SimulationStartRequest, ScenarioConfigRequest

router = APIRouter(prefix="/api/simulation", tags=["Simulation"])

@router.post("/start", response_model=SimulationRun, status_code=202)
def start_simulation(req: SimulationStartRequest, db: Session = Depends(get_db)):
    run = SimulationRunModel(
        scenario=req.scenario,
        started_at=datetime.utcnow(),
        total_yield=0.0,
        reserve_breaches=0,
        emergency_events=0
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run

@router.post("/scenario")
def update_scenario(req: ScenarioConfigRequest):
    return {
        "status": "scenario_applied",
        "active_scenario": req.scenario,
        "intensity": req.intensity
    }

@router.get("/{id}/results", response_model=SimulationRun)
def get_simulation_results(id: int, db: Session = Depends(get_db)):
    run = db.query(SimulationRunModel).filter(SimulationRunModel.id == id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Simulation run {id} not found")
    return run
