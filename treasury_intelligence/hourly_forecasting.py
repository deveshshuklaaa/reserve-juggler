"""Official native hourly cash flow forecasting and causal feature engineering.

Implements TASK RJ-M1-07:
1. Explicit time resolution in forecasting configuration (hourly vs 15-min).
2. Native support for organizer hourly cash-flow buckets and observations.
3. Preserves separate synthetic 15-minute forecasting without alteration.
4. Causal hourly time features:
   - Hour of day (0-23)
   - Day of week (0-6)
   - Weekend indicator (0 or 1)
   - Lagged deposits (lag 1, lag 2, lag 3, lag 24, lag 168)
   - Lagged withdrawals (lag 1, lag 2, lag 3, lag 24, lag 168)
   - Rolling averages and volatility (means and standard deviations)
   - Same hour on previous day (lag 24)
   - Same hour in previous week when available (lag 168)
5. Rolling-mean and seasonal-naive baselines with empirical uncertainty.
6. Separate predictions for deposits and withdrawals.
7. Support for 1-hour, 3-hour, 6-hour, 15-hour, and 24-hour forecast horizons.
8. Complete hourly path output with individual ForecastPoint models.
9. Explicit model resolution and forecast horizon labeling.
10. Safe short-history fallback:
    - Empty history -> 0-flow path.
    - History < seasonal cycle -> rolling-mean fallback over available history.
    - All predictions nonnegative.
"""
from __future__ import annotations

import csv
import io
import math
from collections.abc import Sequence
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from pathlib import Path
from typing import Annotated, Any, Literal, TextIO

from pydantic import Field, field_validator

from .four_tier import (
    ExactDecimal,
    ForecastRiskMetadata,
    FourTierContract,
    HourlyForecastPoint,
    LocalTimestamp,
    Name,
    NonnegativeDecimal,
    OrganizerHourlyObservation,
    PositiveDecimal,
    PositiveInt,
)
from .types import Cents, StrictInt

SUPPORTED_HOURLY_HORIZONS: tuple[int, ...] = (1, 3, 6, 15, 24)


class ForecastResolution(str, Enum):
    """Explicit temporal resolution for treasury cash-flow forecasting."""
    HOURLY = "1h"
    QUARTER_HOURLY = "15m"


class HourlyCashFlowBucket(FourTierContract):
    """Native hourly cash-flow bucket with decimal USD amounts and integer cents."""
    timestamp: LocalTimestamp
    deposits_usd: NonnegativeDecimal
    withdrawals_usd: NonnegativeDecimal
    net_flow_usd: ExactDecimal

    @field_validator("timestamp")
    @classmethod
    def hourly(cls, value: datetime) -> datetime:
        if value.minute or value.second or value.microsecond:
            raise ValueError("hourly cash-flow buckets must be on native hourly boundaries")
        return value

    @property
    def deposits_cents(self) -> int:
        return int((self.deposits_usd * 100).to_integral_value(rounding=ROUND_HALF_UP))

    @property
    def withdrawals_cents(self) -> int:
        return int((self.withdrawals_usd * 100).to_integral_value(rounding=ROUND_HALF_UP))

    @property
    def net_flow_cents(self) -> int:
        return self.deposits_cents - self.withdrawals_cents

    @classmethod
    def from_observation(cls, obs: OrganizerHourlyObservation) -> HourlyCashFlowBucket:
        return cls(
            timestamp=obs.timestamp,
            deposits_usd=obs.deposits_usd,
            withdrawals_usd=obs.withdrawals_usd,
            net_flow_usd=obs.net_flow_usd,
        )


class HourlyForecastConfig(FourTierContract):
    """Configuration for native hourly cash-flow forecasting."""
    resolution: Literal["1h"] = "1h"
    horizon_hours: Literal[1, 3, 6, 15, 24] | PositiveInt = 24
    model_version: Name = "hourly-seasonal-naive-v1"
    rolling_window_hours: PositiveInt = 24
    season_hours: PositiveInt = 24
    uncertainty_multiplier: PositiveDecimal | NonnegativeDecimal = Decimal("1.0")
    uncertainty_status: Literal["not_evaluated", "provisional_uncalibrated", "evaluated"] = "provisional_uncalibrated"
    ml_model: Any = None


