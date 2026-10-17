"""Public engine API; reserve mathematics implemented, other algorithms deferred."""
from collections.abc import Sequence
from datetime import datetime

from .reserve import calculate_required_reserve

from .types import (
    CashFlowBucket, ForecastResult, TreasuryContext, TreasuryPolicy,
    DecisionResult, EvaluationResult, RiskScenarioResult,
    OptimizationResult,
)


from .forecasting import rolling_mean_forecast, seasonal_naive_forecast

def forecast_cashflows(history: Sequence[CashFlowBucket], *, as_of: datetime,
                       horizon_minutes: int, bucket_minutes: int,
                       model_version: str = "baseline-v1") -> ForecastResult:
    if model_version in ("rolling-mean", "rolling-mean-v1"):
        return rolling_mean_forecast(
            history, as_of=as_of, horizon_minutes=horizon_minutes,
            bucket_minutes=bucket_minutes, model_version=model_version
        )
    elif model_version in ("seasonal-naive", "seasonal-naive-v1", "baseline-v1"):
        return seasonal_naive_forecast(
            history, as_of=as_of, horizon_minutes=horizon_minutes,
            bucket_minutes=bucket_minutes, model_version=model_version
        )
    raise ValueError(f"unsupported model_version: {model_version}")


def recommend_treasury_action(context: TreasuryContext, forecast: ForecastResult,
                              policy: TreasuryPolicy) -> DecisionResult:
    raise NotImplementedError("RJ-M1-01 defines contracts only")


def evaluate_forecasting_models(history: Sequence[CashFlowBucket], *,
                                model_versions: Sequence[str], horizon_minutes: int,
                                bucket_minutes: int) -> tuple[EvaluationResult, ...]:
    raise NotImplementedError("RJ-M1-01 defines contracts only")


def generate_risk_scenarios(context: TreasuryContext, forecast: ForecastResult,
                            policy: TreasuryPolicy, *, seed: int,
                            scenario_count: int) -> tuple[RiskScenarioResult, ...]:
    raise NotImplementedError("RJ-M1-01 defines contracts only")


def evaluate_allocation_candidates(context: TreasuryContext, forecast: ForecastResult,
                                   policy: TreasuryPolicy, *,
                                   candidate_allocations_bps: Sequence[int]) -> tuple[OptimizationResult, ...]:
    raise NotImplementedError("RJ-M1-01 defines contracts only")
