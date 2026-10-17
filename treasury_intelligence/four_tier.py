"""Additive four-tier wire contracts. No optimizer, loader, or trading side effects."""
from datetime import datetime, time, timedelta
from decimal import Decimal, ROUND_HALF_UP, localcontext
from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StrictBool, StrictInt, field_validator, model_validator

from .types import Cents, Name, PositiveInt


def _decimal(value):
    if isinstance(value, bool) or not isinstance(value, (Decimal, str, int)):
        raise ValueError("use Decimal or decimal strings; binary floats are forbidden")
    return value


def _timestamp(value):
    if not isinstance(value, (str, datetime)):
        raise ValueError("use a timezone-unspecified ISO timestamp or datetime")
    try:
        parsed = datetime.fromisoformat(value) if isinstance(value, str) else value
    except ValueError as error:
        raise ValueError("invalid ISO timestamp") from error
    if parsed.tzinfo is not None:
        raise ValueError("source timezone is unspecified; offsets must not be inferred")
    return parsed


ExactDecimal = Annotated[Decimal, BeforeValidator(_decimal), Field(allow_inf_nan=False)]
NonnegativeDecimal = Annotated[ExactDecimal, Field(ge=0)]
PositiveDecimal = Annotated[ExactDecimal, Field(gt=0)]
Percent = Annotated[ExactDecimal, Field(ge=0, le=100)]
Fraction = Annotated[ExactDecimal, Field(ge=0, le=1)]
LocalTimestamp = Annotated[datetime, BeforeValidator(_timestamp)]


class FourTierContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)


class InstrumentId(str, Enum):
    TIER0_CASH = "TIER0_CASH"
    TIER1_REPO = "TIER1_REPO"
    TIER2_BOND = "TIER2_BOND"
    TIER3_EQUITY = "TIER3_EQUITY"
    OVERDRAFT = "OVERDRAFT"


ASSET_IDS = frozenset(InstrumentId) - {InstrumentId.OVERDRAFT}
AssetId = Literal["TIER0_CASH", "TIER1_REPO", "TIER2_BOND", "TIER3_EQUITY"]


class OrganizerHourlyObservation(FourTierContract):
    """Exactly the 16 CSV columns, without unit conversion or net-flow rewriting."""
    timestamp: LocalTimestamp
    deposits_usd: NonnegativeDecimal
    withdrawals_usd: NonnegativeDecimal
    net_flow_usd: ExactDecimal
    repo_sweep_window_open: StrictBool
    repo_sweep_mature: StrictBool
    tier1_repo_rate_apy: ExactDecimal
    tier2_bond_yield_pct: ExactDecimal
    tier2_bond_price_index: PositiveDecimal
    tier2_bond_mod_duration: NonnegativeDecimal
    tier3_stock_index_price: PositiveDecimal
    tier3_stock_volatility_pct: NonnegativeDecimal
    tier1_early_redemption_haircut_pct: Percent
    tier2_bond_liquidation_haircut_pct: Percent
    tier3_stock_liquidation_haircut_pct: Percent
    emergency_overdraft_penalty_apr_pct: NonnegativeDecimal

    @field_validator("repo_sweep_window_open", "repo_sweep_mature", mode="before")
    @classmethod
    def csv_boolean(cls, value):
        if value == "True":
            return True
        if value == "False":
            return False
        return value

    @field_validator("timestamp")
    @classmethod
    def hourly(cls, value):
        if value.minute or value.second or value.microsecond:
            raise ValueError("organizer observations must be on native hourly boundaries")
        return value


class MarketRateObservation(FourTierContract):
    observed_at: LocalTimestamp
    repo_apy_pct: ExactDecimal
    bond_yield_pct: ExactDecimal
    equity_volatility_pct: NonnegativeDecimal
    overdraft_apr_pct: NonnegativeDecimal


class MarketPriceObservation(FourTierContract):
    observed_at: LocalTimestamp
    bond_price_index: PositiveDecimal
    bond_modified_duration_years: NonnegativeDecimal
    equity_index_price: PositiveDecimal


class Tier0CashPosition(FourTierContract):
    instrument: Literal["TIER0_CASH"] = "TIER0_CASH"
    available_cents: Cents
    annual_yield_pct: Literal[0] = 0


class Tier1RepoPosition(FourTierContract):
    instrument: Literal["TIER1_REPO"] = "TIER1_REPO"
    position_id: Name
    principal_cents: Cents
    entered_at: LocalTimestamp
    matures_at: LocalTimestamp
    entry_apy_pct: ExactDecimal
    early_break_allowed: StrictBool
    early_break_fee_pct: Percent = Decimal("0.5")
    estimated_interest_cents: StrictInt

    @model_validator(mode="after")
    def overnight_session(self):
        if self.entered_at.time() != time(17) or self.matures_at != self.entered_at + timedelta(hours=15):
            raise ValueError("repo session must run from 17:00 to next-day 08:00 (15 hours)")
        return self