class HourlyForecastResult(FourTierContract):
    """Complete pathwise hourly forecast result with provenance and metadata."""
    generated_at: LocalTimestamp
    model_version: Name
    resolution: Literal["1h"] = "1h"
    horizon_hours: PositiveInt
    points: tuple[HourlyForecastPoint, ...]
    metadata: ForecastRiskMetadata

    @property
    def total_predicted_deposits_cents(self) -> int:
        return sum(p.predicted_deposits_cents for p in self.points)

    @property
    def total_predicted_withdrawals_cents(self) -> int:
        return sum(p.predicted_withdrawals_cents for p in self.points)

    @property
    def total_predicted_net_flow_cents(self) -> int:
        return sum(p.predicted_net_flow_cents for p in self.points)

    @property
    def total_uncertainty_buffer_cents(self) -> int:
        return sum(p.supplied_uncertainty_buffer_cents for p in self.points)

    @property
    def path_deposits_cents(self) -> tuple[int, ...]:
        return tuple(p.predicted_deposits_cents for p in self.points)

    @property
    def path_withdrawals_cents(self) -> tuple[int, ...]:
        return tuple(p.predicted_withdrawals_cents for p in self.points)

    @property
    def path_net_flow_cents(self) -> tuple[int, ...]:
        return tuple(p.predicted_net_flow_cents for p in self.points)


# ---------------------------------------------------------------------------
# Causal Hourly Feature Engineering
# ---------------------------------------------------------------------------

def extract_hourly_calendar_features(dt: datetime) -> dict[str, Any]:
    """Extract causal calendar, time-of-day, and day-of-week features from hourly timestamps.
    
    Operates on native timezone-unspecified datetime objects on hourly boundaries.
    """
    if dt.tzinfo is not None:
        raise ValueError("source timestamps have unspecified timezone; timezone-aware datetimes are forbidden")
    if dt.minute or dt.second or dt.microsecond:
        raise ValueError("hourly timestamps must be on exact hourly boundaries")

    hour_of_day = dt.hour
    day_of_week = dt.weekday()  # 0 = Monday, 6 = Sunday
    is_weekend = 1 if day_of_week >= 5 else 0

    sin_hour_of_day = math.sin(2.0 * math.pi * hour_of_day / 24.0)
    cos_hour_of_day = math.cos(2.0 * math.pi * hour_of_day / 24.0)
    sin_day_of_week = math.sin(2.0 * math.pi * day_of_week / 7.0)
    cos_day_of_week = math.cos(2.0 * math.pi * day_of_week / 7.0)

    return {
        "timestamp": dt,
        "hour_of_day": hour_of_day,
        "day_of_week": day_of_week,
        "is_weekend": is_weekend,
        "sin_hour_of_day": round(sin_hour_of_day, 6),
        "cos_hour_of_day": round(cos_hour_of_day, 6),
        "sin_day_of_week": round(sin_day_of_week, 6),
        "cos_day_of_week": round(cos_day_of_week, 6),
    }


