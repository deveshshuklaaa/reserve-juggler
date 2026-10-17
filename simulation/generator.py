import random
from datetime import datetime
from typing import Dict, Any

class TransactionGenerator:
    """
    Synthetic Transaction Generator for HackForge 2026.
    Generates realistic banking transaction events across multiple stress scenarios.
    """
    SCENARIOS = ["baseline", "payroll_spike", "deposit_run", "high_volatility"]

    def __init__(self, scenario: str = "baseline"):
        self.scenario = scenario if scenario in self.SCENARIOS else "baseline"

    def set_scenario(self, scenario: str):
        if scenario in self.SCENARIOS:
            self.scenario = scenario

    def generate_event(self) -> Dict[str, Any]:
        """
        Generates a single synthetic transaction according to active scenario dynamics.
        """
        now = datetime.utcnow()
        if self.scenario == "payroll_spike":
            # Significant influx of corporate deposits
            tx_type = random.choices(["DEPOSIT", "WITHDRAWAL", "MERCHANT_SETTLEMENT"], weights=[0.75, 0.15, 0.10])[0]
            amount = round(random.uniform(50000.0, 350000.0), 2) if tx_type == "DEPOSIT" else round(random.uniform(5000.0, 45000.0), 2)
            source = "corporate_payroll_ach"
        elif self.scenario == "deposit_run":
            # High outflow pressure: heavy client withdrawals
            tx_type = random.choices(["WITHDRAWAL", "DEPOSIT", "MERCHANT_SETTLEMENT"], weights=[0.80, 0.10, 0.10])[0]
            amount = round(random.uniform(100000.0, 500000.0), 2) if tx_type == "WITHDRAWAL" else round(random.uniform(10000.0, 50000.0), 2)
            source = "urgent_wire_liquidation"
        elif self.scenario == "high_volatility":
            # Unpredictable large swings in both directions
            tx_type = random.choice(["DEPOSIT", "WITHDRAWAL", "MERCHANT_SETTLEMENT"])
            amount = round(random.uniform(80000.0, 600000.0), 2)
            source = "institutional_clearing"
        else: # baseline
            tx_type = random.choices(["DEPOSIT", "WITHDRAWAL", "MERCHANT_SETTLEMENT"], weights=[0.45, 0.40, 0.15])[0]
            amount = round(random.uniform(15000.0, 120000.0), 2)
            source = "retail_clearing_network"

        return {
            "timestamp": now.isoformat(),
            "type": tx_type,
            "amount": amount,
            "source": source,
            "scenario": self.scenario
        }