class MarketPosition(FourTierContract):
    position_id: Name
    index_units: PositiveDecimal
    cost_basis_cents: Cents
    observed_price_index: PositiveDecimal
    marked_at: LocalTimestamp
    market_value_cents: Cents

    @model_validator(mode="after")
    def marked_value(self):
        # Index units are normalized dollar exposure per index point, not exchange lots.
        precision = len(self.index_units.as_tuple().digits) + len(self.observed_price_index.as_tuple().digits) + 20
        with localcontext() as ctx:
            ctx.prec = max(28, precision)
            marked = int((self.index_units * self.observed_price_index * 100).to_integral_value(rounding=ROUND_HALF_UP))
        if self.market_value_cents != marked:
            raise ValueError("market_value_cents must match units times observed index, half-up cents")
        return self


class Tier2BondPosition(MarketPosition):
    instrument: Literal["TIER2_BOND"] = "TIER2_BOND"
    matures_at: LocalTimestamp
    tenor_years: Literal[2] = 2
    annual_yield_pct: ExactDecimal
    modified_duration_years: NonnegativeDecimal
    liquidation_haircut_pct: Percent = Decimal("2")


class Tier3EquityPosition(MarketPosition):
    instrument: Literal["TIER3_EQUITY"] = "TIER3_EQUITY"
    annual_volatility_pct: NonnegativeDecimal
    emergency_sale_slippage_pct: Percent = Decimal("15")


class OverdraftLiability(FourTierContract):
    instrument: Literal["OVERDRAFT"] = "OVERDRAFT"
    principal_cents: Cents
    accrued_financing_cost_cents: Cents
    annual_apr_pct: NonnegativeDecimal
    credit_limit_cents: Cents

    @model_validator(mode="after")
    def credit_limit(self):
        if self.principal_cents > self.credit_limit_cents:
            raise ValueError("overdraft principal exceeds credit limit")
        return self


class CostBreakdown(FourTierContract):
    liquidation_fee_cents: Cents = 0
    repo_break_fee_cents: Cents = 0
    transaction_cost_cents: Cents = 0
    funding_cost_cents: Cents = 0
    market_loss_cents: Cents = 0


class FourTierPortfolioState(FourTierContract):
    as_of: LocalTimestamp
    timestamp_basis: Literal["timezone_unspecified"] = "timezone_unspecified"
    currency: Literal["USD"] = "USD"
    cash: Tier0CashPosition
    repos: tuple[Tier1RepoPosition, ...] = ()
    bonds: tuple[Tier2BondPosition, ...] = ()
    equities: tuple[Tier3EquityPosition, ...] = ()
    overdraft: OverdraftLiability
    market_rates: MarketRateObservation
    market_prices: MarketPriceObservation
    realized_costs: CostBreakdown = Field(default_factory=CostBreakdown)

    @model_validator(mode="after")
    def coherent_snapshot(self):
        positions = (*self.repos, *self.bonds, *self.equities)
        if len({p.position_id for p in positions}) != len(positions):
            raise ValueError("position IDs must be unique")
        if self.market_rates.observed_at > self.as_of or self.market_prices.observed_at > self.as_of:
            raise ValueError("future market observations are forbidden")
        if any(p.entered_at > self.as_of for p in self.repos):
            raise ValueError("future repo entry in current portfolio")
        for position in (*self.bonds, *self.equities):
            price = self.market_prices.bond_price_index if isinstance(position, Tier2BondPosition) else self.market_prices.equity_index_price
            if position.marked_at != self.market_prices.observed_at or position.observed_price_index != price:
                raise ValueError("positions must be marked to the supplied observed prices")
        return self


class ExposureConstraint(FourTierContract):
    instrument: AssetId
    minimum_fraction: Fraction = Decimal("0")
    maximum_fraction: Fraction

    @model_validator(mode="after")
    def ordered_bounds(self):
        if self.minimum_fraction > self.maximum_fraction:
            raise ValueError("minimum exposure exceeds maximum")
        return self


def _all_assets(items):
    if len(items) != 4 or {i.instrument for i in items} != ASSET_IDS:
        raise ValueError("exactly one entry for each of the four asset tiers is required")


