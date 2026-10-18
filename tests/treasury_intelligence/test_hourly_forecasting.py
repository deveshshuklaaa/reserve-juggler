"""Tests for native hourly cash-flow forecasting and causal feature engineering (RJ-M1-07)."""
import csv
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import math
from pathlib import Path

import pytest
from pydantic import ValidationError

from treasury_intelligence import (
    ForecastResolution,
    FourTierRecommendationRequest,
    HourlyCashFlowBucket,
    HourlyForecastConfig,
    HourlyForecastPoint,
    HourlyForecastResult,
    OrganizerHourlyObservation,
    SUPPORTED_HOURLY_HORIZONS,
    build_hourly_feature_matrix,
    compute_hourly_lag_features,
    compute_hourly_rolling_features,
    extract_hourly_calendar_features,
    forecast_cashflows,
    forecast_hourly_cashflows,
    hourly_rolling_mean_forecast,
    hourly_seasonal_naive_forecast,
    load_organizer_dataset,
    validate_hourly_forecast_inputs,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def hourly_series_168() -> tuple[OrganizerHourlyObservation, ...]:
    """168 contiguous real hourly observations from the organizer dataset fixture."""
    fixture_path = FIXTURES_DIR / "organizer_hourly_series.json"
    data = json.loads(fixture_path.read_text(encoding="utf-8"))
    return tuple(OrganizerHourlyObservation.model_validate(r) for r in data)


# ---------------------------------------------------------------------------
# 1. Configuration and Contract Fidelity
# ---------------------------------------------------------------------------

def test_forecast_resolution_enumeration():
    assert ForecastResolution.HOURLY == "1h"
    assert ForecastResolution.QUARTER_HOURLY == "15m"
    assert set(SUPPORTED_HOURLY_HORIZONS) == {1, 3, 6, 15, 24}


def test_hourly_cashflow_bucket_model():
    bucket = HourlyCashFlowBucket(
        timestamp="2026-01-01T12:00:00",
        deposits_usd="1234.56",
        withdrawals_usd="1000.00",
        net_flow_usd="234.56",
    )
    assert bucket.deposits_cents == 123456
    assert bucket.withdrawals_cents == 100000
    assert bucket.net_flow_cents == 23456
    assert bucket.timestamp == datetime(2026, 1, 1, 12, 0, 0)

    # Rejection of non-hourly or timezone-aware timestamps
    with pytest.raises(ValidationError):
        HourlyCashFlowBucket(
            timestamp="2026-01-01T12:15:00",
            deposits_usd="10.00",
            withdrawals_usd="5.00",
            net_flow_usd="5.00",
        )
    with pytest.raises(ValidationError):
        HourlyCashFlowBucket(
            timestamp="2026-01-01T12:00:00Z",
            deposits_usd="10.00",
            withdrawals_usd="5.00",
            net_flow_usd="5.00",
        )


def test_hourly_forecast_config_defaults_and_validation():
    cfg = HourlyForecastConfig()
    assert cfg.resolution == "1h"
    assert cfg.horizon_hours == 24
    assert cfg.model_version == "hourly-seasonal-naive-v1"
    assert cfg.rolling_window_hours == 24
    assert cfg.season_hours == 24
    assert cfg.uncertainty_multiplier == Decimal("1.0")

    custom = HourlyForecastConfig(
        resolution="1h",
        horizon_hours=15,
        model_version="hourly-rolling-mean-v1",
        rolling_window_hours=48,
        season_hours=24,
        uncertainty_multiplier=Decimal("1.5"),
    )
    assert custom.horizon_hours == 15
    assert custom.rolling_window_hours == 48


def test_hourly_forecast_result_serialization_and_immutability():
    as_of = datetime(2026, 1, 2, 17, 0, 0)
    point = HourlyForecastPoint(
        start_at=as_of + timedelta(hours=1),
        predicted_deposits_cents=50000,
        predicted_withdrawals_cents=30000,
        predicted_net_flow_cents=20000,
        supplied_uncertainty_buffer_cents=5000,
    )
    res = hourly_rolling_mean_forecast(
        history=[],
        as_of=as_of,
        horizon_hours=1,
    )
    dumped = res.model_dump_json()
    assert "hourly-rolling-mean-v1" in dumped
    assert '"resolution":"1h"' in dumped
    parsed = HourlyForecastResult.model_validate_json(dumped)
    assert parsed.generated_at == as_of
    assert parsed.resolution == "1h"
    assert parsed.horizon_hours == 1

    with pytest.raises(ValidationError):
        parsed.horizon_hours = 2  # Frozen


# ---------------------------------------------------------------------------
# 2. Causal Feature Engineering
# ---------------------------------------------------------------------------

def test_extract_hourly_calendar_features():
    # 2026-01-01 was a Thursday (weekday=3)
    dt = datetime(2026, 1, 1, 17, 0, 0)
    cal = extract_hourly_calendar_features(dt)
    assert cal["hour_of_day"] == 17
    assert cal["day_of_week"] == 3
    assert cal["is_weekend"] == 0
    assert math.isclose(cal["sin_hour_of_day"], math.sin(2 * math.pi * 17 / 24), abs_tol=1e-5)
    assert math.isclose(cal["cos_hour_of_day"], math.cos(2 * math.pi * 17 / 24), abs_tol=1e-5)

    # Weekend check: 2026-01-03 is Saturday (weekday=5)
    dt_sat = datetime(2026, 1, 3, 10, 0, 0)
    cal_sat = extract_hourly_calendar_features(dt_sat)
    assert cal_sat["day_of_week"] == 5
    assert cal_sat["is_weekend"] == 1

    # Rejection of timezone-aware datetimes
    with pytest.raises(ValueError, match="unspecified timezone"):
        extract_hourly_calendar_features(datetime(2026, 1, 1, 17, 0, 0, tzinfo=timezone(timedelta(hours=5))))

    # Rejection of non-hourly datetimes (e.g. 17:15)
    with pytest.raises(ValueError, match="exact hourly boundaries"):
        extract_hourly_calendar_features(datetime(2026, 1, 1, 17, 15, 0))


def test_correct_hourly_lag_alignment_and_named_aliases(hourly_series_168):
    obs = hourly_series_168
    lags = compute_hourly_lag_features(obs, lags=(1, 2, 3, 24, 168))

    # At index 0: all lags should be None
    assert lags[0]["lag_1_deposits_usd"] is None
    assert lags[0]["lag_24_deposits_usd"] is None
    assert lags[0]["same_hour_prev_day_deposits_usd"] is None
    assert lags[0]["same_hour_prev_week_deposits_usd"] is None

    # At index 1: lag 1 matches index 0 exactly
    assert lags[1]["lag_1_deposits_usd"] == float(obs[0].deposits_usd)
    assert lags[1]["lag_1_withdrawals_usd"] == float(obs[0].withdrawals_usd)
    assert lags[1]["lag_2_deposits_usd"] is None

    # At index 24: exactly 24 hours later (same hour previous day)
    # Target observation is at index 24 (2026-01-02 00:00:00)
    # Lag 24 should be index 0 (2026-01-01 00:00:00)
    assert lags[24]["lag_24_deposits_usd"] == float(obs[0].deposits_usd)
    assert lags[24]["same_hour_prev_day_deposits_usd"] == float(obs[0].deposits_usd)
    assert lags[24]["same_hour_prev_day_withdrawals_usd"] == float(obs[0].withdrawals_usd)
    assert lags[24]["same_hour_prev_week_deposits_usd"] is None

    # At index 167 (last of 168 hours):
    # Lag 168 is not available yet (needs index 168)
    assert lags[167]["same_hour_prev_week_deposits_usd"] is None


def test_causal_rolling_features_and_volatility(hourly_series_168):
    obs = hourly_series_168[:30]
    rolling = compute_hourly_rolling_features(obs, windows=(3, 6, 24), strictly_prior=True)

    # With strictly_prior=True:
    # Index 0 has no strictly prior observations -> None
    assert rolling[0]["rolling_mean_3_deposits_usd"] is None
    assert rolling[0]["rolling_volatility_3_deposits_usd"] is None

    # Index 1 has exactly 1 prior observation (index 0)
    assert rolling[1]["rolling_mean_3_deposits_usd"] == round(float(obs[0].deposits_usd), 2)
    assert rolling[1]["rolling_volatility_3_deposits_usd"] == 0.0  # single observation variance is 0

    # Index 3 has 3 prior observations (indices 0, 1, 2)
    d_vals = [float(o.deposits_usd) for o in obs[:3]]
    expected_mean = round(sum(d_vals) / 3, 2)
    var = sum((x - (sum(d_vals) / 3)) ** 2 for x in d_vals) / 2
    expected_std = round(math.sqrt(var), 2)
    assert rolling[3]["rolling_mean_3_deposits_usd"] == expected_mean
    assert rolling[3]["rolling_volatility_3_deposits_usd"] == expected_std


def test_build_hourly_feature_matrix_shapes_and_values(hourly_series_168):
    obs = hourly_series_168[:50]
    matrix = build_hourly_feature_matrix(obs, lags=(1, 2, 24), windows=(3, 24), strictly_prior=True)
    assert len(matrix) == 50
    first = matrix[0]
    assert first["hour_of_day"] == 0
    assert first["day_of_week"] == 3
    assert first["is_weekend"] == 0
    assert first["deposits_cents"] > 0
    assert first["lag_1_deposits_usd"] is None

    row_25 = matrix[25]
    assert row_25["hour_of_day"] == 1
    assert row_25["same_hour_prev_day_deposits_usd"] is not None


# ---------------------------------------------------------------------------
# 3. Forecast Baselines and Horizon Support
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("horizon", [1, 3, 6, 15, 24])
def test_supported_hourly_horizons_path_completeness(hourly_series_168, horizon):
    history = hourly_series_168[:48]
    as_of = history[-1].timestamp

    # Test rolling mean
    res_rm = hourly_rolling_mean_forecast(history, as_of=as_of, horizon_hours=horizon)
    assert res_rm.horizon_hours == horizon
    assert res_rm.resolution == "1h"
    assert len(res_rm.points) == horizon
    assert res_rm.generated_at == as_of

    # Test seasonal naive
    res_sn = hourly_seasonal_naive_forecast(history, as_of=as_of, horizon_hours=horizon)
    assert res_sn.horizon_hours == horizon
    assert res_sn.resolution == "1h"
    assert len(res_sn.points) == horizon
    assert res_sn.generated_at == as_of

    # Check path spacing and monotonicity: strictly 1-hour increments
    for i in range(len(res_sn.points)):
        pt = res_sn.points[i]
        expected_start = as_of + timedelta(hours=i + 1)
        assert pt.start_at == expected_start
        assert pt.predicted_deposits_cents >= 0
        assert pt.predicted_withdrawals_cents >= 0
        assert pt.supplied_uncertainty_buffer_cents >= 0
        assert pt.predicted_net_flow_cents == pt.predicted_deposits_cents - pt.predicted_withdrawals_cents


def test_15_hour_overnight_repo_horizon(hourly_series_168):
    # Overnight repo is entered at 17:00 and matures next day at 08:00 (exactly 15 hours)
    # Find an observation at 17:00
    idx_17 = next(i for i, o in enumerate(hourly_series_168) if o.timestamp.hour == 17 and i >= 24)
    history = hourly_series_168[:idx_17 + 1]
    as_of = history[-1].timestamp
    assert as_of.hour == 17

    res = forecast_hourly_cashflows(history, as_of=as_of, horizon_hours=15)
    assert len(res.points) == 15
    assert res.points[0].start_at == as_of + timedelta(hours=1)  # 18:00
    assert res.points[-1].start_at == as_of + timedelta(hours=15)  # 08:00 next day
    assert res.points[-1].start_at.hour == 8

    # Totals and paths
    assert res.total_predicted_deposits_cents == sum(res.path_deposits_cents)
    assert res.total_predicted_withdrawals_cents == sum(res.path_withdrawals_cents)
    assert res.total_predicted_net_flow_cents == sum(res.path_net_flow_cents)


def test_24_hour_daily_cycle_horizon(hourly_series_168):
    history = hourly_series_168[:48]
    as_of = history[-1].timestamp
    res = forecast_hourly_cashflows(history, as_of=as_of, horizon_hours=24)
    assert len(res.points) == 24
    assert res.points[0].start_at == as_of + timedelta(hours=1)
    assert res.points[-1].start_at == as_of + timedelta(hours=24)


def test_seasonal_naive_matches_previous_day_hour(hourly_series_168):
    history = hourly_series_168[:48]
    as_of = history[-1].timestamp  # Day 2, hour 23
    res = hourly_seasonal_naive_forecast(history, as_of=as_of, horizon_hours=24, season_hours=24)

    # For step 0 (Day 3, hour 0), seasonal naive must match Day 2, hour 0
    # In history[:48], Day 2 hour 0 is at index 24
    expected_dep = int((history[24].deposits_usd * 100).to_integral_value())
    expected_wtd = int((history[24].withdrawals_usd * 100).to_integral_value())

    assert res.points[0].predicted_deposits_cents == expected_dep
    assert res.points[0].predicted_withdrawals_cents == expected_wtd


def test_baseline_reproducibility(hourly_series_168):
    history = hourly_series_168[:48]
    as_of = history[-1].timestamp
    res1 = forecast_hourly_cashflows(history, as_of=as_of, horizon_hours=24)
    res2 = forecast_hourly_cashflows(history, as_of=as_of, horizon_hours=24)

    assert res1.model_dump_json() == res2.model_dump_json()
    assert res1.path_deposits_cents == res2.path_deposits_cents
    assert res1.path_withdrawals_cents == res2.path_withdrawals_cents


# ---------------------------------------------------------------------------
# 4. Causality and Safe Fallbacks
# ---------------------------------------------------------------------------

def test_no_future_data_leakage(hourly_series_168):
    history = hourly_series_168[:48]
    # If as_of is set prior to the end of history, input validation MUST reject it
    breached_as_of = history[20].timestamp
    with pytest.raises(ValueError, match="causality breach"):
        forecast_hourly_cashflows(history, as_of=breached_as_of, horizon_hours=6)


def test_no_synthetic_quarter_hour_splitting(hourly_series_168):
    history = hourly_series_168[:24]
    as_of = history[-1].timestamp
    res = forecast_hourly_cashflows(history, as_of=as_of, horizon_hours=6)

    # Assert that all points retain hourly spacing, never 15-minute intervals
    for pt in res.points:
        assert pt.start_at.minute == 0
        assert pt.start_at.second == 0

    for a, b in zip(res.points, res.points[1:]):
        assert b.start_at - a.start_at == timedelta(hours=1)


def test_safe_fallback_empty_history():
    as_of = datetime(2026, 1, 1, 10, 0, 0)
    res_rm = hourly_rolling_mean_forecast([], as_of=as_of, horizon_hours=24)
    assert len(res_rm.points) == 24
    assert all(pt.predicted_deposits_cents == 0 for pt in res_rm.points)
    assert all(pt.predicted_withdrawals_cents == 0 for pt in res_rm.points)
    assert all(pt.supplied_uncertainty_buffer_cents == 0 for pt in res_rm.points)

    res_sn = hourly_seasonal_naive_forecast([], as_of=as_of, horizon_hours=15)
    assert len(res_sn.points) == 15
    assert all(pt.predicted_deposits_cents == 0 for pt in res_sn.points)


def test_safe_fallback_short_history_below_seasonal_cycle(hourly_series_168):
    # History has only 10 hours (< 24h seasonal cycle)
    short_hist = hourly_series_168[:10]
    as_of = short_hist[-1].timestamp
    res = hourly_seasonal_naive_forecast(short_hist, as_of=as_of, horizon_hours=6, season_hours=24)

    # Should safely fallback to rolling-mean over the 10 hours while maintaining requested model_version
    assert len(res.points) == 6
    assert res.points[0].predicted_deposits_cents > 0
    assert res.points[0].predicted_withdrawals_cents > 0
    # Rolling mean produces identical predictions for each step
    assert res.points[0].predicted_deposits_cents == res.points[1].predicted_deposits_cents


# ---------------------------------------------------------------------------
# 5. Integration with FourTierRecommendationRequest
# ---------------------------------------------------------------------------

def test_hourly_forecast_satisfies_four_tier_recommendation_request(hourly_series_168):
    req_fixture = json.loads((FIXTURES_DIR / "four_tier_request.json").read_text(encoding="utf-8"))
    history_rows = hourly_series_168[:18]  # Ends at 2026-01-01 17:00:00 (repo entry time)
    as_of = history_rows[-1].timestamp
    assert as_of.hour == 17

    # Generate 15-hour forecast starting from as_of
    forecast_result = forecast_hourly_cashflows(history_rows, as_of=as_of, horizon_hours=15)

    # Prepare request payload with newly generated hourly forecast
    req_dict = dict(req_fixture)
    req_dict["portfolio"]["as_of"] = as_of.isoformat()
    req_dict["portfolio"]["repos"][0]["entered_at"] = as_of.isoformat()
    req_dict["portfolio"]["repos"][0]["matures_at"] = (as_of + timedelta(hours=15)).isoformat()
    req_dict["portfolio"]["bonds"][0]["marked_at"] = as_of.isoformat()
    req_dict["portfolio"]["equities"][0]["marked_at"] = as_of.isoformat()
    req_dict["portfolio"]["market_rates"]["observed_at"] = as_of.isoformat()
    req_dict["portfolio"]["market_prices"]["observed_at"] = as_of.isoformat()
    req_dict["history"] = [json.loads(h.model_dump_json()) for h in history_rows]
    req_dict["metadata"] = json.loads(forecast_result.metadata.model_dump_json())
    req_dict["forecast"] = [json.loads(p.model_dump_json()) for p in forecast_result.points]

    # Validate against FourTierRecommendationRequest
    request = FourTierRecommendationRequest.model_validate(req_dict)
    assert len(request.forecast) == 15
    assert request.forecast[0].start_at == as_of + timedelta(hours=1)


# ---------------------------------------------------------------------------
# 6. Preservation of 15-Minute Synthetic Mode
# ---------------------------------------------------------------------------

def test_preservation_of_15_minute_synthetic_mode():
    from treasury_intelligence import CashFlowBucket
    from datetime import timezone

    as_of = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    delta = timedelta(minutes=15)
    history = [
        CashFlowBucket(
            start_at=as_of - (i + 1) * delta,
            end_at=as_of - i * delta,
            inflow_cents=100000,
            outflow_cents=80000,
        )
        for i in reversed(range(8))
    ]
    res_15m = forecast_cashflows(
        history,
        as_of=as_of,
        horizon_minutes=60,
        bucket_minutes=15,
        model_version="rolling-mean-v1",
    )
    assert len(res_15m.points) == 4
    assert res_15m.points[0].start_at == as_of
    assert res_15m.points[0].end_at == as_of + delta


# ---------------------------------------------------------------------------
# 7. Local Read-Only Organizer Dataset Loader
# ---------------------------------------------------------------------------

def test_load_organizer_dataset_from_fixture_and_limits():
    fixture_path = FIXTURES_DIR / "organizer_hourly_series.json"
    rows_json = json.loads(fixture_path.read_text(encoding="utf-8"))

    # Convert to CSV format in memory
    import io
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(rows_json[0].keys()))
    writer.writeheader()
    writer.writerows(rows_json)
    output.seek(0)

    # Test loading with limit
    loaded_10 = load_organizer_dataset(output, limit=10)
    assert len(loaded_10) == 10
    assert isinstance(loaded_10[0], OrganizerHourlyObservation)
    assert loaded_10[0].timestamp.tzinfo is None
    assert loaded_10[0].deposits_usd > 0


