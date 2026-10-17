"""Validated, immutable quantitative engine wire contracts (Pydantic 2)."""
from datetime import datetime, timedelta
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, field_validator, model_validator

Cents = Annotated[StrictInt, Field(ge=0)]
Bps = Annotated[StrictInt, Field(ge=0, le=10_000)]
PositiveInt = Annotated[StrictInt, Field(gt=0)]
Name = Annotated[str, Field(strict=True, min_length=1)]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)

    @field_validator("*", mode="before")
    @classmethod
    def explicit_wire_types(cls, value, info):
        if info.field_name in {"start_at", "end_at", "as_of", "generated_at"}:
            if not isinstance(value, (str, datetime)):
                raise ValueError("timestamps require ISO 8601 strings or datetime objects")
        if info.field_name == "recommendation_only" and value is not True:
            raise ValueError("recommendation_only must be boolean true")
        return value

    @field_validator("*", mode="after")
    @classmethod
    def utc_only(cls, value):
        if isinstance(value, datetime):
            if value.tzinfo is None or value.utcoffset() != timedelta(0):
                raise ValueError("timestamps must be timezone-aware UTC")
        return value


class CashFlowBucket(Contract):
    start_at: datetime
    end_at: datetime
    inflow_cents: Cents
    outflow_cents: Cents

    @model_validator(mode="after")
    def valid_interval(self):
        if self.end_at <= self.start_at:
            raise ValueError("end_at must follow start_at")
        return self


class ForecastPoint(CashFlowBucket):
    uncertainty_cents: Cents


class ForecastResult(Contract):
    generated_at: datetime
    model_version: Name
    points: Annotated[tuple[ForecastPoint, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def ordered_points(self):
        if self.points[0].start_at < self.generated_at:
            raise ValueError("forecast cannot begin before generated_at")
        if any(b.start_at < a.end_at for a, b in zip(self.points, self.points[1:])):
            raise ValueError("forecast points must be ordered and non-overlapping")
        return self


class VaultPosition(Contract):
    vault_id: Name
    balance_cents: Cents
    withdrawable_cents: Cents
    annual_yield_bps: Bps
    withdrawal_delay_minutes: Annotated[StrictInt, Field(ge=0)]

    @model_validator(mode="after")
    def available_balance(self):
        if self.withdrawable_cents > self.balance_cents:
            raise ValueError("withdrawable amount exceeds balance")
        return self


class TreasuryContext(Contract):
    as_of: datetime
    currency: Annotated[str, Field(strict=True, pattern=r"^[A-Z]{3}$")]
    checking_balance_cents: Cents
    vaults: tuple[VaultPosition, ...] = ()

    @model_validator(mode="after")
    def unique_vaults(self):
        if len({v.vault_id for v in self.vaults}) != len(self.vaults):
            raise ValueError("vault IDs must be unique")
        return self


class TreasuryPolicy(Contract):
    base_buffer_cents: Cents
    uncertainty_multiplier_bps: Annotated[StrictInt, Field(ge=0)]
    tolerance_bps: Bps
    min_transfer_cents: Cents
    max_allocation_bps: Bps


class ReserveResult(Contract):
    as_of: datetime
    net_drain_cents: Cents
    uncertainty_buffer_cents: Cents
    base_buffer_cents: Cents
    required_reserve_cents: Cents

    @model_validator(mode="after")
    def reserve_sum(self):
        if self.required_reserve_cents != self.net_drain_cents + self.uncertainty_buffer_cents + self.base_buffer_cents:
            raise ValueError("reserve must equal the sum of its components")
        return self


class DecisionResult(Contract):
    as_of: datetime
    recommendation_only: Literal[True] = True
    action: Literal["HOLD", "SWEEP", "WITHDRAW", "LIQUIDITY_WARNING"]
    amount_cents: Cents
    vault_id: Name | None = None
    reserve: ReserveResult
    reason: Name

    @model_validator(mode="after")
    def valid_action(self):
        if self.as_of != self.reserve.as_of:
            raise ValueError("decision and reserve timestamps must match")
        if self.action == "HOLD" and (self.amount_cents != 0 or self.vault_id is not None):
            raise ValueError("HOLD cannot recommend a transfer")
        if self.action in ("SWEEP", "WITHDRAW") and (self.amount_cents == 0 or self.vault_id is None):
            raise ValueError("transfers require a positive amount and a vault")
        if self.action == "LIQUIDITY_WARNING" and (self.amount_cents or self.vault_id is not None):
            raise ValueError("warning is an alert, not a transfer")
        return self


class EvaluationResult(Contract):
    model_version: Name
    sample_count: PositiveInt
    mean_absolute_error_cents: Cents
    root_mean_squared_error_cents: Cents
    coverage_bps: Bps


class RiskScenarioResult(Contract):
    scenario_id: Name
    seed: Annotated[StrictInt, Field(ge=0)]
    probability_bps: Bps
    forecast: ForecastResult
    reserve: ReserveResult
    liquidity_shortfall_cents: Cents

    @model_validator(mode="after")
    def aligned_time(self):
        if self.forecast.generated_at != self.reserve.as_of:
            raise ValueError("scenario forecast and reserve timestamps must match")
        return self


class OptimizationResult(Contract):
    candidate_id: Name
    recommendation_only: Literal[True] = True
    allocation_bps: Bps
    allocation_cents: Cents
    expected_yield_cents: Cents
    liquidity_shortfall_cents: Cents
    feasible: StrictBool
    reason: Name
