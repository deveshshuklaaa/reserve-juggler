"""Historical comparison orchestration; execution belongs to the shared hourly engine."""

from .contracts import BacktestRequest, ComparisonResult, ScenarioSpec
from .service import BacktestService, EngineContractError, SharedEngineUnavailable

__all__ = ["BacktestRequest", "BacktestService", "ComparisonResult", "ScenarioSpec",
           "EngineContractError", "SharedEngineUnavailable"]
