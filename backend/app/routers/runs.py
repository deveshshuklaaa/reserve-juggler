"""Versioned simulation run routes implementing four-tier portfolio intelligence."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.backtesting.reports import BacktestReport, RunReport

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
    except ValueError as exc:
        db.rollback()
        raise HTTPException(422, detail={"error_code": "INVALID_RUN", "message": str(exc), "details": {}}) from exc
    except Exception:
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


@router.post("/{id}/backtest", response_model=BacktestReport)
def backtest(id: UUID, request: BacktestRequest, db: Session = Depends(get_db)):
    from app.persistence.models import SimulationRun
    run = db.get(SimulationRun, id)
    if run is None:
        raise HTTPException(status_code=404, detail={
            "error_code": "NOT_FOUND",
            "message": f"Simulation run {id} not found.",
            "details": {},
        })
    if run.source_type != "ORGANIZER_HISTORICAL":
        raise HTTPException(status_code=422, detail={
            "error_code": "UNPROCESSABLE_ENTITY",
            "message": "Backtesting requires the authoritative organizer historical source",
            "details": {},
        })
    if run.seed is None:
        raise HTTPException(status_code=422, detail={
            "error_code": "UNPROCESSABLE_ENTITY",
            "message": "Run has no reproducible seed",
            "details": {},
        })

    req_days = getattr(request, "days", None)
    if req_days in (7, 14, 30):
        days = req_days
    elif run.duration_steps in (168, 336, 720):
        days = run.duration_steps // 24
    else:
        days = 7

    import json
    from app.backtesting.contracts import BacktestRequest as InternalBacktestRequest, ScenarioSpec, canonical_config
    from app.backtesting.reports import BacktestReportService
    from app.backtesting.runtime import SharedRuntimeFactory
    from app.backtesting.service import BacktestService

    def _sanitize_json_for_config(obj):
        if isinstance(obj, float):
            return str(obj)
        if isinstance(obj, dict):
            return {k: _sanitize_json_for_config(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_sanitize_json_for_config(v) for v in obj]
        return obj

    policy_str = canonical_config(json.dumps(_sanitize_json_for_config(run.policy_json or {})))
    scen_params = (run.policy_json or {}).get("scenario_parameters", {})
    initial_events = [event for event in (run.policy_json or {}).get("scenarios", [])
                      if event.get("effective_step") == 1]
    if len(initial_events) == 1 and initial_events[0].get("scenario") == run.scenario:
        scen_params = initial_events[0].get("parameters", {})
    scen_spec = ScenarioSpec(name=run.scenario, parameters_json=canonical_config(json.dumps(_sanitize_json_for_config(scen_params))))

    bt_req = InternalBacktestRequest(
        comparison_id=run.id,
        start=run.source_start_timestamp,
        days=days,
        initial_capital_cents=run.initial_cash_cents,
        seed=run.seed,
        scenario=scen_spec,
        policy_json=policy_str,
        strategies=tuple({"STATIC_RESERVE": "STATIC", "REACTIVE_RESERVE": "REACTIVE",
                          "RESERVE_JUGGLER": "RESERVE_JUGGLER"}[name] for name in request.strategies),
    )
    try:
        from app.services.dataset_import import StoredDatasetSource
        report_svc = BacktestReportService(BacktestService(
            SharedRuntimeFactory(session=db), source=StoredDatasetSource(db, run.dataset_id),
            allow_uploaded_source=True))
        # Ephemeral evaluation: reuse deterministic comparison/run identities
        # safely on repeated requests, and never mutate the parent's live ledger.
        # The validated response is materialized before rolling back child runs.
        with db.begin_nested() as evaluation:
            result = report_svc.compare(bt_req)
            if not request.retain_runs:
                evaluation.rollback()
        child_run_ids = {}
        if request.retain_runs:
            from uuid import uuid5
            child_run_ids = {row.strategy: str(uuid5(run.id, {"STATIC_RESERVE": "STATIC", "REACTIVE_RESERVE": "REACTIVE", "RESERVE_JUGGLER": "RESERVE_JUGGLER"}[row.strategy])) for row in result.results}
            db.commit()
        selected = {row.strategy: row for row in result.results}
        return BacktestReport(**(result.model_dump() | {
            "results": tuple(selected[name] for name in request.strategies),
            "child_run_ids": child_run_ids}))
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail={
            "error_code": "UNPROCESSABLE_ENTITY",
            "message": str(exc),
            "details": {},
        })


@router.get("/{id}/report", response_model=RunReport)
def report(id: UUID, db: Session = Depends(get_db)):
    from app.persistence.models import SimulationRun
    from app.backtesting.reports import BacktestReportService
    from app.backtesting.runtime import RuntimeReceiptUnavailable

    run = db.get(SimulationRun, id)
    if run is None:
        raise HTTPException(status_code=404, detail={
            "error_code": "NOT_FOUND",
            "message": f"Simulation run {id} not found.",
            "details": {},
        })
    try:
        return BacktestReportService.report_run(db, id)
    except KeyError:
        raise HTTPException(status_code=404, detail={
            "error_code": "NOT_FOUND",
            "message": f"Simulation run {id} not found.",
            "details": {},
        })
    except RuntimeReceiptUnavailable as exc:
        raise HTTPException(status_code=422, detail={
            "error_code": "UNPROCESSABLE_ENTITY",
            "message": str(exc),
            "details": {},
        })

