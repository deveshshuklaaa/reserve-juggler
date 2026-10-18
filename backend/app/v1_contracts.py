"""Member 2 public data contracts with additive four-tier portfolio extensions."""

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
    allow_bond_liquidation: bool = Field(default=False, strict=True)
    allow_emergency_equity_liquidation: bool = Field(default=False, strict=True)
    allow_overdraft: bool = Field(default=True, strict=True)
    max_overdraft_cents: int = Field(default=5000000000, strict=True, ge=0, le=9007199254740991)
    publication_delay_seconds: int = Field(default=0, strict=True, ge=0, le=2147483647)

    @model_validator(mode="after")
    def overdraft_policy(self):
        if not self.allow_overdraft and self.max_overdraft_cents:
            raise ValueError("disabled overdraft requires a zero principal cap")
        return self

    @model_validator(mode="before")
    @classmethod
    def map_frontend_policy_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        d = dict(data)
        if d.get("allow_overdraft") is False and "max_overdraft_cents" not in d:
            d["max_overdraft_cents"] = 0
        if "min_sweep_cents" in d and "minimum_sweep_cents" not in d:
            d["minimum_sweep_cents"] = d.pop("min_sweep_cents")
        if "vault_rate_bps" in d and "vault_yield_bps" not in d:
            d["vault_yield_bps"] = d.pop("vault_rate_bps")
        if "lock_steps" in d and "vault_lock_steps" not in d:
            d["vault_lock_steps"] = d.pop("lock_steps")
        if "allow_early_redemption" in d and "early_redemption_allowed" not in d:
            d["early_redemption_allowed"] = d.pop("allow_early_redemption")
        if "risk_percentile" in d and isinstance(d["risk_percentile"], (int, float)):
            # Frontend passes 90, 95, 99 as integer percentages
            if d["risk_percentile"] in (90, 95, 99):
                d["risk_percentile"] = d["risk_percentile"] / 100.0
        return d


class CreateRunRequest(ContractModel):
    dataset_id: str | None = Field(default=None, min_length=1, max_length=200)
    initial_cash_cents: Cents = 2000000000
    duration_steps: PositiveSteps = 288
    seed: int = Field(default=42, strict=True, ge=0, le=2147483647)
    scenario: Scenario = Scenario.NORMAL
    start_time: datetime | None = None
    policy: TreasuryPolicy = Field(default_factory=TreasuryPolicy)

    @model_validator(mode="before")
    @classmethod
    def map_frontend_create_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        d = dict(data)
        if "initial_checking_cents" in d and "initial_cash_cents" not in d:
            d["initial_cash_cents"] = d.pop("initial_checking_cents")
        d.pop("initial_vault_cents", None)
        d.pop("step_minutes", None)
        return d


class RunCreated(ContractModel):
    run_id: UUID
    status: Literal["READY"]
    current_step: Step
    checking_cents: Cents
    vault_locked_cents: Cents


class DatasetImported(ContractModel):
    dataset_id: str
    row_count: int
    content_hash: str
    native_interval_seconds: Literal[3600]
    first_timestamp: str
    last_timestamp: str
    timezone_status: Literal["UNSPECIFIED"]
    validation_status: Literal["VALIDATED", "VALIDATED_WITH_DIAGNOSTICS"]
    validation: dict[str, Any]


class AdvanceRequest(ContractModel):
    expected_step: Step
    steps: int = Field(default=1, strict=True, ge=1, le=168)


class ScenarioRequest(ContractModel):
    scenario: Scenario
    parameters: dict[str, Any] = Field(default_factory=dict)
    effective_step: Step | None = None


class ScenarioApplied(ContractModel):
    run_id: UUID
    scenario: Scenario
    effective_step: Step
    parameters: dict[str, Any]