# ---------------------------------------------------------------------------
# 8. Edge Cases, Validation Rejections, and Full Dataset Verification
# ---------------------------------------------------------------------------

def test_hourly_forecasting_input_validation_rejections(hourly_series_168):
    valid_history = hourly_series_168[:5]
    as_of = valid_history[-1].timestamp

    # Invalid as_of types / formats
    with pytest.raises(ValueError, match="datetime object"):
        validate_hourly_forecast_inputs(valid_history, as_of="2026-01-01T04:00:00", horizon_hours=6)

    with pytest.raises(ValueError, match="unspecified timezone"):
        validate_hourly_forecast_inputs(
            valid_history, as_of=datetime(2026, 1, 1, 4, 0, 0, tzinfo=timezone.utc), horizon_hours=6
        )

    with pytest.raises(ValueError, match="exact hourly boundary"):
        validate_hourly_forecast_inputs(valid_history, as_of=datetime(2026, 1, 1, 4, 15, 0), horizon_hours=6)

    # Invalid horizon
    with pytest.raises(ValueError, match="positive integer"):
        validate_hourly_forecast_inputs(valid_history, as_of=as_of, horizon_hours=0)

    with pytest.raises(ValueError, match="positive integer"):
        validate_hourly_forecast_inputs(valid_history, as_of=as_of, horizon_hours=-5)

    with pytest.raises(ValueError, match="positive integer"):
        validate_hourly_forecast_inputs(valid_history, as_of=as_of, horizon_hours=True)

    # History out of chronological order
    reversed_hist = list(reversed(valid_history))
    with pytest.raises(ValueError, match="strictly chronologically ordered"):
        validate_hourly_forecast_inputs(reversed_hist, as_of=as_of, horizon_hours=6)


