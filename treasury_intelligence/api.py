"""Public engine API; forecasting, reserves, and recommendations are implemented."""
from collections.abc import Sequence
from datetime import datetime

from .reserve import calculate_required_reserve
from .policy import recommend_treasury_action
from .portfolio import recommend_portfolio_allocation
from .optimizer import recommend_four_tier_allocation
from .liquidity_risk import calculate_four_tier_liquidity_risk

from .types import (
    CashFlowBucket, ForecastResult, TreasuryContext, TreasuryPolicy,
    EvaluationResult, RiskScenarioResult,
    OptimizationResult,
)


from .forecasting import rolling_mean_forecast, seasonal_naive_forecast
from .hourly_forecasting import (
    ForecastResolution,
    HourlyCashFlowBucket,
    HourlyForecastConfig,
    HourlyForecastResult,
    SUPPORTED_HOURLY_HORIZONS,
    forecast_hourly_cashflows,
    hourly_rolling_mean_forecast,
    hourly_seasonal_naive_forecast,
    load_organizer_dataset,
)
from .ml_forecasting import (
    HourlyCashFlowMLModel,
    HourlyModelEvaluationReport,
    evaluate_hourly_forecast_models,
    hourly_ml_forecast,
)
from .monte_carlo_risk import (
    MONTE_CARLO_RISK_MODEL_VERSION,
    MarketRiskSummary,
    MultiAssetMonteCarloRiskResult,
    PercentileSummary,
    PortfolioDownsideRiskSummary,
    ShortfallDistributionSummary,
    generate_multi_asset_scenarios,
    simulate_multi_asset_monte_carlo_risk,
)
from .four_tier_demo import (
    FourTierDemoScenarioResult,
    FourTierDemoSuiteResult,
    build_demo_portfolio_state,
    load_demo_observations,
    resolve_organizer_dataset_path,
    run_four_tier_demo,
    run_scenario_liquidity_shortage,
    run_scenario_market_decline,
    run_scenario_repo_sweep,
    run_scenario_repo_unavailable,
)


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
