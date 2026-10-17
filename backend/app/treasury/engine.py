from datetime import datetime
from typing import Dict, Any

class TreasuryDecisionEngine:
    """
    Quantitative Treasury Decision Engine.
    Evaluates liquidity state, near-term forecast, and uncertainty corridors
    to recommend HOLD, SWEEP, WITHDRAW, or LIQUIDITY_WARNING.
    """
    def __init__(
        self,
        base_safety_buffer: float = 50000.00,
        uncertainty_multiplier: float = 1.96,
        min_sweep_threshold: float = 10000.00,
        tolerance_band: float = 0.05
    ):
        self.base_safety_buffer = base_safety_buffer
        self.uncertainty_multiplier = uncertainty_multiplier
        self.min_sweep_threshold = min_sweep_threshold
        self.tolerance_band = tolerance_band

    def calculate_required_reserve(
        self,
        predicted_outflow: float,
        predicted_inflow: float,
        uncertainty: float
    ) -> float:
        """
        Expected Liquidity Requirement + Forecast Uncertainty + Operational Safety Buffer = Recommended Liquid Reserve
        """
        net_drain = max(0.0, predicted_outflow - predicted_inflow)
        uncertainty_buffer = self.uncertainty_multiplier * max(0.0, uncertainty)
        required_reserve = net_drain + uncertainty_buffer + self.base_safety_buffer
        return round(required_reserve, 2)

    def evaluate_decision(
        self,
        checking_balance: float,
        vault_balance: float,
        predicted_outflow: float,
        predicted_inflow: float,
        uncertainty: float
    ) -> Dict[str, Any]:
        """
        Calculates deployable cash and determines optimal liquidity action.
        """
        required_reserve = self.calculate_required_reserve(
            predicted_outflow=predicted_outflow,
            predicted_inflow=predicted_inflow,
            uncertainty=uncertainty
        )
        
        deployable_cash = round(checking_balance - required_reserve, 2)
        total_liquidity = round(checking_balance + vault_balance, 2)
        forecast_net = round(predicted_inflow - predicted_outflow, 2)
        
        # 1. Extreme stress: Consolidated checking + vault cannot meet required reserve
        if total_liquidity < required_reserve:
            shortfall = round(required_reserve - total_liquidity, 2)
            emergency_amount = min(vault_balance, round(required_reserve - checking_balance, 2)) if vault_balance > 0 else 0.0
            return {
                "decision_type": "LIQUIDITY_WARNING",
                "amount": emergency_amount,
                "required_reserve": required_reserve,
                "deployable_cash": deployable_cash,
                "forecast_value": forecast_net,
                "forecast_uncertainty": uncertainty,
                "safety_buffer": self.base_safety_buffer,
                "reason": (
                    f"CRITICAL: Total liquidity (${total_liquidity:,.2f}) falls short of "
                    f"required reserve (${required_reserve:,.2f}) by ${shortfall:,.2f}. "
                    "Emergency liquidation and liquidity alert active."
                )
            }

        # 2. Deficit: Checking is below required reserve, but vault can cover
        if checking_balance < required_reserve:
            deficit = round(required_reserve - checking_balance, 2)
            withdraw_amount = min(vault_balance, deficit)
            return {
                "decision_type": "WITHDRAW",
                "amount": withdraw_amount,
                "required_reserve": required_reserve,
                "deployable_cash": deployable_cash,
                "forecast_value": forecast_net,
                "forecast_uncertainty": uncertainty,
                "safety_buffer": self.base_safety_buffer,
                "reason": (
                    f"Checking balance (${checking_balance:,.2f}) is below required reserve "
                    f"(${required_reserve:,.2f}). Withdrawing ${withdraw_amount:,.2f} from yield vault."
                )
            }

        # 3. Excess: Checking significantly exceeds required reserve beyond tolerance band
        upper_bound = required_reserve * (1.0 + self.tolerance_band)
        if checking_balance > upper_bound and deployable_cash >= self.min_sweep_threshold:
            sweep_amount = deployable_cash
            return {
                "decision_type": "SWEEP",
                "amount": sweep_amount,
                "required_reserve": required_reserve,
                "deployable_cash": deployable_cash,
                "forecast_value": forecast_net,
                "forecast_uncertainty": uncertainty,
                "safety_buffer": self.base_safety_buffer,
                "reason": (
                    f"Checking balance (${checking_balance:,.2f}) exceeds reserve target "
                    f"(${required_reserve:,.2f}) + tolerance corridor. "
                    f"Sweeping ${sweep_amount:,.2f} idle cash to yield vault."
                )
            }

        # 4. Equilibrium corridor: Checking balance is balanced
        return {
            "decision_type": "HOLD",
            "amount": 0.0,
            "required_reserve": required_reserve,
            "deployable_cash": deployable_cash,
            "forecast_value": forecast_net,
            "forecast_uncertainty": uncertainty,
            "safety_buffer": self.base_safety_buffer,
            "reason": (
                f"Checking balance (${checking_balance:,.2f}) operates within risk-neutral "
                f"corridor of required reserve (${required_reserve:,.2f}). Maintaining current balance."
            )
        }
