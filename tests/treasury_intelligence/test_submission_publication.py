"""Submission gate: actual fitted artifacts obey completed-hour publication."""
import pickle
from datetime import timedelta
import pytest
from test_ml_forecasting import hourly_series_168
from treasury_intelligence.hourly_forecasting import forecast_hourly_cashflows, HourlyForecastConfig
from treasury_intelligence.ml_forecasting import HourlyCashFlowMLModel, hourly_ml_forecast


@pytest.mark.parametrize("delay", [0, 3600])
@pytest.mark.parametrize("entry", ["public", "ml", "config"])
def test_public_artifact_admission_includes_calibration_publication(hourly_series_168, delay, entry):
    observations = hourly_series_168
    model = HourlyCashFlowMLModel().fit(observations[:80],
        validation_history=observations[80:120], stride=24, horizons=(1,))
    model = HourlyCashFlowMLModel.from_bytes(model.to_bytes())
    assert model.training_cutoff == observations[119].timestamp
    available = model.training_cutoff+timedelta(hours=1, seconds=delay)
    def call(at, artifact=model):
        history = tuple(o for o in observations if o.timestamp+timedelta(hours=1, seconds=delay) <= at)
        kwargs = dict(as_of=at, horizon_hours=1, publication_delay_seconds=delay)
        if entry == "ml":
            return hourly_ml_forecast(history, ml_model=artifact, **kwargs)
        if entry == "config":
            return forecast_hourly_cashflows(history,
                config=HourlyForecastConfig(horizon_hours=1, ml_model=artifact), **kwargs)
        return forecast_hourly_cashflows(history, ml_model=artifact, **kwargs)
    with pytest.raises(ValueError, match="publication cutoff"):
        call(available-timedelta(hours=1))
    accepted = call(available)
    assert accepted.metadata.training_data_through == observations[119].timestamp
    assert len(accepted.points) == 1
    state = pickle.loads(model.to_bytes())  # trusted, locally generated test data
    del state["cutoff_includes_calibration"]
    legacy = HourlyCashFlowMLModel.from_bytes(pickle.dumps(state))
    with pytest.raises(ValueError, match="provenance"):
        call(available, legacy)


@pytest.mark.parametrize("delay", [-1, True, 0.5, 2147483648])
def test_invalid_publication_delay_rejected(hourly_series_168, delay):
    with pytest.raises(ValueError, match="publication_delay"):
        hourly_ml_forecast(hourly_series_168[:30], as_of=hourly_series_168[30].timestamp,
            publication_delay_seconds=delay)


@pytest.mark.parametrize("days", [0, 1, 8, 7.0, True, "7"])
def test_invalid_backtest_days_rejected(days):
    from app.v1_contracts import BacktestRequest
    with pytest.raises(ValueError, match="days"):
        BacktestRequest(days=days)


@pytest.mark.parametrize("days", [7, 14, 30])
def test_supported_backtest_days_preserve_frontend_aliases(days):
    from app.v1_contracts import BacktestRequest
    request = BacktestRequest(days=days, strategies=["STATIC", "REACTIVE", "RESERVE_JUGGLER"])
    assert request.days == days
    assert request.strategies == ["STATIC_RESERVE", "REACTIVE_RESERVE", "RESERVE_JUGGLER"]