def _extract_amounts(obs: Any) -> tuple[float, float, float, int, int, int]:
    """Extract (dep_usd, wtd_usd, net_usd, dep_cents, wtd_cents, net_cents) from observation."""
    if hasattr(obs, "deposits_usd") and hasattr(obs, "withdrawals_usd"):
        d_usd = float(obs.deposits_usd)
        w_usd = float(obs.withdrawals_usd)
        n_usd = float(obs.net_flow_usd) if hasattr(obs, "net_flow_usd") else (d_usd - w_usd)
        d_cents = int((Decimal(str(obs.deposits_usd)) * 100).to_integral_value(rounding=ROUND_HALF_UP))
        w_cents = int((Decimal(str(obs.withdrawals_usd)) * 100).to_integral_value(rounding=ROUND_HALF_UP))
        n_cents = d_cents - w_cents
    elif hasattr(obs, "deposits_cents") and hasattr(obs, "withdrawals_cents"):
        d_cents = int(obs.deposits_cents)
        w_cents = int(obs.withdrawals_cents)
        n_cents = d_cents - w_cents
        d_usd = d_cents / 100.0
        w_usd = w_cents / 100.0
        n_usd = n_cents / 100.0
    elif hasattr(obs, "inflow_cents") and hasattr(obs, "outflow_cents"):
        d_cents = int(obs.inflow_cents)
        w_cents = int(obs.outflow_cents)
        n_cents = d_cents - w_cents
        d_usd = d_cents / 100.0
        w_usd = w_cents / 100.0
        n_usd = n_cents / 100.0
    else:
        raise TypeError(f"unsupported observation type: {type(obs)}")
    return d_usd, w_usd, n_usd, d_cents, w_cents, n_cents


def compute_hourly_lag_features(
    observations: Sequence[Any],
    lags: Sequence[int] = (1, 2, 3, 24, 168),
    fill_value: Any = None,
) -> list[dict[str, Any]]:
    """Compute causal historical lag features for an hourly observation sequence.
    
    Includes standard lags (1, 2, 3) as well as same hour on previous day (lag 24)
    and same hour in previous week (lag 168).
    Strictly causal: observation at index i only accesses indices i - k where k >= 1.
    """
    results: list[dict[str, Any]] = []
    extracted = [_extract_amounts(o) for o in observations]

    for i in range(len(observations)):
        row: dict[str, Any] = {}
        for lag in lags:
            prev_idx = i - lag
            if prev_idx >= 0:
                d_usd, w_usd, n_usd, d_cents, w_cents, n_cents = extracted[prev_idx]
                row[f"lag_{lag}_deposits_usd"] = d_usd
                row[f"lag_{lag}_withdrawals_usd"] = w_usd
                row[f"lag_{lag}_net_flow_usd"] = n_usd
                row[f"lag_{lag}_deposits_cents"] = d_cents
                row[f"lag_{lag}_withdrawals_cents"] = w_cents
                row[f"lag_{lag}_net_flow_cents"] = n_cents
            else:
                row[f"lag_{lag}_deposits_usd"] = fill_value
                row[f"lag_{lag}_withdrawals_usd"] = fill_value
                row[f"lag_{lag}_net_flow_usd"] = fill_value
                row[f"lag_{lag}_deposits_cents"] = fill_value
                row[f"lag_{lag}_withdrawals_cents"] = fill_value
                row[f"lag_{lag}_net_flow_cents"] = fill_value

        # Named canonical convenience aliases
        row["same_hour_prev_day_deposits_usd"] = row.get("lag_24_deposits_usd", fill_value)
        row["same_hour_prev_day_withdrawals_usd"] = row.get("lag_24_withdrawals_usd", fill_value)
        row["same_hour_prev_day_net_flow_usd"] = row.get("lag_24_net_flow_usd", fill_value)
        row["same_hour_prev_day_deposits_cents"] = row.get("lag_24_deposits_cents", fill_value)
        row["same_hour_prev_day_withdrawals_cents"] = row.get("lag_24_withdrawals_cents", fill_value)
        row["same_hour_prev_day_net_flow_cents"] = row.get("lag_24_net_flow_cents", fill_value)

        row["same_hour_prev_week_deposits_usd"] = row.get("lag_168_deposits_usd", fill_value)
        row["same_hour_prev_week_withdrawals_usd"] = row.get("lag_168_withdrawals_usd", fill_value)
        row["same_hour_prev_week_net_flow_usd"] = row.get("lag_168_net_flow_usd", fill_value)
        row["same_hour_prev_week_deposits_cents"] = row.get("lag_168_deposits_cents", fill_value)
        row["same_hour_prev_week_withdrawals_cents"] = row.get("lag_168_withdrawals_cents", fill_value)
        row["same_hour_prev_week_net_flow_cents"] = row.get("lag_168_net_flow_cents", fill_value)

        results.append(row)
    return results