def test_hourly_cashflow_bucket_from_observation(hourly_series_168):
    obs = hourly_series_168[0]
    bucket = HourlyCashFlowBucket.from_observation(obs)
    assert bucket.timestamp == obs.timestamp
    assert bucket.deposits_usd == obs.deposits_usd
    assert bucket.withdrawals_usd == obs.withdrawals_usd
    assert bucket.net_flow_usd == obs.net_flow_usd
    assert bucket.deposits_cents == int((obs.deposits_usd * 100).to_integral_value())


def test_single_observation_history_rolling_mean():
    # If len(history) == 1, uncertainty is 15% of total volume
    obs = HourlyCashFlowBucket(
        timestamp="2026-01-01T10:00:00",
        deposits_usd="1000.00",
        withdrawals_usd="500.00",
        net_flow_usd="500.00",
    )
    res = hourly_rolling_mean_forecast([obs], as_of=datetime(2026, 1, 1, 10, 0, 0), horizon_hours=3)
    assert len(res.points) == 3
    assert res.points[0].predicted_deposits_cents == 100000
    assert res.points[0].predicted_withdrawals_cents == 50000
    assert res.points[0].predicted_net_flow_cents == 50000
    # 15% of (100,000 + 50,000) = 22,500
    assert res.points[0].supplied_uncertainty_buffer_cents == 22500


