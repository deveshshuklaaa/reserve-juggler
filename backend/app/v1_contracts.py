"""Member 2 public data contracts. No forecasting or accounting implementation."""

from datetime import datetime, timezone
from enum import Enum
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


Cents = Annotated[int, Field(strict=True, ge=0, le=9223372036854775807)]
PositiveCents = Annotated[int, Field(strict=True, gt=0, le=9223372036854775807)]
Step = Annotated[int, Field(strict=True, ge=0)]
PositiveSteps = Annotated[int, Field(strict=True, gt=0)]
BasisPoints = Annotated[int, Field(strict=True, ge=0, le=10000)]


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    @field_validator("*", mode="after")
    @classmethod
    def require_utc(cls, value):
        if isinstance(value, datetime):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("A timezone-aware timestamp is required")
            return value.astimezone(timezone.utc)
        return value


class Scenario(str, Enum):
    NORMAL = "NORMAL"
    HIGH_WITHDRAWAL = "HIGH_WITHDRAWAL"
    LOW_DEPOSIT = "LOW_DEPOSIT"
    SETTLEMENT_DELAY = "SETTLEMENT_DELAY"
    LIQUIDITY_SHOCK = "LIQUIDITY_SHOCK"


class TreasuryPolicy(ContractModel):
    risk_percentile: float = Field(default=0.95, gt=0, lt=1, allow_inf_nan=False)
    operational_buffer_cents: Cents = 50000000
    minimum_sweep_cents: Cents = 1000000
    vault_yield_bps: BasisPoints = 500
    vault_lock_steps: PositiveSteps = 96
    early_redemption_allowed: bool = True
    early_redemption_penalty_bps: BasisPoints = 200


class CreateRunRequest(ContractModel):
    initial_cash_cents: Cents = 2000000000
    duration_steps: PositiveSteps = 288
    seed: int = Field(default=42, strict=True, ge=0, le=2147483647)
    scenario: Scenario = Scenario.NORMAL
    start_time: datetime | None = None
    policy: TreasuryPolicy = Field(default_factory=TreasuryPolicy)


class RunCreated(ContractModel):
    run_id: UUID
    status: Literal["READY"]
    current_step: Step
    checking_cents: Cents
    vault_locked_cents: Cents


class AdvanceRequest(ContractModel):
    expected_step: Step
    steps: PositiveSteps = 1


class ScenarioRequest(ContractModel):
    scenario: Scenario
    # Scenario-specific parameter validation is deferred until those contracts freeze.
    parameters: dict[str, Any] = Field(default_factory=dict)


class ScenarioApplied(ContractModel):
    run_id: UUID
    scenario: Scenario
    effective_step: Step
    parameters: dict[str, Any]


class PolicyPatch(ContractModel):
    # Omission or null means unchanged; the future service applies non-null fields.
    risk_percentile: float | None = Field(default=None, gt=0, lt=1, allow_inf_nan=False)
    operational_buffer_cents: Cents | None = None
    minimum_sweep_cents: Cents | None = None
    vault_yield_bps: BasisPoints | None = None
    vault_lock_steps: PositiveSteps | None = None
    early_redemption_allowed: bool | None = None
    early_redemption_penalty_bps: BasisPoints | None = None

class CashFlowBucket(ContractModel):
    step: Step
    timestamp: datetime
    inflow_cents: Cents
    outflow_cents: Cents


class TransactionRecord(ContractModel):
    transaction_id: UUID
    run_id: UUID
    timestamp: datetime
    step: Step
    type: Literal["DEPOSIT", "WITHDRAWAL", "MERCHANT_SETTLEMENT"]
    direction: Literal["INFLOW", "OUTFLOW"]
    amount_cents: PositiveCents
    source: str = Field(min_length=1, max_length=100)
    scenario: Scenario

    @model_validator(mode="after")
    def validate_direction(self):
        expected = {"DEPOSIT": "INFLOW", "WITHDRAWAL": "OUTFLOW"}.get(self.type)
        if expected and self.direction != expected:
            raise ValueError("Direction conflicts with transaction type")
        return self


class LedgerEntry(ContractModel):
    entry_id: UUID
    run_id: UUID
    timestamp: datetime
    step: Step
    entry_type: str
    amount_cents: Cents
    balance_before_cents: Cents
    balance_after_cents: Cents
    reference_id: str


class VaultPosition(ContractModel):
    position_id: UUID
    run_id: UUID
    principal_cents: PositiveCents
    annual_rate_bps: BasisPoints
    created_at: datetime
    matures_at: datetime
    status: Literal["LOCKED", "MATURED", "REDEEMED"]
    early_redemption_allowed: bool
    early_redemption_penalty_bps: BasisPoints

    @model_validator(mode="after")
    def validate_maturity(self):
        if self.matures_at <= self.created_at:
            raise ValueError("Maturity must follow creation")
        return self


class ForecastSummary(ContractModel):
    horizon_minutes: PositiveSteps = 1440
    peak_shortfall_cents: Cents
    uncertainty_buffer_cents: Cents
    operational_buffer_cents: Cents
    model_version: str


class DecisionRecord(ContractModel):
    action: Literal["HOLD", "SWEEP", "WITHDRAW", "LIQUIDITY_WARNING"]
    amount_cents: Cents
    pre_checking_cents: Cents
    post_checking_cents: Cents
    executed: bool
    explanation: list[str]


class SimulationSnapshot(ContractModel):
    run_id: UUID
    step: Step
    timestamp: datetime
    checking_cents: Cents
    vault_locked_cents: Cents
    vault_redeemable_cents: Cents
    required_reserve_cents: Cents | None
    forecast: ForecastSummary | None
    decision: DecisionRecord | None


class FinancialMetrics(ContractModel):
    realized_interest_cents: Cents
    accrued_interest_cents: Cents
    average_checking_cents: Cents
    average_vault_cents: Cents
    redemption_penalties_cents: Cents
    emergency_borrowing_cost_cents: Cents
    emergency_events: Step
    reserve_breaches: Step
    failed_payouts: Step
    unpaid_cents: Cents
    net_benefit_cents: int = Field(strict=True)


class BacktestRequest(ContractModel):
    strategies: list[Literal["STATIC_RESERVE", "REACTIVE_RESERVE", "RESERVE_JUGGLER"]] = Field(
        default_factory=lambda: ["STATIC_RESERVE", "REACTIVE_RESERVE", "RESERVE_JUGGLER"],
        min_length=1,
    )


class StrategyResult(ContractModel):
    strategy: Literal["STATIC_RESERVE", "REACTIVE_RESERVE", "RESERVE_JUGGLER"]
    metrics: FinancialMetrics


class BacktestResult(ContractModel):
    run_id: UUID
    scenario: Scenario
    seed: int
    started_at: datetime
    ended_at: datetime
    results: list[StrategyResult]


class PerformanceReport(ContractModel):
    run_id: UUID
    scenario: Scenario
    seed: int
    started_at: datetime
    ended_at: datetime | None
    metrics: FinancialMetrics | None


class ErrorResponse(ContractModel):
    error_code: str
    message: str
    details: dict[str, Any] | list[dict[str, Any]]
