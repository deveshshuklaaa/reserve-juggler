"""Pure Python end-to-end Treasury Intelligence Pipeline.

Connects:
Historical Cash Flows
  → Baseline Forecast
  → Supplied Provisional Uncertainty Policy
  → Required Reserve
  → Treasury Recommendation
  → Expected Economic Result
  → Structured Explanation
"""
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Literal

from .api import forecast_cashflows
from .policy import recommend_treasury_action, TreasuryDecisionPolicy
from .reserve import calculate_required_reserve
from .types import (
    CashFlowBucket,
    Contract,
    DecisionResult,
    ForecastResult,
    Name,
    ReserveResult,
    TreasuryContext,
    TreasuryPolicy,
)


class TreasuryPipelineResult(Contract):
    """Immutable result of a single treasury pipeline evaluation."""
    scenario_name: Name
    context: TreasuryContext
    forecast: ForecastResult
    policy: TreasuryDecisionPolicy | TreasuryPolicy
    reserve: ReserveResult
    decision: DecisionResult
    uncertainty_status: Literal["provisional_uncalibrated"] = "provisional_uncalibrated"
    uncertainty_note: Name = (
        "Provisional uncalibrated uncertainty policy; not validated against empirical model evaluation."
    )
    executed_at: datetime


def run_treasury_pipeline(
    scenario_name: str,
    history: Sequence[CashFlowBucket],
    context: TreasuryContext,
    policy: TreasuryPolicy | TreasuryDecisionPolicy,
    *,
    horizon_minutes: int = 60,
    bucket_minutes: int = 15,
    model_version: str = "baseline-v1",
    forecast: ForecastResult | None = None,
) -> TreasuryPipelineResult:
    """
    Execute the standalone quantitative treasury pipeline.
    
    1. If forecast is not supplied, generates baseline forecast from historical cash flows.
    2. Calculates the required liquid reserve based on pathwise peak shortfall and policy buffers.
    3. Evaluates capital allocation and issues an explainable decision (HOLD, SWEEP, WITHDRAW, LIQUIDITY_WARNING).
    4. Evaluates expected economics (modeled yield, penalties, net economic benefit).
    5. Returns an immutable, validated TreasuryPipelineResult.
    """
    if context.as_of.tzinfo is None or context.as_of.tzinfo.utcoffset(context.as_of) != timezone.utc.utcoffset(context.as_of):
        raise ValueError("context.as_of must be timezone-aware UTC")

    # Step 1: Forecast cash flows (or use supplied forecast)
    if forecast is None:
        fc = forecast_cashflows(
            history,
            as_of=context.as_of,
            horizon_minutes=horizon_minutes,
            bucket_minutes=bucket_minutes,
            model_version=model_version,
        )
    else:
        if forecast.generated_at != context.as_of:
            raise ValueError("supplied forecast generated_at must match context.as_of")
        fc = forecast

    # Step 2: Compute required reserve
    reserve = calculate_required_reserve(fc, policy)

    # Step 3: Recommend treasury action & economic outcomes
    decision = recommend_treasury_action(context, fc, policy)

    return TreasuryPipelineResult(
        scenario_name=scenario_name,
        context=context,
        forecast=fc,
        policy=policy,
        reserve=reserve,
        decision=decision,
        executed_at=context.as_of,
    )
