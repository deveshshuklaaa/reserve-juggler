import pytest
from simulation.generator import TransactionGenerator

def test_generator_baseline_event():
    gen = TransactionGenerator(scenario="baseline")
    event = gen.generate_event()
    assert event["scenario"] == "baseline"
    assert event["type"] in ["DEPOSIT", "WITHDRAWAL", "MERCHANT_SETTLEMENT"]
    assert event["amount"] > 0

def test_generator_payroll_spike():
    gen = TransactionGenerator(scenario="payroll_spike")
    events = [gen.generate_event() for _ in range(20)]
    deposit_count = sum(1 for e in events if e["type"] == "DEPOSIT")
    assert deposit_count > 0

def test_generator_deposit_run():
    gen = TransactionGenerator(scenario="deposit_run")
    events = [gen.generate_event() for _ in range(20)]
    withdrawal_count = sum(1 for e in events if e["type"] == "WITHDRAWAL")
    assert withdrawal_count > 0