def compute_hourly_rolling_features(
    observations: Sequence[Any],
    windows: Sequence[int] = (3, 6, 24, 168),
    strictly_prior: bool = True,
) -> list[dict[str, Any]]:
    """Compute causal rolling averages and volatility (sample standard deviation) for hourly data.
    
    If strictly_prior is True (default for forecasting features), index i only uses observations
    prior to i (indices max(0, i - w) to i - 1).
    """
    results: list[dict[str, Any]] = []
    extracted = [_extract_amounts(o) for o in observations]

    for i in range(len(observations)):
        row: dict[str, Any] = {}
        for w in windows:
            if strictly_prior:
                start_idx = max(0, i - w)
                end_idx = i
            else:
                start_idx = max(0, i - w + 1)
                end_idx = i + 1

            if end_idx <= start_idx:
                for target in ("deposits_usd", "withdrawals_usd", "net_flow_usd",
                               "deposits_cents", "withdrawals_cents", "net_flow_cents"):
                    row[f"rolling_mean_{w}_{target}"] = None
                    row[f"rolling_std_{w}_{target}"] = None
                    row[f"rolling_volatility_{w}_{target}"] = None
                continue

            slice_items = extracted[start_idx:end_idx]
            m = len(slice_items)

            d_usds = [x[0] for x in slice_items]
            w_usds = [x[1] for x in slice_items]
            n_usds = [x[2] for x in slice_items]
            d_cents = [x[3] for x in slice_items]
            w_cents = [x[4] for x in slice_items]
            n_cents = [x[5] for x in slice_items]

            def _stats(arr: list[float | int]) -> tuple[float, float]:
                mean_val = sum(arr) / len(arr)
                if len(arr) > 1:
                    var = sum((x - mean_val) ** 2 for x in arr) / (len(arr) - 1)
                    std_val = math.sqrt(var)
                else:
                    std_val = 0.0
                return round(mean_val, 2), round(std_val, 2)

            for target_name, arr in [
                ("deposits_usd", d_usds),
                ("withdrawals_usd", w_usds),
                ("net_flow_usd", n_usds),
                ("deposits_cents", d_cents),
                ("withdrawals_cents", w_cents),
                ("net_flow_cents", n_cents),
            ]:
                mean_v, std_v = _stats(arr)
                row[f"rolling_mean_{w}_{target_name}"] = mean_v
                row[f"rolling_std_{w}_{target_name}"] = std_v
                row[f"rolling_volatility_{w}_{target_name}"] = std_v

        results.append(row)
    return results


def build_hourly_feature_matrix(
    observations: Sequence[Any],
    lags: Sequence[int] = (1, 2, 3, 24, 168),
    windows: Sequence[int] = (3, 6, 24, 168),
    strictly_prior: bool = True,
) -> list[dict[str, Any]]:
    """Construct full causal feature matrix for native hourly observations."""
    lag_feats = compute_hourly_lag_features(observations, lags=lags)
    rolling_feats = compute_hourly_rolling_features(observations, windows=windows, strictly_prior=strictly_prior)

    matrix: list[dict[str, Any]] = []
    for i, obs in enumerate(observations):
        ts = obs.timestamp if hasattr(obs, "timestamp") else getattr(obs, "start_at")
        cal = extract_hourly_calendar_features(ts)
        d_usd, w_usd, n_usd, d_cents, w_cents, n_cents = _extract_amounts(obs)
        row = {
            "timestamp": ts,
            "deposits_usd": d_usd,
            "withdrawals_usd": w_usd,
            "net_flow_usd": n_usd,
            "deposits_cents": d_cents,
            "withdrawals_cents": w_cents,
            "net_flow_cents": n_cents,
            **cal,
            **lag_feats[i],
            **rolling_feats[i],
        }
        matrix.append(row)
    return matrix


