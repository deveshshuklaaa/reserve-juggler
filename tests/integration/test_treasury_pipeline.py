import pytest
from simulation.generator import TransactionGenerator
from forecasting.forecaster import CashFlowForecaster
from app.treasury.engine import TreasuryDecisionEngine

def test_end_to_end_pipeline():
    # 1. Simulate transactions
    gen = TransactionGenerator(scenario="baseline")
    stream = [gen.generate_event() for _ in range(10)]
    
    # 2. Forecast cash flows
    forecaster = CashFlowForecaster(default_horizon_minutes=60)
    forecast = forecaster.forecast_flows(recent_transactions=stream)
    
    # 3. Compute decision
    engine = TreasuryDecisionEngine(base_safety_buffer=50000.0)
    decision = engine.evaluate_decision(
        checking_balance=600000.0,
        vault_balance=2000000.0,
        predicted_outflow=forecast["predicted_outflow"],
        predicted_inflow=forecast["predicted_inflow"],
        uncertainty=forecast["uncertainty"]
    )
    
    # 4. Verify output contracts
    assert decision["decision_type"] in ["HOLD", "SWEEP", "WITHDRAW", "LIQUIDITY_WARNING"]
    assert decision["required_reserve"] > 0
    assert "reason" in decision
