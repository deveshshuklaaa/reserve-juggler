"""Causal feature engineering for treasury cash flow time-series.

Strictly causal: No future observations or lookahead are ever accessed.
All calendar, lag, and rolling statistics are calculated using only observations
available up to the observation timestamp.
"""
import math
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any

from .types import CashFlowBucket


def extract_calendar_features(dt: datetime, bucket_minutes: int = 15) -> dict[str, float | int]:
    """
    Extract causal calendar, time-of-day, and day-of-week features.
    
    Returns cyclical encodings (sin/cos) and integer indices for time of day and day of week.
    """
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) != timezone.utc.utcoffset(dt):
        raise ValueError("timestamps must be timezone-aware UTC")

    minute_of_day = dt.hour * 60 + dt.minute
    hour_of_day = dt.hour
    interval_of_day = minute_of_day // bucket_minutes
    day_of_week = dt.weekday()  # 0 = Monday, 6 = Sunday
    is_weekend = 1 if day_of_week >= 5 else 0

    # Cyclical representations
    sin_time_of_day = math.sin(2.0 * math.pi * minute_of_day / 1440.0)
    cos_time_of_day = math.cos(2.0 * math.pi * minute_of_day / 1440.0)
    sin_day_of_week = math.sin(2.0 * math.pi * day_of_week / 7.0)
    cos_day_of_week = math.cos(2.0 * math.pi * day_of_week / 7.0)

    return {
        "minute_of_day": minute_of_day,
        "hour_of_day": hour_of_day,
        "interval_of_day": interval_of_day,
        "day_of_week": day_of_week,
        "is_weekend": is_weekend,
        "sin_time_of_day": round(sin_time_of_day, 6),
        "cos_time_of_day": round(cos_time_of_day, 6),
        "sin_day_of_week": round(sin_day_of_week, 6),
        "cos_day_of_week": round(cos_day_of_week, 6),
    }


def compute_lag_features(
    buckets: Sequence[CashFlowBucket],
    lags: Sequence[int] = (1, 2, 4, 96),
    fill_value: int | None = None,
) -> list[dict[str, int | None]]:
    """
    Compute historical lag features for a sequence of CashFlowBuckets.
    
    For index i and lag k, the feature value is taken from index i - k.
    If i - k < 0, fill_value is used (default None).
    """
    results: list[dict[str, int | None]] = []
    for i in range(len(buckets)):
        row: dict[str, int | None] = {}
        for lag in lags:
            prev_idx = i - lag
            if prev_idx >= 0:
                row[f"lag_{lag}_inflow_cents"] = buckets[prev_idx].inflow_cents
                row[f"lag_{lag}_outflow_cents"] = buckets[prev_idx].outflow_cents
                row[f"lag_{lag}_net_cents"] = (
                    buckets[prev_idx].inflow_cents - buckets[prev_idx].outflow_cents
                )
            else:
                row[f"lag_{lag}_inflow_cents"] = fill_value
                row[f"lag_{lag}_outflow_cents"] = fill_value
                row[f"lag_{lag}_net_cents"] = fill_value
        results.append(row)
    return results


def compute_rolling_features(
    buckets: Sequence[CashFlowBucket],
    windows: Sequence[int] = (4, 16, 96),
    strictly_prior: bool = False,
) -> list[dict[str, float | None]]:
    """
    Compute causal rolling means and standard deviations for inflows, outflows, and net flows.
    
    If strictly_prior is True, window for index i considers buckets up to i - 1.
    If strictly_prior is False, window for index i includes bucket i.
    """
    results: list[dict[str, float | None]] = []
    for i in range(len(buckets)):
        row: dict[str, float | None] = {}
        for w in windows:
            if strictly_prior:
                start_idx = max(0, i - w)
                end_idx = i  # exclusive, so up to i - 1
            else:
                start_idx = max(0, i - w + 1)
                end_idx = i + 1

            if end_idx <= start_idx:
                row[f"rolling_mean_{w}_inflow_cents"] = None
                row[f"rolling_std_{w}_inflow_cents"] = None
                row[f"rolling_mean_{w}_outflow_cents"] = None
                row[f"rolling_std_{w}_outflow_cents"] = None
                row[f"rolling_mean_{w}_net_cents"] = None
                row[f"rolling_std_{w}_net_cents"] = None
                continue

            window_buckets = buckets[start_idx:end_idx]
            n = len(window_buckets)

            inflows = [b.inflow_cents for b in window_buckets]
            outflows = [b.outflow_cents for b in window_buckets]
            nets = [b.inflow_cents - b.outflow_cents for b in window_buckets]

            mean_in = sum(inflows) / n
            mean_out = sum(outflows) / n
            mean_net = sum(nets) / n

            if n > 1:
                std_in = math.sqrt(sum((x - mean_in) ** 2 for x in inflows) / (n - 1))
                std_out = math.sqrt(sum((x - mean_out) ** 2 for x in outflows) / (n - 1))
                std_net = math.sqrt(sum((x - mean_net) ** 2 for x in nets) / (n - 1))
            else:
                std_in = 0.0
                std_out = 0.0
                std_net = 0.0

            row[f"rolling_mean_{w}_inflow_cents"] = round(mean_in, 2)
            row[f"rolling_std_{w}_inflow_cents"] = round(std_in, 2)
            row[f"rolling_mean_{w}_outflow_cents"] = round(mean_out, 2)
            row[f"rolling_std_{w}_outflow_cents"] = round(std_out, 2)
            row[f"rolling_mean_{w}_net_cents"] = round(mean_net, 2)
            row[f"rolling_std_{w}_net_cents"] = round(std_net, 2)

        results.append(row)
    return results


def build_feature_matrix(
    buckets: Sequence[CashFlowBucket],
    bucket_minutes: int = 15,
    lags: Sequence[int] = (1, 2, 4, 96),
    windows: Sequence[int] = (4, 16, 96),
) -> list[dict[str, Any]]:
    """
    Construct a complete causal feature row for each bucket in the historical series.
    """
    lag_feats = compute_lag_features(buckets, lags=lags)
    rolling_feats = compute_rolling_features(buckets, windows=windows, strictly_prior=True)

    matrix: list[dict[str, Any]] = []
    for i, bucket in enumerate(buckets):
        cal = extract_calendar_features(bucket.start_at, bucket_minutes=bucket_minutes)
        row = {
            "start_at": bucket.start_at,
            "end_at": bucket.end_at,
            "inflow_cents": bucket.inflow_cents,
            "outflow_cents": bucket.outflow_cents,
            "net_cents": bucket.inflow_cents - bucket.outflow_cents,
            **cal,
            **lag_feats[i],
            **rolling_feats[i],
        }
        matrix.append(row)
    return matrix