# ---------------------------------------------------------------------------
# Hourly Forecasting Baselines
# ---------------------------------------------------------------------------

def validate_hourly_forecast_inputs(
    history: Sequence[Any],
    *,
    as_of: datetime,
    horizon_hours: int,
) -> None:
    """Validate causality, hourly granularity, and ordering for hourly forecasting."""
    if not isinstance(as_of, datetime):
        raise ValueError("as_of must be a datetime object")
    if as_of.tzinfo is not None:
        raise ValueError("source timestamps have unspecified timezone; timezone-aware datetimes are forbidden")
    if as_of.minute or as_of.second or as_of.microsecond:
        raise ValueError("as_of must be on an exact hourly boundary")

    if not isinstance(horizon_hours, int) or isinstance(horizon_hours, bool) or horizon_hours <= 0:
        raise ValueError("horizon_hours must be a positive integer")

    # Validate historical timestamps
    for i, obs in enumerate(history):
        ts = getattr(obs, "timestamp", getattr(obs, "start_at", None))
        if ts is None or not isinstance(ts, datetime):
            raise ValueError(f"history observation at index {i} has invalid timestamp")
        if ts.tzinfo is not None:
            raise ValueError(f"history observation at index {i} has forbidden timezone offset")
        if ts.minute or ts.second or ts.microsecond:
            raise ValueError(f"history observation at index {i} is not on native hourly boundary")
        if i > 0:
            prev_ts = getattr(history[i - 1], "timestamp", getattr(history[i - 1], "start_at", None))
            if ts <= prev_ts:
                raise ValueError("history observations must be strictly chronologically ordered")
            if ts - prev_ts != timedelta(hours=1):
                raise ValueError("hourly history must be contiguous; missing hours cannot be treated as hourly lags")

    if history:
        last_ts = getattr(history[-1], "timestamp", getattr(history[-1], "start_at", None))
        if last_ts > as_of:
            raise ValueError("history contains observations after as_of (causality breach)")


