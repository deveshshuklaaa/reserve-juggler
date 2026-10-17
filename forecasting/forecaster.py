from typing import List, Dict, Any
from datetime import datetime, timedelta

class CashFlowForecaster:
    """
    Rolling window flow forecaster with uncertainty estimation.
    Estimates expected inflows, outflows, and net drain variance.
    """
    def __init__(self, default_horizon_minutes: int = 60, model_version: str = "v0.1-quantile-baseline"):
        self.default_horizon_minutes = default_horizon_minutes
        self.model_version = model_version

    def forecast_flows(self, recent_transactions: List[Dict[str, Any]] = None, horizon_minutes: int = None) -> Dict[str, Any]:
        horizon = horizon_minutes or self.default_horizon_minutes
        
        # If no transactions or sparse history, return baseline conservative estimates
        if not recent_transactions:
            return {
                "timestamp": datetime.utcnow().isoformat(),
                "horizon_minutes": horizon,
                "predicted_inflow": 220000.00,
                "predicted_outflow": 180000.00,
                "predicted_net_flow": 40000.00,
                "uncertainty": 25000.00,
                "model_version": self.model_version
            }

        # Calculate empirical moving window inflows and outflows
        inflows = sum(t["amount"] for t in recent_transactions if t.get("type") in ["DEPOSIT", "MERCHANT_SETTLEMENT"])
        outflows = sum(t["amount"] for t in recent_transactions if t.get("type") == "WITHDRAWAL")
        
        # Scale to horizon
        count = len(recent_transactions)
        scale = max(1.0, float(horizon) / max(1.0, count * 5.0))
        predicted_in = round(inflows * scale, 2)
        predicted_out = round(outflows * scale, 2)
        predicted_net = round(predicted_in - predicted_out, 2)
        
        # Conservative uncertainty: 15% of total flow volume
        uncertainty = round((predicted_in + predicted_out) * 0.15, 2)

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "horizon_minutes": horizon,
            "predicted_inflow": predicted_in,
            "predicted_outflow": predicted_out,
            "predicted_net_flow": predicted_net,
            "uncertainty": uncertainty,
            "model_version": self.model_version
        }
