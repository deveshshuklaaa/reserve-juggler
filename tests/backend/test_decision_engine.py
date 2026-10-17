import pytest
from app.treasury.engine import TreasuryDecisionEngine

def test_required_reserve_calculation():
    engine = TreasuryDecisionEngine(base_safety_buffer=50000.0, uncertainty_multiplier=1.96)
    # Drain = 100000 - 40000 = 60000. Uncertainty = 1.96 * 10000 = 19600. Safety = 50000
    # Expected reserve = 60000 + 19600 + 50000 = 129600
    reserve = engine.calculate_required_reserve(
        predicted_outflow=100000.0,
        predicted_inflow=40000.0,
        uncertainty=10000.0
    )
    assert reserve == 129600.0

def test_sweep_decision_on_excess_cash():
    engine = TreasuryDecisionEngine(base_safety_buffer=50000.0, min_sweep_threshold=10000.0)
    decision = engine.evaluate_decision(
        checking_balance=500000.0,
        vault_balance=1000000.0,
        predicted_outflow=100000.0,
        predicted_inflow=50000.0,
        uncertainty=10000.0
    )
    assert decision["decision_type"] == "SWEEP"
    assert decision["amount"] > 0

def test_withdraw_decision_on_liquidity_deficit():
    engine = TreasuryDecisionEngine(base_safety_buffer=50000.0)
    decision = engine.evaluate_decision(
        checking_balance=50000.0,
        vault_balance=1000000.0,
        predicted_outflow=150000.0,
        predicted_inflow=20000.0,
        uncertainty=15000.0
    )
    assert decision["decision_type"] == "WITHDRAW"
    assert decision["amount"] > 0

def test_liquidity_warning_on_extreme_insolvency():
    engine = TreasuryDecisionEngine(base_safety_buffer=100000.0)
    decision = engine.evaluate_decision(
        checking_balance=10000.0,
        vault_balance=20000.0,
        predicted_outflow=300000.0,
        predicted_inflow=10000.0,
        uncertainty=50000.0
    )
    assert decision["decision_type"] == "LIQUIDITY_WARNING"

def test_hold_decision_in_corridor():
    engine = TreasuryDecisionEngine(base_safety_buffer=50000.0, tolerance_band=0.10)
    # Reserve = (100000 - 100000) + (1.96 * 0) + 50000 = 50000. Checking = 52000
    decision = engine.evaluate_decision(
        checking_balance=52000.0,
        vault_balance=500000.0,
        predicted_outflow=100000.0,
        predicted_inflow=100000.0,
        uncertainty=0.0
    )
    assert decision["decision_type"] == "HOLD"
    assert decision["amount"] == 0.0