def hourly_rolling_mean_forecast(
    history: Sequence[Any],
    *,
    as_of: datetime,
    horizon_hours: int = 24,
    window_hours: int = 24,
    start_at: datetime | None = None,
    model_version: str = "hourly-rolling-mean-v1",
    uncertainty_multiplier: Decimal | float = Decimal("1.0"),
) -> HourlyForecastResult:
    """Rolling-mean cash flow forecast for native hourly resolution.
    
    Predicts separate nonnegative deposits and withdrawals over horizon_hours.
    Uncertainty is empirical sample standard deviation of historical net flows.
    Safe fallback:
    - If history is empty: produces zero predictions and zero uncertainty.
    - If history < window_hours: averages all available observations.
    """
    validate_hourly_forecast_inputs(history, as_of=as_of, horizon_hours=horizon_hours)

    if start_at is None:
        if history and getattr(history[-1], "timestamp", getattr(history[-1], "start_at", None)) == as_of:
            start_at = as_of + timedelta(hours=1)
        else:
            start_at = as_of
    else:
        if start_at.tzinfo is not None or start_at.minute or start_at.second or start_at.microsecond:
            raise ValueError("start_at must be a naive datetime on hourly boundary")
        if start_at < as_of:
            raise ValueError("forecast cannot start before decision time as_of")

    hour_delta = timedelta(hours=1)

    if not history:
        # Safe short-history fallback: 0-flow path
        points = tuple(
            HourlyForecastPoint(
                start_at=start_at + i * hour_delta,
                predicted_deposits_cents=0,
                predicted_withdrawals_cents=0,
                predicted_net_flow_cents=0,
                supplied_uncertainty_buffer_cents=0,
            )
            for i in range(horizon_hours)
        )
        metadata = ForecastRiskMetadata(
            model_version=model_version,
            generated_at=as_of,
            training_data_through=as_of,
            granularity_hours=1,
            net_flow_target="deposits_minus_withdrawals",
            uncertainty_status="provisional_uncalibrated",
            evaluation_reference=None,
            notes=(
                f"Resolution: 1h; Horizon: {horizon_hours}h",
                "Empty history fallback: 0-flow forecast",
            ),
        )
        return HourlyForecastResult(
            generated_at=as_of,
            model_version=model_version,
            resolution="1h",
            horizon_hours=horizon_hours,
            points=points,
            metadata=metadata,
        )

    recent = history[-window_hours:]
    n = len(recent)
    extracted = [_extract_amounts(o) for o in recent]

    d_cents = [x[3] for x in extracted]
    w_cents = [x[4] for x in extracted]
    n_cents = [x[5] for x in extracted]

    mean_dep = sum(d_cents) / n
    mean_wtd = sum(w_cents) / n
    pred_dep = max(0, int(round(mean_dep)))
    pred_wtd = max(0, int(round(mean_wtd)))
    pred_net = pred_dep - pred_wtd

    if n > 1:
        mean_net = sum(n_cents) / n
        var_net = sum((x - mean_net) ** 2 for x in n_cents) / (n - 1)
        uncertainty = math.sqrt(var_net)
    elif n == 1:
        uncertainty = (pred_dep + pred_wtd) * 0.15
    else:
        uncertainty = 0.0

    mult = float(uncertainty_multiplier)
    uncertainty_cents = max(0, int(round(uncertainty * mult)))

    points = tuple(
        HourlyForecastPoint(
            start_at=start_at + i * hour_delta,
            predicted_deposits_cents=pred_dep,
            predicted_withdrawals_cents=pred_wtd,
            predicted_net_flow_cents=pred_net,
            supplied_uncertainty_buffer_cents=uncertainty_cents,
        )
        for i in range(horizon_hours)
    )

    last_ts = getattr(history[-1], "timestamp", getattr(history[-1], "start_at", as_of))
    metadata = ForecastRiskMetadata(
        model_version=model_version,
        generated_at=as_of,
        training_data_through=last_ts,
        granularity_hours=1,
        net_flow_target="deposits_minus_withdrawals",
        uncertainty_status="provisional_uncalibrated",
        evaluation_reference=None,
        notes=(
            f"Resolution: 1h; Horizon: {horizon_hours}h",
            f"Model: {model_version}; Window: {n}h",
        ),
    )

    return HourlyForecastResult(
        generated_at=as_of,
        model_version=model_version,
        resolution="1h",
        horizon_hours=horizon_hours,
        points=points,
        metadata=metadata,
    )