class PolicyPatch(ContractModel):
    risk_percentile: float | None = Field(default=None, gt=0, lt=1, allow_inf_nan=False)
    operational_buffer_cents: Cents | None = None
    minimum_sweep_cents: Cents | None = None
    vault_yield_bps: BasisPoints | None = None
    vault_lock_steps: PositiveSteps | None = None
    early_redemption_allowed: bool | None = None
    early_redemption_penalty_bps: BasisPoints | None = None
    allow_bond_liquidation: bool | None = Field(default=None, strict=True)
    allow_emergency_equity_liquidation: bool | None = Field(default=None, strict=True)
    allow_overdraft: bool | None = Field(default=None, strict=True)
    max_overdraft_cents: int | None = Field(default=None, strict=True, ge=0, le=9007199254740991)
    publication_delay_seconds: int | None = Field(default=None, strict=True, ge=0, le=2147483647)

    @model_validator(mode="before")
    @classmethod
    def map_frontend_patch_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        d = dict(data)
        if "min_sweep_cents" in d and "minimum_sweep_cents" not in d:
            d["minimum_sweep_cents"] = d.pop("min_sweep_cents")
        if "vault_rate_bps" in d and "vault_yield_bps" not in d:
            d["vault_yield_bps"] = d.pop("vault_rate_bps")
        if "lock_steps" in d and "vault_lock_steps" not in d:
            d["vault_lock_steps"] = d.pop("lock_steps")
        if "allow_early_redemption" in d and "early_redemption_allowed" not in d:
            d["early_redemption_allowed"] = d.pop("allow_early_redemption")
        if "risk_percentile" in d and isinstance(d["risk_percentile"], (int, float)):
            if d["risk_percentile"] in (90, 95, 99):
                d["risk_percentile"] = d["risk_percentile"] / 100.0
        return d


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


# ---------------------------------------------------------
# Four-Tier Additive Models (Matching Frontend Contracts)
# ---------------------------------------------------------

class Tier0Snapshot(ContractModel):
    tier: int = 0
    name: str = "Operating Cash Buffer"
    checking_cents: Cents
    required_reserve_cents: Cents
    operational_buffer_cents: Cents
    deployable_surplus_cents: Cents
    reserve_deficit_cents: Cents
    immediate_liquidity_cents: Cents
    status: Literal["BALANCED", "SURPLUS", "DEFICIT"]


class Tier1Snapshot(ContractModel):
    tier: int = 1
    id: str = "REPO-1"
    name: str = "Overnight Repo"
    principal_cents: Cents
    repo_apy_bps: BasisPoints | None
    repo_apy_decimal: str | None
    accrued_interest_cents: Cents
    realized_interest_cents: Cents
    status: Literal["LOCKED", "MATURED", "REDEEMED"]
    entry_window_open: bool
    early_redemption_allowed: bool
    early_break_fee_bps: BasisPoints
    break_fee_cents: Cents
    net_redeemable_cents: Cents
    immediate_liquidity_cents: Cents
    entry_time: str = "17:00"
    maturity_time: str = "08:00"
    maturity_timestamp: str | None = None


class Tier2Snapshot(ContractModel):
    tier: int = 2
    id: str = "BOND-SOV-1"
    name: str = "Sovereign Bonds"
    notional_cents: Cents
    quantity: float
    acquisition_price: str | None
    current_price: str | None
    market_value_cents: Cents
    ytm_bps: BasisPoints | None
    ytm_decimal: str | None
    modified_duration: float | None
    liquidation_haircut_bps: BasisPoints
    haircut_cents: Cents
    realized_pnl_cents: int = Field(strict=True)
    unrealized_pnl_cents: int = Field(strict=True)
    available_liquidity_cents: Cents
    liquidity_status: str = "2-DAY_SETTLEMENT_OR_HAIRCUT"


class Tier3Snapshot(ContractModel):
    tier: int = 3
    id: str = "EQ-IDX-1"
    name: str = "Growth Equities"
    quantity: float
    acquisition_price: str | None
    current_price: str | None
    market_value_cents: Cents
    cost_basis_cents: Cents
    volatility_bps: BasisPoints | None
    volatility_decimal: str | None
    emergency_slippage_bps: BasisPoints
    slippage_cents: Cents
    realized_pnl_cents: int = Field(strict=True)
    unrealized_pnl_cents: int = Field(strict=True)
    available_liquidity_cents: Cents
    liquidity_status: str = "MARKET_VOLATILITY_AND_SLIPPAGE"


