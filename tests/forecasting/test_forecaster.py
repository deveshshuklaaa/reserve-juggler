import pytest
from forecasting.forecaster import CashFlowForecaster

def test_forecaster_baseline():
    forecaster = CashFlowForecaster(default_horizon_minutes=60)
    fc = forecaster.forecast_flows()
    assert fc["horizon_minutes"] == 60
    assert fc["predicted_inflow"] > 0
    assert fc["predicted_outflow"] > 0
    assert fc["uncertainty"] > 0

def test_forecaster_with_transactions():
    forecaster = CashFlowForecaster(default_horizon_minutes=30)
    txs = [
        {"type": "DEPOSIT", "amount": 100000.0},
        {"type": "WITHDRAWAL", "amount": 40000.0},
        {"type": "MERCHANT_SETTLEMENT", "amount": 25000.0}
    ]
    fc = forecaster.forecast_flows(recent_transactions=txs, horizon_minutes=30)
    assert fc["predicted_inflow"] > 0
    assert fc["predicted_outflow"] > 0
    assert fc["uncertainty"] > 0