def hourly_seasonal_naive_forecast(
    history: Sequence[Any],
    *,
    as_of: datetime,
    horizon_hours: int = 24,
    season_hours: int = 24,
    start_at: datetime | None = None,
    model_version: str = "hourly-seasonal-naive-v1",
    uncertainty_multiplier: Decimal | float = Decimal("1.0"),
) -> HourlyForecastResult:
    """Seasonal-naive cash flow forecast for native hourly resolution.
    
    Each future step matches the exact observation from 1 seasonal cycle ago (default 24h).
    Safe fallback:
    - If history is empty: falls back to 0-flow path.
    - If history < season_hours: automatically falls back to rolling-mean forecast.
    """
    validate_hourly_forecast_inputs(history, as_of=as_of, horizon_hours=horizon_hours)

    if season_hours <= 0:
        raise ValueError("season_hours must be a positive integer")

    # Safe fallback for insufficient history
    if len(history) < season_hours:
        return hourly_rolling_mean_forecast(
            history,
            as_of=as_of,
            horizon_hours=horizon_hours,
            window_hours=min(season_hours, len(history)) if history else season_hours,
            start_at=start_at,
            model_version=model_version,
            uncertainty_multiplier=uncertainty_multiplier,
        )

    if start_at is None:
        if history and getattr(history[-1], "timestamp", getattr(history[-1], "start_at", None)) == as_of:
            start_at = as_of + timedelta(hours=1)
        else:
            start_at = as_of
    else:
        if start_at.tzinfo is not None or start_at.minute or start_at.second or start_at.microsecond:
            raise ValueError("start_at must be a naive datetime on hourly boundary")
        if start_at < as_of:
            raise ValueError("forecast cannot start before decision time as_of")

    hour_delta = timedelta(hours=1)
    n = len(history)
    extracted = [_extract_amounts(o) for o in history]

    # Calculate seasonal uncertainty from historical seasonal residuals
    # (residual = net_flow[j] - net_flow[j - season_hours])
    seasonal_errors: list[float] = []
    for j in range(season_hours, n):
        net_curr = extracted[j][5]
        net_season_prev = extracted[j - season_hours][5]
        seasonal_errors.append(float(net_curr - net_season_prev))

    if len(seasonal_errors) > 1:
        mean_err = sum(seasonal_errors) / len(seasonal_errors)
        var_err = sum((e - mean_err) ** 2 for e in seasonal_errors) / (len(seasonal_errors) - 1)
        uncertainty = math.sqrt(var_err)
    elif len(seasonal_errors) == 1:
        uncertainty = abs(seasonal_errors[0])
    else:
        recent_nets = [x[5] for x in extracted[-season_hours:]]
        mean_n = sum(recent_nets) / len(recent_nets)
        var_n = sum((x - mean_n) ** 2 for x in recent_nets) / (len(recent_nets) - 1)
        uncertainty = math.sqrt(var_n)

    mult = float(uncertainty_multiplier)
    uncertainty_cents = max(0, int(round(uncertainty * mult)))

    points: list[HourlyForecastPoint] = []
    for i in range(horizon_hours):
        target_time = start_at + i * hour_delta
        # Match the historical observation from season_hours ago for this relative cycle index
        # Align by timestamp, including explicit start_at=as_of and stale
        # histories. Recycle only already observed seasonal values.
        reference_time = target_time - timedelta(hours=season_hours)
        last_time = getattr(history[-1], "timestamp", getattr(history[-1], "start_at", None))
        while reference_time > last_time:
            reference_time -= timedelta(hours=season_hours)
        hist_idx = n - 1 + int((reference_time - last_time) / hour_delta)
        if hist_idx < 0:
            hist_idx = n - 1  # No prior seasonal match; causal last-observation fallback.
        d_usd, w_usd, n_usd, d_cents, w_cents, n_cents = extracted[hist_idx]

        pred_dep = max(0, d_cents)
        pred_wtd = max(0, w_cents)
        pred_net = pred_dep - pred_wtd

        points.append(
            HourlyForecastPoint(
                start_at=target_time,
                predicted_deposits_cents=pred_dep,
                predicted_withdrawals_cents=pred_wtd,
                predicted_net_flow_cents=pred_net,
                supplied_uncertainty_buffer_cents=uncertainty_cents,
            )
        )

    last_ts = getattr(history[-1], "timestamp", getattr(history[-1], "start_at", as_of))
    metadata = ForecastRiskMetadata(
        model_version=model_version,
        generated_at=as_of,
        training_data_through=last_ts,
        granularity_hours=1,
        net_flow_target="deposits_minus_withdrawals",
        uncertainty_status="provisional_uncalibrated",
        evaluation_reference=None,
        notes=(
            f"Resolution: 1h; Horizon: {horizon_hours}h",
            f"Model: {model_version}; Season: {season_hours}h",
        ),
    )

    return HourlyForecastResult(
        generated_at=as_of,
        model_version=model_version,
        resolution="1h",
        horizon_hours=horizon_hours,
        points=tuple(points),
        metadata=metadata,
    )