class FourTierRiskPolicy(FourTierContract):
    minimum_liquid_reserve_cents: Cents
    operational_buffer_cents: Cents
    max_estimated_loss_cents: Cents
    overdraft_allowed: StrictBool
    max_overdraft_cents: Cents
    exposure_constraints: tuple[ExposureConstraint, ...]
    bond_risk_method: Literal["observed_index_with_separate_duration_stress"] = "observed_index_with_separate_duration_stress"

    @model_validator(mode="after")
    def constraints(self):
        _all_assets(self.exposure_constraints)
        with localcontext() as ctx:
            ctx.prec = max(28, sum(len(c.minimum_fraction.as_tuple().digits) + len(c.maximum_fraction.as_tuple().digits) for c in self.exposure_constraints) + 10)
            if sum(c.minimum_fraction for c in self.exposure_constraints) > 1 or sum(c.maximum_fraction for c in self.exposure_constraints) < 1:
                raise ValueError("exposure bounds cannot describe a fully allocated portfolio")
        if not self.overdraft_allowed and self.max_overdraft_cents:
            raise ValueError("disabled overdraft must have a zero policy limit")
        return self


class ForecastRiskMetadata(FourTierContract):
    model_version: Name
    generated_at: LocalTimestamp
    training_data_through: LocalTimestamp
    granularity_hours: Literal[1] = 1
    net_flow_target: Literal["source_net_flow_usd", "deposits_minus_withdrawals"]
    uncertainty_status: Literal["not_evaluated", "provisional_uncalibrated", "evaluated"]
    evaluation_reference: Name | None = None
    notes: tuple[Name, ...] = ()

    @model_validator(mode="after")
    def provenance(self):
        if self.training_data_through > self.generated_at:
            raise ValueError("training data cannot be from the future")
        if (self.uncertainty_status == "evaluated") != (self.evaluation_reference is not None):
            raise ValueError("evaluated status requires an actual evaluation reference only")
        return self


class HourlyForecastPoint(FourTierContract):
    start_at: LocalTimestamp
    predicted_deposits_cents: Cents
    predicted_withdrawals_cents: Cents
    predicted_net_flow_cents: StrictInt
    supplied_uncertainty_buffer_cents: Cents

    @field_validator("start_at")
    @classmethod
    def hourly(cls, value):
        if value.minute or value.second or value.microsecond:
            raise ValueError("four-tier forecasts must retain hourly boundaries")
        return value


