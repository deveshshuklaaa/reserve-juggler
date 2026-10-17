from datetime import datetime, timedelta, timezone
import math
import pytest

import treasury_intelligence as e
from treasury_intelligence.features import (
    extract_calendar_features,
    compute_lag_features,
    compute_rolling_features,
    build_feature_matrix,
)
from treasury_intelligence.forecasting import (
    rolling_mean_forecast,
    seasonal_naive_forecast,
)

BASE_TIME = datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc)


def make_history(n_buckets: int, inflow_base: int = 100_000, outflow_base: int = 80_000, bucket_minutes: int = 15):
    """Helper to generate a sequence of contiguous historical buckets."""
    buckets = []
    delta = timedelta(minutes=bucket_minutes)
    for i in range(n_buckets):
        start = BASE_TIME + i * delta
        end = start + delta
        # Add slight variation
        inf = inflow_base + (i % 10) * 5_000
        outf = outflow_base + (i % 8) * 4_000
        buckets.append(
            e.CashFlowBucket(
                start_at=start,
                end_at=end,
                inflow_cents=inf,
                outflow_cents=outf,
            )
        )
    return tuple(buckets)


# --- 1. Feature Engineering Tests ---

def test_calendar_features_causal():
    dt = datetime(2026, 10, 17, 14, 30, tzinfo=timezone.utc)  # Saturday, 14:30
    feats = extract_calendar_features(dt, bucket_minutes=15)

    assert feats["hour_of_day"] == 14
    assert feats["minute_of_day"] == 14 * 60 + 30
    assert feats["interval_of_day"] == (14 * 60 + 30) // 15
    assert feats["day_of_week"] == 5  # Saturday
    assert feats["is_weekend"] == 1

    # Cyclical checks
    expected_sin_time = round(math.sin(2.0 * math.pi * (14 * 60 + 30) / 1440.0), 6)
    assert feats["sin_time_of_day"] == expected_sin_time

    # Must reject naive timezone
    with pytest.raises(ValueError, match="timezone-aware UTC"):
        extract_calendar_features(datetime(2026, 10, 17, 14, 30))


def test_correct_lag_alignment():
    history = [
        e.CashFlowBucket(
            start_at=BASE_TIME + i * timedelta(minutes=15),
            end_at=BASE_TIME + (i + 1) * timedelta(minutes=15),
            inflow_cents=(i + 1) * 1000,
            outflow_cents=(i + 1) * 500,
        )
        for i in range(10)
    ]

    lags = (1, 2, 4, 96)
    lag_feats = compute_lag_features(history, lags=lags)

    assert len(lag_feats) == 10

    # At index 0, all lags should be None (no prior data)
    assert lag_feats[0]["lag_1_inflow_cents"] is None
    assert lag_feats[0]["lag_2_inflow_cents"] is None

    # At index 1, lag 1 is index 0
    assert lag_feats[1]["lag_1_inflow_cents"] == 1000
    assert lag_feats[1]["lag_1_outflow_cents"] == 500
    assert lag_feats[1]["lag_1_net_cents"] == 500
    assert lag_feats[1]["lag_2_inflow_cents"] is None

    # At index 5:
    # lag 1 = index 4 (5000 inflow)
    # lag 2 = index 3 (4000 inflow)
    # lag 4 = index 1 (2000 inflow)
    # lag 96 = None (history length is only 10)
    assert lag_feats[5]["lag_1_inflow_cents"] == 5000
    assert lag_feats[5]["lag_2_inflow_cents"] == 4000
    assert lag_feats[5]["lag_4_inflow_cents"] == 2000
    assert lag_feats[5]["lag_96_inflow_cents"] is None


