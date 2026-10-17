"""Frozen Member 2 route interfaces; business services are not implemented yet."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from app.v1_contracts import (
    AdvanceRequest, BacktestRequest, BacktestResult, CreateRunRequest,
    DecisionRecord, ErrorResponse, ForecastSummary, PerformanceReport, PolicyPatch,
    RunCreated, ScenarioApplied, ScenarioRequest, SimulationSnapshot,
    TransactionRecord, TreasuryPolicy,
)


router = APIRouter(prefix="/runs", tags=["Simulation runs"], responses={
    code: {"model": ErrorResponse, "description": description}
    for code, description in {
        400: "Invalid parameters", 404: "Run not found",
        409: "Conflicting step or simulation state", 422: "Schema validation failure",
        500: "Internal error", 501: "Contract defined; service not implemented",
    }.items()
})


def unavailable():
    raise HTTPException(status_code=501, detail={
        "error_code": "NOT_IMPLEMENTED",
        "message": "This API contract is defined; the simulation service is not implemented.",
        "details": {},
    })


@router.post("", response_model=RunCreated, status_code=201)
def create_run(request: CreateRunRequest):
    unavailable()


@router.get("/{id}/snapshot", response_model=SimulationSnapshot)
def snapshot(id: UUID):
    unavailable()


@router.post("/{id}/advance", response_model=SimulationSnapshot)
def advance(id: UUID, request: AdvanceRequest):
    unavailable()


@router.post("/{id}/scenario", response_model=ScenarioApplied)
def scenario(id: UUID, request: ScenarioRequest):
    unavailable()


@router.patch("/{id}/policy", response_model=TreasuryPolicy)
def policy(id: UUID, request: PolicyPatch):
    unavailable()


@router.get("/{id}/history", response_model=list[SimulationSnapshot])
def history(id: UUID, limit: int = Query(100, ge=1, le=1000)):
    unavailable()


@router.get("/{id}/forecast", response_model=ForecastSummary | None)
def forecast(id: UUID):
    unavailable()


@router.get("/{id}/decisions", response_model=list[DecisionRecord])
def decisions(id: UUID, limit: int = Query(100, ge=1, le=1000)):
    unavailable()


@router.get("/{id}/transactions", response_model=list[TransactionRecord])
def transactions(id: UUID, limit: int = Query(50, ge=1, le=200)):
    unavailable()


@router.post("/{id}/backtest", response_model=BacktestResult)
def backtest(id: UUID, request: BacktestRequest):
    unavailable()


@router.get("/{id}/report", response_model=PerformanceReport)
def report(id: UUID):
    unavailable()
