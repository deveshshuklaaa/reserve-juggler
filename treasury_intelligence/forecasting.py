"""Quantitative cash flow forecasting and uncertainty modeling.

Implements:
1. Rolling-mean forecast
2. Seasonal-naive forecast
3. Automatic fallback for insufficient history
4. Separate inflow and outflow predictions
5. Multi-step forecast paths for arbitrary horizons (e.g. 1, 2, 4, 96 intervals)
6. Strictly causal - no future information is ever accessed
"""
import math
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone

from .types import CashFlowBucket, ForecastPoint, ForecastResult


def validate_forecast_inputs(
    history: Sequence[CashFlowBucket],
    *,
    as_of: datetime,
    horizon_minutes: int,
    bucket_minutes: int,
) -> None:
    """Validate input parameters and causality constraints."""
    if not isinstance(as_of, datetime):
        raise ValueError("as_of must be a datetime object")
    if as_of.tzinfo is None or as_of.tzinfo.utcoffset(as_of) != timezone.utc.utcoffset(as_of):
        raise ValueError("timestamps must be timezone-aware UTC")

    if not isinstance(horizon_minutes, int) or isinstance(horizon_minutes, bool) or horizon_minutes <= 0:
        raise ValueError("horizon_minutes must be a positive integer")
    if not isinstance(bucket_minutes, int) or isinstance(bucket_minutes, bool) or bucket_minutes <= 0:
        raise ValueError("bucket_minutes must be a positive integer")

    if horizon_minutes % bucket_minutes != 0:
        raise ValueError("horizon_minutes must be an exact multiple of bucket_minutes")

    # Validate historical bucket ordering, intervals, and causality
    for i, bucket in enumerate(history):
        if bucket.end_at <= bucket.start_at:
            raise ValueError(f"history bucket at index {i} has invalid interval")
        if i > 0 and bucket.start_at < history[i - 1].end_at:
            raise ValueError("historical buckets must be strictly ordered and non-overlapping")

    if history and history[-1].end_at > as_of:
        raise ValueError("history contains observations after as_of (causality breach)")


def rolling_mean_forecast(
    history: Sequence[CashFlowBucket],
    *,
    as_of: datetime,
    horizon_minutes: int,
    bucket_minutes: int,
    window: int = 16,
    model_version: str = "rolling-mean-v1",
) -> ForecastResult:
    """
    Rolling-mean cash flow forecast with empirical uncertainty.
    
    Predicts separate inflows and outflows using the rolling mean over the most recent
    `window` historical buckets. If history has fewer buckets than `window`, uses all
    available buckets. If history is empty, falls back to 0-flow baseline.
    """
    validate_forecast_inputs(
        history, as_of=as_of, horizon_minutes=horizon_minutes, bucket_minutes=bucket_minutes
    )

    num_intervals = horizon_minutes // bucket_minutes
    bucket_delta = timedelta(minutes=bucket_minutes)

    if not history:
        # Fallback for empty history
        points = tuple(
            ForecastPoint(
                start_at=as_of + i * bucket_delta,
                end_at=as_of + (i + 1) * bucket_delta,
                inflow_cents=0,
                outflow_cents=0,
                uncertainty_cents=0,
            )
            for i in range(num_intervals)
        )
        return ForecastResult(generated_at=as_of, model_version=model_version, points=points)

    recent = history[-window:]
    n = len(recent)

    inflows = [b.inflow_cents for b in recent]
    outflows = [b.outflow_cents for b in recent]
    nets = [b.inflow_cents - b.outflow_cents for b in recent]

    mean_inflow = sum(inflows) / n
    mean_outflow = sum(outflows) / n
    pred_inflow = max(0, int(round(mean_inflow)))
    pred_outflow = max(0, int(round(mean_outflow)))

    if n > 1:
        mean_net = sum(nets) / n
        var_net = sum((x - mean_net) ** 2 for x in nets) / (n - 1)
        uncertainty = math.sqrt(var_net)
    elif n == 1:
        # For a single observation, uncertainty is 15% of volume or 0 if zero
        uncertainty = (pred_inflow + pred_outflow) * 0.15
    else:
        uncertainty = 0.0

    uncertainty_cents = max(0, int(round(uncertainty)))

    points = tuple(
        ForecastPoint(
            start_at=as_of + i * bucket_delta,
            end_at=as_of + (i + 1) * bucket_delta,
            inflow_cents=pred_inflow,
            outflow_cents=pred_outflow,
            uncertainty_cents=uncertainty_cents,
        )
        for i in range(num_intervals)
    )

    return ForecastResult(generated_at=as_of, model_version=model_version, points=points)