def test_rolling_inflow_outflow_means_and_stds():
    # Constant series -> std should be 0.0
    constant_history = [
        e.CashFlowBucket(
            start_at=BASE_TIME + i * timedelta(minutes=15),
            end_at=BASE_TIME + (i + 1) * timedelta(minutes=15),
            inflow_cents=50_000,
            outflow_cents=30_000,
        )
        for i in range(8)
    ]
    rolling = compute_rolling_features(constant_history, windows=(4,))
    assert rolling[3]["rolling_mean_4_inflow_cents"] == 50_000.0
    assert rolling[3]["rolling_std_4_inflow_cents"] == 0.0
    assert rolling[3]["rolling_mean_4_outflow_cents"] == 30_000.0
    assert rolling[3]["rolling_std_4_outflow_cents"] == 0.0

    # Varying series
    varying_history = [
        e.CashFlowBucket(
            start_at=BASE_TIME + i * timedelta(minutes=15),
            end_at=BASE_TIME + (i + 1) * timedelta(minutes=15),
            inflow_cents=10_000 * (i + 1),
            outflow_cents=5_000 * (i + 1),
        )
        for i in range(4)
    ]
    # inflows: 10k, 20k, 30k, 40k -> mean = 25k, sample std of (10, 20, 30, 40) is ~12909.94
    rolling_var = compute_rolling_features(varying_history, windows=(4,))
    assert rolling_var[3]["rolling_mean_4_inflow_cents"] == 25_000.0
    assert rolling_var[3]["rolling_std_4_inflow_cents"] == pytest.approx(12909.94, abs=0.1)


def test_feature_matrix_generation():
    history = make_history(10)
    matrix = build_feature_matrix(history, bucket_minutes=15)
    assert len(matrix) == 10
    row = matrix[5]
    assert "sin_time_of_day" in row
    assert "lag_1_inflow_cents" in row
    assert "rolling_mean_4_inflow_cents" in row
    assert row["inflow_cents"] == history[5].inflow_cents


# --- 2. Baseline Forecasting Tests ---

@pytest.mark.parametrize("intervals,horizon_minutes", [
    (1, 15),
    (2, 30),
    (4, 60),
    (96, 1440),
])
def test_forecast_horizons_1_2_4_96(intervals, horizon_minutes):
    history = make_history(100)
    as_of = history[-1].end_at

    result = e.forecast_cashflows(
        history,
        as_of=as_of,
        horizon_minutes=horizon_minutes,
        bucket_minutes=15,
        model_version="rolling-mean-v1",
    )

    assert result.generated_at == as_of
    assert result.model_version == "rolling-mean-v1"
    assert len(result.points) == intervals

    # Interval continuity
    assert result.points[0].start_at == as_of
    assert result.points[0].end_at == as_of + timedelta(minutes=15)
    for i in range(len(result.points) - 1):
        assert result.points[i].end_at == result.points[i + 1].start_at
    assert result.points[-1].end_at == as_of + timedelta(minutes=horizon_minutes)


def test_separate_inflow_and_outflow_predictions():
    history = [
        e.CashFlowBucket(
            start_at=BASE_TIME + i * timedelta(minutes=15),
            end_at=BASE_TIME + (i + 1) * timedelta(minutes=15),
            inflow_cents=200_000,
            outflow_cents=50_000,
        )
        for i in range(16)
    ]
    as_of = history[-1].end_at

    res = e.forecast_cashflows(
        history, as_of=as_of, horizon_minutes=30, bucket_minutes=15, model_version="rolling-mean-v1"
    )

    assert len(res.points) == 2
    for p in res.points:
        assert p.inflow_cents == 200_000
        assert p.outflow_cents == 50_000
        assert p.uncertainty_cents == 0  # constant net flows -> 0 uncertainty


def test_seasonal_naive_forecast_with_full_history():
    # 96 intervals per day. Create 2 days = 192 intervals
    history = make_history(192, inflow_base=100_000, outflow_base=60_000)
    as_of = history[-1].end_at

    result = e.forecast_cashflows(
        history,
        as_of=as_of,
        horizon_minutes=60,  # 4 intervals
        bucket_minutes=15,
        model_version="seasonal-naive-v1",
    )

    assert len(result.points) == 4
    # Future point 0 corresponds to history[192 - 96 + 0] = history[96]
    assert result.points[0].inflow_cents == history[96].inflow_cents
    assert result.points[0].outflow_cents == history[96].outflow_cents
    # Future point 1 corresponds to history[97]
    assert result.points[1].inflow_cents == history[97].inflow_cents
    assert result.points[1].outflow_cents == history[97].outflow_cents