def forecast_hourly_cashflows(
    history: Sequence[Any],
    *,
    as_of: datetime,
    horizon_hours: int = 24,
    model_version: str = "hourly-seasonal-naive-v1",
    config: HourlyForecastConfig | None = None,
    start_at: datetime | None = None,
    ml_model: Any | None = None,
    publication_delay_seconds: int = 0,
) -> HourlyForecastResult:
    """Unified entry point for native hourly cash-flow forecasting.
    
    Supports horizons: 1, 3, 6, 15, and 24 hours (and any positive integer).
    Respects explicit HourlyForecastConfig if provided.
    Dispatches to ML models, rolling-mean, or seasonal-naive based on model_version.
    """
    if config is not None:
        horizon_hours = config.horizon_hours
        model_version = config.model_version
        mult = config.uncertainty_multiplier
        rolling_window = config.rolling_window_hours
        season_hours = config.season_hours
        if ml_model is None and getattr(config, "ml_model", None) is not None:
            ml_model = config.ml_model
    else:
        mult = Decimal("1.0")
        rolling_window = 24
        season_hours = 24

    if "ml" in model_version or "hist-gb" in model_version or "random-forest" in model_version or ml_model is not None:
        from .ml_forecasting import hourly_ml_forecast
        return hourly_ml_forecast(
            history,
            as_of=as_of,
            horizon_hours=horizon_hours,
            ml_model=ml_model,
            start_at=start_at,
            model_version=model_version,
            publication_delay_seconds=publication_delay_seconds,
        )

    if "rolling" in model_version:
        return hourly_rolling_mean_forecast(
            history,
            as_of=as_of,
            horizon_hours=horizon_hours,
            window_hours=rolling_window,
            start_at=start_at,
            model_version=model_version,
            uncertainty_multiplier=mult,
        )
    return hourly_seasonal_naive_forecast(
        history,
        as_of=as_of,
        horizon_hours=horizon_hours,
        season_hours=season_hours,
        start_at=start_at,
        model_version=model_version,
        uncertainty_multiplier=mult,
    )


# ---------------------------------------------------------------------------
# Local, Read-Only Adapter for Organizer Dataset
# ---------------------------------------------------------------------------

def load_organizer_dataset(
    source: str | Path | TextIO,
    *,
    limit: int | None = None,
) -> tuple[OrganizerHourlyObservation, ...]:
    """Read-only adapter for organizer hourly dataset CSV.
    
    Loads CSV rows without altering numeric scale or converting timezones.
    Each row is validated into an OrganizerHourlyObservation.
    
    Expected CSV structure:
    - 16 comma-separated columns matching OrganizerHourlyObservation field names.
    - Naive ISO timestamps 'YYYY-MM-DD HH:MM:SS' on the hour.
    - deposits_usd, withdrawals_usd, net_flow_usd in decimal USD.
    - Boolean strings 'True' / 'False' for repo window flags.
    - Market quotes, yields, indices, haircut percentages.
    
    Does NOT overwrite or duplicate Member 2's authoritative loader.
    """
    rows: list[OrganizerHourlyObservation] = []

    def _parse_reader(reader: csv.DictReader) -> tuple[OrganizerHourlyObservation, ...]:
        count = 0
        parsed_rows: list[OrganizerHourlyObservation] = []
        for r in reader:
            if limit is not None and count >= limit:
                break
            obs = OrganizerHourlyObservation.model_validate(r)
            parsed_rows.append(obs)
            count += 1
        return tuple(parsed_rows)

    if isinstance(source, (str, Path)):
        p = Path(source)
        if not p.is_file():
            # Check cwd
            candidate = Path.cwd() / source
            if candidate.is_file():
                p = candidate
            else:
                raise FileNotFoundError(f"organizer dataset not found at {source}")
        with open(p, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            return _parse_reader(reader)
    elif hasattr(source, "read"):
        reader = csv.DictReader(source)
        return _parse_reader(reader)
    else:
        raise TypeError(f"unsupported source type for dataset adapter: {type(source)}")