def test_full_downloads_dataset_if_present():
    dataset_path = Path(r"C:\Users\Arvind Shekhawat\Downloads\treasury_4tier_dataset.csv")
    if not dataset_path.exists():
        pytest.skip("Downloads dataset not found on this machine")

    # Load 720 hours (30 days) and run 24h seasonal naive forecast
    observations = load_organizer_dataset(dataset_path, limit=720)
    assert len(observations) == 720

    as_of = observations[-1].timestamp
    res = forecast_hourly_cashflows(observations, as_of=as_of, horizon_hours=24)
    assert len(res.points) == 24
    assert res.points[0].predicted_deposits_cents > 0
    assert res.points[0].predicted_withdrawals_cents > 0
    assert res.points[0].supplied_uncertainty_buffer_cents > 0


def test_seasonal_forecast_explicit_current_hour_alignment(hourly_series_168):
    history = hourly_series_168[:50]
    as_of = history[-1].timestamp
    result = hourly_seasonal_naive_forecast(history, as_of=as_of, start_at=as_of, horizon_hours=1)
    assert result.points[0].predicted_deposits_cents == int(history[25].deposits_usd * 100)
    with pytest.raises(ValueError, match='contiguous'):
        hourly_seasonal_naive_forecast(history[:25] + history[26:], as_of=as_of, horizon_hours=1)