def test_short_history_fallback():
    # 1. Seasonal naive with only 10 buckets (< 96) -> automatically falls back to rolling mean
    short_history = make_history(10)
    as_of = short_history[-1].end_at

    res = e.forecast_cashflows(
        short_history,
        as_of=as_of,
        horizon_minutes=30,
        bucket_minutes=15,
        model_version="seasonal-naive-v1",
    )
    assert len(res.points) == 2
    assert res.points[0].inflow_cents > 0
    assert res.points[0].outflow_cents > 0

    # 2. History with 1 bucket
    single_history = (
        e.CashFlowBucket(
            start_at=BASE_TIME,
            end_at=BASE_TIME + timedelta(minutes=15),
            inflow_cents=123_456,
            outflow_cents=65_432,
        ),
    )
    res_single = e.forecast_cashflows(
        single_history,
        as_of=single_history[0].end_at,
        horizon_minutes=15,
        bucket_minutes=15,
        model_version="rolling-mean-v1",
    )
    assert len(res_single.points) == 1
    assert res_single.points[0].inflow_cents == 123_456
    assert res_single.points[0].outflow_cents == 65_432

    # 3. Empty history
    res_empty = e.forecast_cashflows(
        (),
        as_of=BASE_TIME,
        horizon_minutes=60,
        bucket_minutes=15,
        model_version="baseline-v1",
    )
    assert len(res_empty.points) == 4
    for p in res_empty.points:
        assert p.inflow_cents == 0
        assert p.outflow_cents == 0
        assert p.uncertainty_cents == 0


def test_zero_cash_flow_input():
    history = [
        e.CashFlowBucket(
            start_at=BASE_TIME + i * timedelta(minutes=15),
            end_at=BASE_TIME + (i + 1) * timedelta(minutes=15),
            inflow_cents=0,
            outflow_cents=0,
        )
        for i in range(20)
    ]
    as_of = history[-1].end_at

    res = e.forecast_cashflows(
        history, as_of=as_of, horizon_minutes=60, bucket_minutes=15, model_version="rolling-mean-v1"
    )

    for p in res.points:
        assert p.inflow_cents == 0
        assert p.outflow_cents == 0
        assert p.uncertainty_cents == 0


def test_reproducible_predictions():
    history = make_history(50)
    as_of = history[-1].end_at

    res1 = e.forecast_cashflows(
        history, as_of=as_of, horizon_minutes=60, bucket_minutes=15, model_version="rolling-mean-v1"
    )
    res2 = e.forecast_cashflows(
        history, as_of=as_of, horizon_minutes=60, bucket_minutes=15, model_version="rolling-mean-v1"
    )

    assert res1 == res2
    assert res1.model_dump_json() == res2.model_dump_json()


def test_nonnegative_predicted_inflow_outflow():
    history = make_history(30)
    as_of = history[-1].end_at

    res = e.forecast_cashflows(
        history, as_of=as_of, horizon_minutes=1440, bucket_minutes=15, model_version="rolling-mean-v1"
    )

    for p in res.points:
        assert isinstance(p.inflow_cents, int)
        assert isinstance(p.outflow_cents, int)
        assert isinstance(p.uncertainty_cents, int)
        assert p.inflow_cents >= 0
        assert p.outflow_cents >= 0
        assert p.uncertainty_cents >= 0


def test_json_serialization_roundtrip():
    history = make_history(20)
    as_of = history[-1].end_at

    res = e.forecast_cashflows(
        history, as_of=as_of, horizon_minutes=60, bucket_minutes=15, model_version="baseline-v1"
    )

    json_str = res.model_dump_json()
    deserialized = e.ForecastResult.model_validate_json(json_str)

    assert deserialized == res
    assert len(deserialized.points) == 4


def test_causality_and_input_validation():
    history = make_history(10)
    as_of = history[-1].end_at

    # Future data in history: bucket ends after as_of
    invalid_as_of = history[-2].end_at  # earlier than last bucket end
    with pytest.raises(ValueError, match="causality breach"):
        e.forecast_cashflows(
            history, as_of=invalid_as_of, horizon_minutes=30, bucket_minutes=15
        )

    # Incompatible horizon and bucket_minutes
    with pytest.raises(ValueError, match="exact multiple"):
        e.forecast_cashflows(
            history, as_of=as_of, horizon_minutes=25, bucket_minutes=15
        )

    # Non-UTC as_of
    naive_as_of = datetime(2026, 10, 1, 12, 0)
    with pytest.raises(ValueError, match="timezone-aware UTC"):
        e.forecast_cashflows(
            history, as_of=naive_as_of, horizon_minutes=30, bucket_minutes=15
        )

    # Unsupported model_version
    with pytest.raises(ValueError, match="unsupported model_version"):
        e.forecast_cashflows(
            history, as_of=as_of, horizon_minutes=30, bucket_minutes=15, model_version="random-forest"
        )