def seasonal_naive_forecast(
    history: Sequence[CashFlowBucket],
    *,
    as_of: datetime,
    horizon_minutes: int,
    bucket_minutes: int,
    season_intervals: int | None = None,
    model_version: str = "seasonal-naive-v1",
) -> ForecastResult:
    """
    Seasonal-naive cash flow forecast.
    
    Each future step matches the observation from exactly one seasonal cycle ago
    (default: 1 day = 1440 // bucket_minutes intervals, e.g. 96 intervals for 15-min buckets).
    
    Automatic Fallback:
    If history has fewer than `season_intervals` buckets, automatically falls back
    to rolling-mean forecast while maintaining the requested model_version.
    """
    validate_forecast_inputs(
        history, as_of=as_of, horizon_minutes=horizon_minutes, bucket_minutes=bucket_minutes
    )

    if season_intervals is None:
        season_intervals = 1440 // bucket_minutes

    if season_intervals <= 0:
        raise ValueError("season_intervals must be a positive integer")

    # Automatic fallback for insufficient history
    if len(history) < season_intervals:
        return rolling_mean_forecast(
            history,
            as_of=as_of,
            horizon_minutes=horizon_minutes,
            bucket_minutes=bucket_minutes,
            window=min(16, len(history)) if history else 16,
            model_version=model_version,
        )

    num_intervals = horizon_minutes // bucket_minutes
    bucket_delta = timedelta(minutes=bucket_minutes)
    n = len(history)

    # Calculate seasonal uncertainty from historical seasonal residuals
    # (difference between bucket t and bucket t - season_intervals)
    seasonal_errors = []
    for j in range(season_intervals, n):
        net_curr = history[j].inflow_cents - history[j].outflow_cents
        net_season_prev = history[j - season_intervals].inflow_cents - history[j - season_intervals].outflow_cents
        seasonal_errors.append(net_curr - net_season_prev)

    if len(seasonal_errors) > 1:
        mean_err = sum(seasonal_errors) / len(seasonal_errors)
        var_err = sum((e - mean_err) ** 2 for e in seasonal_errors) / (len(seasonal_errors) - 1)
        uncertainty = math.sqrt(var_err)
    elif len(seasonal_errors) == 1:
        uncertainty = abs(seasonal_errors[0])
    else:
        # Exactly one season available: use recent net variance as proxy
        recent_nets = [b.inflow_cents - b.outflow_cents for b in history[-season_intervals:]]
        mean_n = sum(recent_nets) / len(recent_nets)
        var_n = sum((x - mean_n) ** 2 for x in recent_nets) / (len(recent_nets) - 1)
        uncertainty = math.sqrt(var_n)

    uncertainty_cents = max(0, int(round(uncertainty)))

    points_list = []
    for i in range(num_intervals):
        # Look back season_intervals from current position
        hist_idx = n - season_intervals + (i % season_intervals)
        hist_bucket = history[hist_idx]

        start_at = as_of + i * bucket_delta
        end_at = as_of + (i + 1) * bucket_delta

        points_list.append(
            ForecastPoint(
                start_at=start_at,
                end_at=end_at,
                inflow_cents=max(0, hist_bucket.inflow_cents),
                outflow_cents=max(0, hist_bucket.outflow_cents),
                uncertainty_cents=uncertainty_cents,
            )
        )

    return ForecastResult(generated_at=as_of, model_version=model_version, points=tuple(points_list))
