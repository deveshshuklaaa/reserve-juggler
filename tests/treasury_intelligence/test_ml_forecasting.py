"""Tests for hourly machine-learning forecasting and chronological evaluation (RJ-M1-09)."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import math
from pathlib import Path

import pytest
from pydantic import ValidationError

from treasury_intelligence import (
    HourlyCashFlowBucket,
    HourlyCashFlowMLModel,
    HourlyForecastConfig,
    HourlyForecastResult,
    HourlyModelEvaluationReport,
    OrganizerHourlyObservation,
    SUPPORTED_HOURLY_HORIZONS,
    SUPPORTED_ML_ALGORITHMS,
    evaluate_hourly_forecast_models,
    forecast_hourly_cashflows,
    hourly_ml_forecast,
    load_organizer_dataset,
)
from treasury_intelligence.ml_forecasting import (
    ML_FEATURE_NAMES,
    extract_ml_features_for_step,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def hourly_series_168() -> tuple[OrganizerHourlyObservation, ...]:
    """168 contiguous real hourly observations from the organizer dataset fixture."""
    fixture_path = FIXTURES_DIR / "organizer_hourly_series.json"
    data = json.loads(fixture_path.read_text(encoding="utf-8"))
    return tuple(OrganizerHourlyObservation.model_validate(r) for r in data)


# ---------------------------------------------------------------------------
# 1. Causal Feature Timing and Market Data Visibility
# ---------------------------------------------------------------------------

def test_extract_ml_features_timing_and_no_lookahead(hourly_series_168):
    obs = hourly_series_168[:50]
    as_of = obs[40].timestamp  # Decision time: observation index 40

    # For step h=3: target hour is as_of + 3h (equivalent to index 43 if realized)
    feats = extract_ml_features_for_step(obs[:41], as_of, step_h=3)
    assert len(feats) == len(ML_FEATURE_NAMES)

    target_dt = as_of + timedelta(hours=3)
    assert feats[0] == 3.0  # forecast_step
    assert feats[1] == float(target_dt.hour)  # target_hour
    assert feats[2] == float(target_dt.weekday())  # target_day_of_week

    # Verify seasonal naive feature at target hour (as_of + 3h - 24h = as_of - 21h = index 40 - 21 = index 19)
    # This was observed 21 hours before as_of, strictly in the past!
    expected_sn_dep = float(obs[19].deposits_usd)
    assert feats[8] == expected_sn_dep  # seasonal_naive_dep_usd

    # Verify as_of cash flows match index 40
    assert feats[12] == float(obs[40].deposits_usd)  # as_of_dep_usd
    assert feats[13] == float(obs[40].withdrawals_usd)  # as_of_wtd_usd

    # Verify market quotes match index 40 (decision cutoff)
    assert feats[20] == float(obs[40].tier1_repo_rate_apy)
    assert feats[21] == float(obs[40].tier2_bond_yield_pct)


def test_market_data_visibility_isolated_at_as_of(hourly_series_168):
    # If market data changes in the future (e.g. index 45), as_of at index 40 must NOT see it
    obs = list(hourly_series_168[:50])
    as_of = obs[40].timestamp

    # Modify future observation at index 45 with extreme rate
    mutated_future = obs[45].model_dump()
    mutated_future["tier1_repo_rate_apy"] = "99.999"
    obs[45] = OrganizerHourlyObservation.model_validate(mutated_future)

    feats = extract_ml_features_for_step(obs[:41], as_of, step_h=5)
    # Must reflect rate at index 40, NOT 99.999
    assert feats[20] == float(obs[40].tier1_repo_rate_apy)
    assert feats[20] != 99.999


# ---------------------------------------------------------------------------
# 2. Model Training, Horizons, and Non-Negativity
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("algorithm", ["hist_gradient_boosting", "random_forest"])
def test_ml_model_fit_and_supported_horizons(hourly_series_168, algorithm):
    # Train on first 140 hours, test on remaining
    train_history = hourly_series_168[:140]
    test_history = hourly_series_168[:150]
    as_of = test_history[140].timestamp

    model = HourlyCashFlowMLModel(algorithm=algorithm, random_state=42)
    assert not model.is_fitted
    model.fit(train_history, stride=2, horizons=(1, 3, 6, 15, 24))
    assert model.is_fitted
    assert model.train_sample_count > 0
    assert model.training_cutoff == train_history[-1].timestamp

    for H in (1, 3, 6, 15, 24):
        pred_d, pred_w, unc = model.predict_path(test_history[:141], as_of, horizon_hours=H)
        assert len(pred_d) == H
        assert len(pred_w) == H
        assert all(d >= 0 for d in pred_d)
        assert all(w >= 0 for w in pred_w)
        assert unc >= 0


def test_hourly_ml_forecast_result_contract(hourly_series_168):
    train_history = hourly_series_168[:140]
    as_of = hourly_series_168[140].timestamp

    model = HourlyCashFlowMLModel(algorithm="hist_gradient_boosting", random_state=42)
    model.fit(train_history, stride=3)

    res = hourly_ml_forecast(
        hourly_series_168[:141],
        as_of=as_of,
        horizon_hours=15,
        ml_model=model,
        model_version="hourly-hist-gb-v1",
    )
    assert isinstance(res, HourlyForecastResult)
    assert res.resolution == "1h"
    assert res.horizon_hours == 15
    assert len(res.points) == 15
    assert res.generated_at == as_of
    assert res.points[0].start_at == as_of + timedelta(hours=1)
    assert res.points[-1].start_at == as_of + timedelta(hours=15)

    # Invariants
    for pt in res.points:
        assert pt.predicted_deposits_cents >= 0
        assert pt.predicted_withdrawals_cents >= 0
        assert pt.predicted_net_flow_cents == pt.predicted_deposits_cents - pt.predicted_withdrawals_cents
        assert pt.supplied_uncertainty_buffer_cents >= 0


# ---------------------------------------------------------------------------
# 3. Seed Reproducibility and Model Persistence
# ---------------------------------------------------------------------------

def test_ml_seed_reproducibility(hourly_series_168):
    train_data = hourly_series_168[:140]
    as_of = train_data[-1].timestamp

    m1 = HourlyCashFlowMLModel(algorithm="hist_gradient_boosting", random_state=123).fit(train_data, stride=3)
    m2 = HourlyCashFlowMLModel(algorithm="hist_gradient_boosting", random_state=123).fit(train_data, stride=3)

    p1_d, p1_w, u1 = m1.predict_path(train_data, as_of, horizon_hours=12)
    p2_d, p2_w, u2 = m2.predict_path(train_data, as_of, horizon_hours=12)

    assert p1_d == p2_d
    assert p1_w == p2_w
    assert u1 == u2


def test_ml_model_save_and_load(hourly_series_168, tmp_path):
    train_data = hourly_series_168[:140]
    as_of = train_data[-1].timestamp

    model = HourlyCashFlowMLModel(algorithm="hist_gradient_boosting", random_state=42).fit(train_data, stride=3)
    p_orig = model.predict_path(train_data, as_of, horizon_hours=6)

    save_file = tmp_path / "model.pkl"
    model.save(save_file)

    loaded = HourlyCashFlowMLModel.load(save_file)
    assert loaded.is_fitted
    assert loaded.algorithm == model.algorithm
    assert loaded.training_cutoff == model.training_cutoff

    p_loaded = loaded.predict_path(train_data, as_of, horizon_hours=6)
    assert p_orig == p_loaded


# ---------------------------------------------------------------------------
# 4. Safe Baseline Fallback
# ---------------------------------------------------------------------------

def test_ml_forecast_fallback_when_untrained(hourly_series_168):
    history = hourly_series_168[:30]
    as_of = history[-1].timestamp

    # Unfitted model
    unfitted_model = HourlyCashFlowMLModel(algorithm="hist_gradient_boosting")
    res = hourly_ml_forecast(history, as_of=as_of, horizon_hours=6, ml_model=unfitted_model)
    assert isinstance(res, HourlyForecastResult)
    assert len(res.points) == 6
    assert any("fell back to baseline" in note for note in res.metadata.notes)


def test_ml_forecast_fallback_when_none_model(hourly_series_168):
    history = hourly_series_168[:30]
    as_of = history[-1].timestamp

    res = hourly_ml_forecast(history, as_of=as_of, horizon_hours=6, ml_model=None)
    assert isinstance(res, HourlyForecastResult)
    assert len(res.points) == 6
    assert any("fell back to baseline" in note for note in res.metadata.notes)


def test_ml_forecast_fallback_when_insufficient_history():
    as_of = datetime(2026, 1, 1, 10, 0, 0)
    # Only 5 observations (< 24h)
    history = [
        HourlyCashFlowBucket(
            timestamp=as_of - timedelta(hours=i),
            deposits_usd="1000.00",
            withdrawals_usd="500.00",
            net_flow_usd="500.00",
        )
        for i in reversed(range(5))
    ]
    res = hourly_ml_forecast(history, as_of=as_of, horizon_hours=3, ml_model=None)
    assert len(res.points) == 3
    assert all(pt.predicted_deposits_cents > 0 for pt in res.points)


# ---------------------------------------------------------------------------
# 5. Unified Integration via forecast_hourly_cashflows
# ---------------------------------------------------------------------------

def test_forecast_hourly_cashflows_with_ml_model(hourly_series_168):
    train_data = hourly_series_168[:140]
    test_data = hourly_series_168[:145]
    as_of = test_data[-1].timestamp

    model = HourlyCashFlowMLModel(algorithm="hist_gradient_boosting", random_state=42).fit(train_data, stride=3)

    # Via direct ml_model parameter
    res1 = forecast_hourly_cashflows(test_data, as_of=as_of, horizon_hours=6, ml_model=model)
    assert isinstance(res1, HourlyForecastResult)
    assert len(res1.points) == 6

    # Via HourlyForecastConfig
    cfg = HourlyForecastConfig(
        resolution="1h",
        horizon_hours=15,
        model_version="hourly-hist-gb-v1",
        ml_model=model,
    )
    res2 = forecast_hourly_cashflows(test_data, as_of=as_of, config=cfg)
    assert len(res2.points) == 15
    assert res2.model_version == "hourly-hist-gb-v1"


# ---------------------------------------------------------------------------
# 6. Evaluation Framework & Chronological Report
# ---------------------------------------------------------------------------

def test_chronological_evaluation_framework_metrics(hourly_series_168):
    # Repeat series to have at least 240 observations for evaluation partition
    last_ts = hourly_series_168[-1].timestamp
    additional = [
        obs.model_copy(update={"timestamp": last_ts + timedelta(hours=i + 1)})
        for i, obs in enumerate(hourly_series_168[:80])
    ]
    extended_series = hourly_series_168 + tuple(additional)
    assert len(extended_series) == 248

    reports = evaluate_hourly_forecast_models(
        extended_series,
        horizons=(1, 6),
        train_ratio=0.60,
        val_ratio=0.20,
        eval_stride=12,
        algorithms=("hist_gradient_boosting",),
        random_state=42,
    )
    assert len(reports) == 2
    r_1h = next(r for r in reports if r.horizon_hours == 1)
    r_6h = next(r for r in reports if r.horizon_hours == 6)

    # Check boundaries: strictly chronological
    assert r_1h.train_cutoff < r_1h.test_start <= r_1h.test_end
    assert r_1h.test_sample_count > 0
    assert r_1h.train_sample_count > 0

    # Check metrics
    assert r_1h.mae_deposits_usd >= 0
    assert r_1h.mae_withdrawals_usd >= 0
    assert r_1h.mae_net_usd >= 0
    assert r_1h.rmse_net_usd >= 0
    assert r_1h.cumulative_net_mae_usd >= 0
    assert r_1h.peak_shortfall_mae_usd >= 0

    assert r_1h.baseline_mae_net_usd > 0
    assert r_1h.baseline_rmse_net_usd > 0

    # Improvements are reported without modification
    assert isinstance(r_1h.net_mae_improvement_pct, Decimal)
    assert isinstance(r_1h.net_rmse_improvement_pct, Decimal)


def test_comparison_of_two_lightweight_models(hourly_series_168):
    last_ts = hourly_series_168[-1].timestamp
    additional = [
        obs.model_copy(update={"timestamp": last_ts + timedelta(hours=i + 1)})
        for i, obs in enumerate(hourly_series_168[:80])
    ]
    extended_series = hourly_series_168 + tuple(additional)
    reports = evaluate_hourly_forecast_models(
        extended_series,
        horizons=(6,),
        train_ratio=0.60,
        val_ratio=0.20,
        eval_stride=12,
        algorithms=("hist_gradient_boosting", "random_forest"),
        random_state=42,
    )
    assert len(reports) == 2
    algorithms_evaluated = {r.algorithm for r in reports}
    assert algorithms_evaluated == {"hist_gradient_boosting", "random_forest"}


def test_full_dataset_ml_evaluation_if_present():
    dataset_path = Path(r"C:\Users\Arvind Shekhawat\Downloads\treasury_4tier_dataset.csv")
    if not dataset_path.exists():
        pytest.skip("Downloads dataset not found on this machine")

    # Load 1000 hours and evaluate across horizons
    observations = load_organizer_dataset(dataset_path, limit=1000)
    reports = evaluate_hourly_forecast_models(
        observations,
        horizons=(1, 15, 24),
        train_ratio=0.70,
        val_ratio=0.15,
        eval_stride=24,
        algorithms=("hist_gradient_boosting",),
        random_state=42,
    )
    assert len(reports) == 3
    for r in reports:
        # Verify valid positive sample counts and positive metrics
        assert r.test_sample_count > 0
        assert r.mae_net_usd > 0
        assert r.cumulative_net_mae_usd > 0
        assert r.peak_shortfall_mae_usd > 0


def test_fitted_artifact_cannot_be_used_before_calibration_cutoff(hourly_series_168):
    model = HourlyCashFlowMLModel().fit(hourly_series_168[:80],
        validation_history=hourly_series_168[80:120], stride=24, horizons=(1,))
    assert model.training_cutoff == hourly_series_168[119].timestamp
    with pytest.raises(ValueError, match='cutoff'):
        model.predict_path(hourly_series_168[:100], hourly_series_168[99].timestamp, 1)
    with pytest.raises(ValueError, match='start_at'):
        model.predict_path(hourly_series_168[:120], hourly_series_168[119].timestamp, 1,
                           start_at=hourly_series_168[118].timestamp)


def test_ml_seasonal_feature_uses_explicit_target_timestamp(hourly_series_168):
    history = hourly_series_168[:50]
    as_of = history[-1].timestamp
    features = extract_ml_features_for_step(history, as_of, step_h=1, start_at=as_of)
    assert features[8] == float(history[25].deposits_usd)
    with pytest.raises(ValueError, match='causality'):
        extract_ml_features_for_step(hourly_series_168, as_of, step_h=1)