class OverdraftSnapshot(ContractModel):
    borrowing_outstanding_cents: Cents
    financing_rate_bps: BasisPoints | None
    financing_cost_cents: Cents
    liability_status: Literal["ACTIVE", "CLEARED"]
    is_active: bool


class AggregatesSnapshot(ContractModel):
    gross_assets_cents: Cents
    total_liabilities_cents: Cents
    net_portfolio_value_cents: int = Field(strict=True)
    total_immediate_liquidity_cents: Cents
    total_realized_returns_cents: int = Field(strict=True)
    total_unrealized_returns_cents: int = Field(strict=True)
    net_financial_benefit_cents: int = Field(strict=True)
    checking_cents: Cents
    required_reserve_cents: Cents
    deployable_surplus_cents: Cents


class FourTierPortfolioSnapshot(ContractModel):
    timestamp: str | None = None
    market_data_available: bool = True
    market_observation_timestamp: str | None = None
    publication_delay_seconds: int = 0
    tier0: Tier0Snapshot
    tier1: Tier1Snapshot
    tier2: Tier2Snapshot
    tier3: Tier3Snapshot
    overdraft: OverdraftSnapshot
    aggregates: AggregatesSnapshot


class SimulationSnapshot(ContractModel):
    source_dataset: dict[str, Any] | None = None
    duration_steps: PositiveSteps | None = None
    run_id: UUID
    step: Step
    timestamp: datetime
    checking_cents: Cents
    vault_locked_cents: Cents
    vault_redeemable_cents: Cents
    required_reserve_cents: Cents | None
    forecast: ForecastSummary | None
    decision: DecisionRecord | None
    status: str = "READY"
    policy: TreasuryPolicy | None = None
    deployable_surplus_cents: Cents = 0
    four_tier: FourTierPortfolioSnapshot | None = None


# ---------------------------------------------------------
# Collections & Enveloped Responses
# ---------------------------------------------------------

class HistoryResponse(ContractModel):
    items: list[SimulationSnapshot]


class DecisionsResponse(ContractModel):
    items: list[DecisionRecord]


class TransactionsResponse(ContractModel):
    items: list[TransactionRecord]


class ForecastPoint(ContractModel):
    timestamp: datetime
    predicted_inflow_cents: Cents
    predicted_outflow_cents: Cents
    predicted_net_cents: int = Field(strict=True)
    lower_cents: int = Field(strict=True)
    upper_cents: int = Field(strict=True)


class ForecastResponse(ContractModel):
    as_of: datetime
    horizon_minutes: PositiveSteps
    model_version: str
    points: list[ForecastPoint]
    summary: ForecastSummary | None = None


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
    retain_runs: bool = False
    days: Literal[7, 14, 30] | None = None
    scenario: Scenario | None = None
    seed: int | None = None

    @field_validator("days", mode="before")
    @classmethod
    def strict_backtest_days(cls, value):
        if value is not None and (type(value) is not int or value not in (7, 14, 30)):
            raise ValueError("Backtests require integer days of 7, 14 or 30")
        return value

    @model_validator(mode="before")
    @classmethod
    def normalize_frontend_backtest_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        d = dict(data)
        if "strategies" in d and isinstance(d["strategies"], list):
            mapping = {
                "STATIC": "STATIC_RESERVE",
                "STATIC_RESERVE": "STATIC_RESERVE",
                "REACTIVE": "REACTIVE_RESERVE",
                "REACTIVE_RESERVE": "REACTIVE_RESERVE",
                "RESERVE_JUGGLER": "RESERVE_JUGGLER",
            }
            d["strategies"] = [mapping.get(s, s) for s in d["strategies"]]
        return d

    @field_validator("strategies")
    @classmethod
    def unique_strategies(cls, value):
        if len(set(value)) != len(value):
            raise ValueError("Requested strategies must be unique")
        return value


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
