"""Versioned simulation run routes implementing four-tier portfolio intelligence."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.hourly_engine import StepConflictError
from app.services.run_service import (
    advance_simulation_run,
    apply_simulation_scenario,
    create_simulation_run,
    get_simulation_decisions,
    get_simulation_forecast,
    get_simulation_history,
    get_simulation_snapshot,
    get_simulation_transactions,
    update_simulation_policy,
)
from app.v1_contracts import (
    AdvanceRequest,
    BacktestRequest,
    BacktestResult,
    CreateRunRequest,
    DecisionsResponse,
    ErrorResponse,
    ForecastResponse,
    HistoryResponse,
    PerformanceReport,
    PolicyPatch,
    RunCreated,
    ScenarioApplied,
    ScenarioRequest,
    SimulationSnapshot,
    TransactionsResponse,
    TreasuryPolicy,
)


router = APIRouter(prefix="/runs", tags=["Simulation runs"], responses={
    code: {"model": ErrorResponse, "description": description}
    for code, description in {
        400: "Invalid parameters",
        404: "Run not found",
        409: "Conflicting step or simulation state",
        422: "Schema validation failure",
        500: "Internal error",
        501: "Contract defined; service not implemented",
    }.items()
})


@router.post("", response_model=RunCreated, status_code=201)
def create_run(request: CreateRunRequest, db: Session = Depends(get_db)):
    try:
        run_created = create_simulation_run(db, request)
        db.commit()
        return run_created
    except Exception as exc:
        db.rollback()
        raise


@router.get("/{id}/snapshot", response_model=SimulationSnapshot)
def snapshot(id: UUID, db: Session = Depends(get_db)):
    try:
        return get_simulation_snapshot(db, id)
    except (KeyError, ValueError):
        raise HTTPException(status_code=404, detail={
            "error_code": "NOT_FOUND",
            "message": f"Simulation run {id} not found.",
            "details": {},
        })


@router.post("/{id}/advance", response_model=SimulationSnapshot)
def advance(id: UUID, request: AdvanceRequest, db: Session = Depends(get_db)):
    try:
        snap = advance_simulation_run(db, id, request)
        db.commit()
        return snap
    except (KeyError, ValueError):
        db.rollback()
        raise HTTPException(status_code=404, detail={
            "error_code": "NOT_FOUND",
            "message": f"Simulation run {id} not found.",
            "details": {},
        })
    except StepConflictError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail={
            "error_code": "CONFLICTING_STEP",
            "message": f"Expected step {exc.expected_step} conflicts with current step {exc.current_step}.",
            "details": {"expected_step": exc.expected_step, "current_step": exc.current_step},
        })
    except Exception:
        db.rollback()
        raise


@router.post("/{id}/scenario", response_model=ScenarioApplied)
def scenario(id: UUID, request: ScenarioRequest, db: Session = Depends(get_db)):
    try:
        applied = apply_simulation_scenario(db, id, request)
        db.commit()
        return applied
    except (KeyError, ValueError):
        db.rollback()
        raise HTTPException(status_code=404, detail={
            "error_code": "NOT_FOUND",
            "message": f"Simulation run {id} not found.",
            "details": {},
        })
    except Exception:
        db.rollback()
        raise


@router.patch("/{id}/policy", response_model=TreasuryPolicy)
def policy(id: UUID, request: PolicyPatch, db: Session = Depends(get_db)):
    try:
        updated = update_simulation_policy(db, id, request)
        db.commit()
        return updated
    except (KeyError, ValueError):
        db.rollback()
        raise HTTPException(status_code=404, detail={
            "error_code": "NOT_FOUND",
            "message": f"Simulation run {id} not found.",
            "details": {},
        })
    except Exception:
        db.rollback()
        raise


@router.get("/{id}/history", response_model=HistoryResponse)
def history(id: UUID, limit: int = Query(100, ge=1, le=1000), db: Session = Depends(get_db)):
    try:
        return get_simulation_history(db, id, limit=limit)
    except (KeyError, ValueError):
        raise HTTPException(status_code=404, detail={
            "error_code": "NOT_FOUND",
            "message": f"Simulation run {id} not found.",
            "details": {},
        })


@router.get("/{id}/forecast", response_model=ForecastResponse)
def forecast(id: UUID, horizon_minutes: int = Query(240, ge=15, le=1440), db: Session = Depends(get_db)):
    try:
        return get_simulation_forecast(db, id, horizon_minutes=horizon_minutes)
    except (KeyError, ValueError):
        raise HTTPException(status_code=404, detail={
            "error_code": "NOT_FOUND",
            "message": f"Simulation run {id} not found.",
            "details": {},
        })


@router.get("/{id}/decisions", response_model=DecisionsResponse)
def decisions(id: UUID, limit: int = Query(100, ge=1, le=1000), db: Session = Depends(get_db)):
    try:
        return get_simulation_decisions(db, id, limit=limit)
    except (KeyError, ValueError):
        raise HTTPException(status_code=404, detail={
            "error_code": "NOT_FOUND",
            "message": f"Simulation run {id} not found.",
            "details": {},
        })


@router.get("/{id}/transactions", response_model=TransactionsResponse)
def transactions(id: UUID, limit: int = Query(50, ge=1, le=200), db: Session = Depends(get_db)):
    try:
        return get_simulation_transactions(db, id, limit=limit)
    except (KeyError, ValueError):
        raise HTTPException(status_code=404, detail={
            "error_code": "NOT_FOUND",
            "message": f"Simulation run {id} not found.",
            "details": {},
        })


@router.post("/{id}/backtest", response_model=BacktestResult)
def backtest(id: UUID, request: BacktestRequest):
    raise HTTPException(status_code=501, detail={
        "error_code": "NOT_IMPLEMENTED",
        "message": "Strategy backtesting engine integration is owned by Agent 2.",
        "details": {},
    })


@router.get("/{id}/report", response_model=PerformanceReport)
def report(id: UUID):
    raise HTTPException(status_code=501, detail={
        "error_code": "NOT_IMPLEMENTED",
        "message": "Backtest performance reporting is owned by Agent 2.",
        "details": {},
    })