class FourTierRecommendationRequest(FourTierContract):
    request_id: Name
    portfolio: FourTierPortfolioState
    history: Annotated[tuple[OrganizerHourlyObservation, ...], Field(min_length=1)]
    policy: FourTierRiskPolicy
    metadata: ForecastRiskMetadata
    forecast: Annotated[tuple[HourlyForecastPoint, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def causal_hourly_input(self):
        as_of = self.portfolio.as_of
        if self.metadata.generated_at != as_of or self.metadata.training_data_through > self.history[-1].timestamp:
            raise ValueError("metadata must match decision time and available history")
        if any(h.timestamp > as_of for h in self.history):
            raise ValueError("future historical observations are forbidden")
        if any(b.timestamp - a.timestamp != timedelta(hours=1) for a, b in zip(self.history, self.history[1:])):
            raise ValueError("history must be ordered contiguous native hourly observations")
        if self.forecast[0].start_at < as_of:
            raise ValueError("forecast cannot start before decision time")
        if any(b.start_at - a.start_at != timedelta(hours=1) for a, b in zip(self.forecast, self.forecast[1:])):
            raise ValueError("forecast points must be ordered hourly")
        return self


class AllocationTarget(FourTierContract):
    instrument: AssetId
    target_cents: Cents


class TradeRecommendation(FourTierContract):
    trade_id: Name
    instrument: InstrumentId
    action: Literal["ENTER_REPO", "REDEEM_REPO", "BUY", "SELL", "BORROW", "REPAY"]
    principal_cents: Annotated[StrictInt, Field(gt=0)]
    index_units: PositiveDecimal | None = None
    position_id: Name | None = None
    earliest_execution_at: LocalTimestamp
    expected_settlement_at: LocalTimestamp
    expected_maturity_at: LocalTimestamp | None = None
    expected_costs: CostBreakdown
    reason: Name
    recommendation_only: Literal[True] = True
    execution_status: Literal["NOT_EXECUTED"] = "NOT_EXECUTED"

    @field_validator("recommendation_only", mode="before")
    @classmethod
    def true_boolean(cls, value):
        if value is not True:
            raise ValueError("recommendation_only must be boolean true")
        return value

    @model_validator(mode="after")
    def trade_shape(self):
        allowed = {
            InstrumentId.TIER0_CASH: (), InstrumentId.TIER1_REPO: ("ENTER_REPO", "REDEEM_REPO"),
            InstrumentId.TIER2_BOND: ("BUY", "SELL"), InstrumentId.TIER3_EQUITY: ("BUY", "SELL"),
            InstrumentId.OVERDRAFT: ("BORROW", "REPAY"),
        }
        if self.action not in allowed[self.instrument]:
            raise ValueError("action is incompatible with instrument")
        if (self.instrument in (InstrumentId.TIER2_BOND, InstrumentId.TIER3_EQUITY)) != (self.index_units is not None):
            raise ValueError("only market trades require index units")
        if self.action in ("SELL", "REDEEM_REPO") and self.position_id is None:
            raise ValueError("sales and redemptions require a position ID")
        if self.expected_settlement_at < self.earliest_execution_at:
            raise ValueError("settlement cannot precede execution")
        if self.action == "ENTER_REPO":
            if self.earliest_execution_at.time() != time(17) or self.expected_settlement_at != self.earliest_execution_at:
                raise ValueError("repo entry must settle at the proposed 17:00 entry window")
            if self.expected_maturity_at != self.earliest_execution_at + timedelta(hours=15):
                raise ValueError("repo entry must specify next-day 08:00 maturity")
        elif self.expected_maturity_at is not None:
            raise ValueError("only repo entry recommendations specify a new maturity")
        return self


class InstrumentReturnEstimate(FourTierContract):
    instrument: InstrumentId
    horizon_hours: PositiveInt
    expected_income_cents: StrictInt
    expected_price_change_cents: StrictInt
    expected_costs: CostBreakdown
    estimated_stress_loss_cents: Cents
    estimate_basis: Name
    realized: Literal[False] = False

    @field_validator("realized", mode="before")
    @classmethod
    def false_boolean(cls, value):
        if value is not False:
            raise ValueError("return estimate cannot be labeled realized")
        return value


class PortfolioRecommendation(FourTierContract):
    request_id: Name
    as_of: LocalTimestamp
    action: Literal["HOLD", "REBALANCE", "LIQUIDITY_WARNING"]
    recommendation_only: Literal[True] = True
    execution_status: Literal["NOT_EXECUTED"] = "NOT_EXECUTED"
    feasible: StrictBool
    allocation_budget_cents: Cents
    targets: tuple[AllocationTarget, ...]
    target_overdraft_principal_cents: Cents
    required_liquid_reserve_cents: Cents
    trades: tuple[TradeRecommendation, ...] = ()
    expected_costs: CostBreakdown
    estimated_market_risk_loss_cents: Cents
    instrument_returns: tuple[InstrumentReturnEstimate, ...]
    exposure_constraints: tuple[ExposureConstraint, ...]
    metadata: ForecastRiskMetadata
    explanations: Annotated[tuple[Name, ...], Field(min_length=1)]

    @field_validator("recommendation_only", mode="before")
    @classmethod
    def true_boolean(cls, value):
        if value is not True:
            raise ValueError("recommendation_only must be boolean true")
        return value

    @model_validator(mode="after")
    def consistent_recommendation(self):
        _all_assets(self.targets)
        _all_assets(self.exposure_constraints)
        if sum(t.target_cents for t in self.targets) != self.allocation_budget_cents:
            raise ValueError("targets must sum to allocation budget; overdraft is a separate liability")
        if self.metadata.generated_at != self.as_of:
            raise ValueError("metadata and recommendation times must match")
        if len({t.trade_id for t in self.trades}) != len(self.trades):
            raise ValueError("trade IDs must be unique")
        if len({r.instrument for r in self.instrument_returns}) != len(self.instrument_returns):
            raise ValueError("duplicate instrument return estimates")
        if any(t.earliest_execution_at < self.as_of for t in self.trades):
            raise ValueError("recommended trades cannot execute in the past")
        if self.action != "REBALANCE" and self.trades:
            raise ValueError("HOLD and warning responses do not propose trades")
        if self.action == "REBALANCE" and (not self.trades or not self.feasible):
            raise ValueError("rebalancing requires feasible proposed trades")
        if self.action == "LIQUIDITY_WARNING" and self.feasible:
            raise ValueError("liquidity warnings cannot claim feasibility")
        if self.feasible:
            cash = next(t.target_cents for t in self.targets if t.instrument == "TIER0_CASH")
            if cash < self.required_liquid_reserve_cents:
                raise ValueError("feasible target cash must cover required reserve")
            bounds = {c.instrument: c for c in self.exposure_constraints}
            with localcontext() as ctx:
                ctx.prec = max(28, len(str(self.allocation_budget_cents)) + max(len(c.maximum_fraction.as_tuple().digits) + len(c.minimum_fraction.as_tuple().digits) for c in bounds.values()) + 20)
                for target in self.targets:
                    bound = bounds[target.instrument]
                    if not bound.minimum_fraction * self.allocation_budget_cents <= target.target_cents <= bound.maximum_fraction * self.allocation_budget_cents:
                        raise ValueError("feasible target violates exposure bounds")
        return self


def recommend_portfolio_allocation(request: FourTierRecommendationRequest) -> PortfolioRecommendation:
    """Additive contract boundary for Member 2; optimizer is a later milestone."""
    raise NotImplementedError("RJ-M1-06 defines four-tier contracts only")
