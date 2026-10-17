"""Canonical four-tier wire contracts; supplied state, never financial execution.

Field names/units follow Member 2 migration 003. The v1 generic-vault engine is
deliberately not an implicit adapter for these instrument-specific contracts.
"""
from datetime import datetime, time, timedelta
from decimal import Decimal
from enum import Enum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, BeforeValidator, Field, StrictBool, StrictInt, field_validator, model_validator

from .types import Bps, Cents, Contract, Name, PositiveInt, ReserveResult, TreasuryPolicy


def _decimal(value):
    if isinstance(value, bool) or not isinstance(value, (Decimal, str, int)):
        raise ValueError("use Decimal, a decimal string, or an integer; never binary floats")
    try:
        result = Decimal(value)
    except ArithmeticError as exc:
        raise ValueError("invalid decimal") from exc
    if not result.is_finite():
        raise ValueError("financial quantities must be finite")
    return result


def _timestamp(value):
    if not isinstance(value, (str, datetime)):
        raise ValueError("timestamps require ISO 8601 strings or datetime objects")
    return value


ExactDecimal = Annotated[Decimal, BeforeValidator(_decimal)]
NonnegativeDecimal = Annotated[ExactDecimal, Field(ge=0)]
PositiveDecimal = Annotated[ExactDecimal, Field(gt=0)]
HaircutPct = Annotated[ExactDecimal, Field(ge=0, le=100)]
SignedCents = StrictInt
Timestamp = Annotated[datetime, BeforeValidator(_timestamp)]
TimeBasis = Literal["UNSPECIFIED", "UTC"]


def _check_times(record):
    for name in type(record).model_fields:
        value = getattr(record, name)
        if isinstance(value, datetime):
            if record.time_basis == "UNSPECIFIED" and value.tzinfo is not None:
                raise ValueError(f"{name}: organizer source time must remain naive")
            if record.time_basis == "UTC" and (value.tzinfo is None or value.utcoffset() != timedelta(0)):
                raise ValueError(f"{name}: explicitly UTC time must be timezone-aware UTC")
    return record


class TimedPortfolioContract(BaseModel):
    # Reuse v1 immutability/extra-field policy, not its blanket UTC validators.
    model_config = Contract.model_config
    time_basis: TimeBasis

    @field_validator("recommendation_only", mode="before", check_fields=False)
    @classmethod
    def recommendation_is_true(cls, value):
        if value is not True:
            raise ValueError("recommendation_only must be boolean true")
        return value

    @model_validator(mode="after")
    def explicit_time_basis(self):
        return _check_times(self)


class InstrumentId(str, Enum):
    TIER0_CASH = "TIER0_CASH"
    TIER1_REPO = "TIER1_REPO"
    TIER2_BOND = "TIER2_BOND"
    TIER3_EQUITY = "TIER3_EQUITY"
    OVERDRAFT = "OVERDRAFT"


class OrganizerHourlyObservation(BaseModel):
    # Exactly the source's 16 fields: timestamp basis is intrinsically UNSPECIFIED.
    model_config = Contract.model_config
    timestamp: Timestamp
    deposits_usd: NonnegativeDecimal
    withdrawals_usd: NonnegativeDecimal
    net_flow_usd: ExactDecimal
    repo_sweep_window_open: StrictBool
    repo_sweep_mature: StrictBool
    tier1_repo_rate_apy: ExactDecimal
    tier2_bond_yield_pct: ExactDecimal
    tier2_bond_price_index: PositiveDecimal
    tier2_bond_mod_duration: PositiveDecimal
    tier3_stock_index_price: PositiveDecimal
    tier3_stock_volatility_pct: NonnegativeDecimal
    tier1_early_redemption_haircut_pct: HaircutPct
    tier2_bond_liquidation_haircut_pct: HaircutPct
    tier3_stock_liquidation_haircut_pct: HaircutPct
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
        if value.tzinfo is not None or value.minute or value.second or value.microsecond:
            raise ValueError("organizer source observations must retain native hourly timestamps")
        return value


class MarketRateObservation(TimedPortfolioContract):
    observed_at: Timestamp
    repo_apy_pct: ExactDecimal
    bond_yield_pct: ExactDecimal
    equity_volatility_pct: NonnegativeDecimal
    overdraft_apr_pct: NonnegativeDecimal


class MarketPriceObservation(TimedPortfolioContract):
    observed_at: Timestamp
    bond_price_index: PositiveDecimal
    bond_modified_duration_years: PositiveDecimal
    equity_index_price: PositiveDecimal


class PortfolioSource(TimedPortfolioContract):
    run_id: UUID
    source_type: Literal["ORGANIZER_HISTORICAL", "SYNTHETIC"]
    dataset_id: Name | None = None
    source_observation_timestamp: Timestamp | None = None

    @model_validator(mode="after")
    def source_provenance(self):
        if self.source_type == "ORGANIZER_HISTORICAL":
            if self.time_basis != "UNSPECIFIED" or self.dataset_id is None or self.source_observation_timestamp is None:
                raise ValueError("historical state requires dataset, naive observation time and UNSPECIFIED basis")
            if any((self.source_observation_timestamp.minute, self.source_observation_timestamp.second,
                    self.source_observation_timestamp.microsecond)):
                raise ValueError("historical references must identify native hourly observations")
        elif self.time_basis != "UTC" or self.dataset_id is not None or self.source_observation_timestamp is not None:
            raise ValueError("synthetic state requires UTC and no organizer observation reference")
        as_of = getattr(self, "as_of", None)
        if as_of is not None and self.source_observation_timestamp is not None and self.source_observation_timestamp > as_of:
            raise ValueError("state/recommendations cannot use an observation later than as_of")
        return self


class PositionLiquidity(Contract):
    classification: Literal["IMMEDIATE", "LOCKED", "LIQUIDATABLE", "UNAVAILABLE"]
    available_cents: Cents
    locked_cents: Cents
    liquidatable_value_cents: Cents

    @model_validator(mode="after")
    def classification_consistency(self):
        if self.classification != "IMMEDIATE" and self.available_cents:
            raise ValueError("non-immediate funds cannot be reported as available cash")
        if self.classification == "IMMEDIATE" and self.locked_cents:
            raise ValueError("immediate funds cannot simultaneously be locked")
        if self.classification == "UNAVAILABLE" and self.liquidatable_value_cents:
            raise ValueError("unavailable funds cannot be reported as liquidatable proceeds")
        return self


class Position(PortfolioSource):
    id: UUID
    liquidity: PositionLiquidity

    @model_validator(mode="before")
    @classmethod
    def strict_tier(cls, value):
        if isinstance(value, dict) and "tier" in value and type(value["tier"]) is not int:
            raise ValueError("tier must be an integer, not a bool, string or float")
        return value


class CashPosition(Position):
    tier: Literal[0] = 0
    balance_cents: Cents
    last_ledger_entry_id: UUID | None = None
    apy_pct: Annotated[ExactDecimal, Field(ge=0, le=0)] = Decimal("0")

    @model_validator(mode="after")
    def cash_is_liquid(self):
        if (self.liquidity.classification != "IMMEDIATE" or self.liquidity.locked_cents
                or self.liquidity.available_cents != self.balance_cents
                or self.liquidity.liquidatable_value_cents != self.balance_cents):
            raise ValueError("Tier 0 is zero-yield, fully and immediately liquid cash")
        return self


class RepoPosition(Position):
    tier: Literal[1] = 1
    principal_cents: Cents
    entered_at: Timestamp
    scheduled_maturity_at: Timestamp
    applicable_apy_pct: ExactDecimal
    status: Literal["LOCKED", "MATURED", "REDEEMED"]
    early_redemption_at: Timestamp | None = None
    early_redemption_haircut_pct: HaircutPct
    accrued_interest_cents: SignedCents | None = None
    realized_interest_cents: SignedCents | None = None
    early_redemption_cost_cents: Cents | None = None
    proceeds_returned_cents: Cents | None = None
    market_value_cents: Cents | None = None
    early_redemption_allowed: StrictBool | None = None
    expected_interest_cents: SignedCents | None = None

    @model_validator(mode="after")
    def repo_schedule(self):
        if self.scheduled_maturity_at <= self.entered_at:
            raise ValueError("repo maturity must follow entry; no generic 24-hour lock is assumed")
        if self.source_type == "ORGANIZER_HISTORICAL" and (
                self.entered_at.time() != time(17) or self.scheduled_maturity_at != self.entered_at + timedelta(hours=15)):
            raise ValueError("organizer repo session is 17:00 to next-day 08:00")
        if self.early_redemption_at is not None and not self.entered_at <= self.early_redemption_at < self.scheduled_maturity_at:
            raise ValueError("early redemption must occur between entry and maturity")
        if self.status == "LOCKED" and self.liquidity.available_cents:
            raise ValueError("locked repo is not immediately available cash")
        if self.market_value_cents is not None and max(self.liquidity.available_cents,
                self.liquidity.locked_cents, self.liquidity.liquidatable_value_cents) > self.market_value_cents:
            raise ValueError("repo liquidity cannot exceed supplied current value")
        return self


class MarketPosition(Position):
    quantity: PositiveDecimal
    acquisition_price_index: PositiveDecimal
    acquired_at: Timestamp
    current_market_price_index: PositiveDecimal | None = None
    current_market_value_cents: Cents | None = None
    realized_pnl_cents: SignedCents | None = None
    unrealized_pnl_cents: SignedCents | None = None
    liquidation_haircut_pct: HaircutPct
    liquidation_cost_cents: Cents | None = None
    liquidation_proceeds_cents: Cents | None = None
    market_observation_timestamp: Timestamp | None = None
    status: Literal["OPEN", "CLOSED"]
    acquisition_cost_cents: Cents | None = None

    @model_validator(mode="after")
    def market_liquidity(self):
        if self.liquidity.available_cents:
            raise ValueError("an unsold market position is liquidatable, not Tier 0 cash")
        if self.current_market_value_cents is not None and max(self.liquidity.locked_cents,
                self.liquidity.liquidatable_value_cents) > self.current_market_value_cents:
            raise ValueError("liquidatable proceeds cannot exceed supplied market value")
        return self


class BondPosition(MarketPosition):
    tier: Literal[2] = 2
    supplied_yield_pct: ExactDecimal
    modified_duration: PositiveDecimal
    tenor_years: Literal[2] = 2
    contractual_maturity_at: Timestamp | None = None

    @field_validator("tenor_years", mode="before")
    @classmethod
    def strict_tenor(cls, value):
        if type(value) is not int:
            raise ValueError("tenor is the integer 2-year instrument label")
        return value

    @model_validator(mode="after")
    def maturity_order(self):
        if self.contractual_maturity_at is not None and self.contractual_maturity_at <= self.acquired_at:
            raise ValueError("supplied bond maturity must follow acquisition")
        return self


class EquityPosition(MarketPosition):
    tier: Literal[3] = 3
    supplied_volatility_pct: NonnegativeDecimal


TreasuryPosition = Annotated[CashPosition | RepoPosition | BondPosition | EquityPosition, Field(discriminator="tier")]


class OverdraftLiability(PortfolioSource):
    id: UUID
    borrowed_at: Timestamp
    borrowed_cents: Cents
    outstanding_principal_cents: Cents
    repaid_principal_cents: Cents
    apr_pct: NonnegativeDecimal
    financing_cost_cents: Cents | None = None
    paid_financing_cost_cents: Cents | None = None
    outstanding_financing_cost_cents: Cents | None = None
    breach_id: UUID
    reference_id: Name

    @model_validator(mode="after")
    def principal_identity(self):
        if self.borrowed_cents != self.outstanding_principal_cents + self.repaid_principal_cents:
            raise ValueError("borrowed principal must equal outstanding plus repaid principal")
        paid, unpaid = self.paid_financing_cost_cents, self.outstanding_financing_cost_cents
        if (paid is None) != (unpaid is None):
            raise ValueError("paid and outstanding financing cost must be supplied together")
        if paid is not None and (self.financing_cost_cents is None or paid + unpaid != self.financing_cost_cents):
            raise ValueError("incurred financing cost must equal paid plus outstanding cost")
        return self


class PortfolioValuation(PortfolioSource):
    valued_at: Timestamp
    tier0_cash_cents: Cents
    tier1_principal_cents: Cents
    tier1_value_cents: Cents
    tier2_market_value_cents: Cents
    tier3_market_value_cents: Cents
    total_portfolio_value_cents: Cents
    immediately_available_cents: Cents
    liquidatable_value_cents: Cents
    restricted_value_cents: Cents
    liabilities_cents: Cents
    net_portfolio_value_cents: SignedCents
    reference_id: Name

    @model_validator(mode="after")
    def valuation_identities(self):
        if self.total_portfolio_value_cents != (self.tier0_cash_cents + self.tier1_value_cents
                + self.tier2_market_value_cents + self.tier3_market_value_cents):
            raise ValueError("total assets must equal the four tier values")
        if self.net_portfolio_value_cents != self.total_portfolio_value_cents - self.liabilities_cents:
            raise ValueError("net portfolio value must deduct liabilities")
        if max(self.immediately_available_cents, self.liquidatable_value_cents, self.restricted_value_cents) > self.total_portfolio_value_cents:
            raise ValueError("liquidity values cannot exceed gross portfolio assets")
        return self


def _same_source(parent, child):
    if any(getattr(parent, field) != getattr(child, field)
           for field in ("run_id", "source_type", "dataset_id", "time_basis")):
        raise ValueError("nested records must belong to the same run, dataset and time basis")


class PortfolioState(PortfolioSource):
    """One authoritative current four-tier context; never projected into v1 vaults."""
    as_of: Timestamp
    native_interval_seconds: Annotated[StrictInt, Field(gt=0)]
    currency: Annotated[str, Field(strict=True, pattern=r"^[A-Z]{3}$")]
    cash: CashPosition
    repo_positions: tuple[RepoPosition, ...] = ()
    bond_positions: tuple[BondPosition, ...] = ()
    equity_positions: tuple[EquityPosition, ...] = ()
    overdrafts: tuple[OverdraftLiability, ...] = ()
    valuation: PortfolioValuation
    market_rates: MarketRateObservation | None = None
    market_prices: MarketPriceObservation | None = None

    @model_validator(mode="after")
    def coherent_snapshot(self):
        if self.source_type == "ORGANIZER_HISTORICAL" and self.native_interval_seconds != 3600:
            raise ValueError("organizer historical observations remain hourly; never fabricate 15-minute rows")
        if self.source_type == "ORGANIZER_HISTORICAL" and self.currency != "USD":
            raise ValueError("organizer USD data cannot be silently denominated in another currency")
        positions = (self.cash, *self.repo_positions, *self.bond_positions, *self.equity_positions)
        records = (*positions, *self.overdrafts, self.valuation)
        if len({p.id for p in (*positions, *self.overdrafts)}) != len(positions) + len(self.overdrafts):
            raise ValueError("position/liability IDs must be unique within the snapshot")
        for record in (self, *records):
            _same_source(self, record)
            for name in ("source_observation_timestamp", "entered_at", "acquired_at", "borrowed_at", "market_observation_timestamp"):
                value = getattr(record, name, None)
                if value is not None and value > self.as_of:
                    raise ValueError("current state cannot reference future observations or acquisitions")
        if any(p.status == "REDEEMED" for p in self.repo_positions) or any(
                p.status != "OPEN" for p in (*self.bond_positions, *self.equity_positions)):
            raise ValueError("current portfolio holds only unsettled repo/open market positions; keep closed records in history")
        if any(p.market_value_cents is None for p in self.repo_positions) or any(
                p.current_market_value_cents is None for p in (*self.bond_positions, *self.equity_positions)):
            raise ValueError("a complete portfolio snapshot requires supplied current valuations")
        v = self.valuation
        if v.valued_at != self.as_of:
            raise ValueError("portfolio and valuation times must agree")
        expected = (self.cash.balance_cents, sum(p.principal_cents for p in self.repo_positions),
                    sum(p.market_value_cents for p in self.repo_positions),
                    sum(p.current_market_value_cents for p in self.bond_positions),
                    sum(p.current_market_value_cents for p in self.equity_positions))
        actual = (v.tier0_cash_cents, v.tier1_principal_cents, v.tier1_value_cents,
                  v.tier2_market_value_cents, v.tier3_market_value_cents)
        if actual != expected:
            raise ValueError("valuation tier values must match the supplied positions")
        if (v.immediately_available_cents != sum(p.liquidity.available_cents for p in positions)
                or v.liquidatable_value_cents != sum(p.liquidity.liquidatable_value_cents for p in positions)
                or v.restricted_value_cents != sum(p.liquidity.locked_cents for p in positions)):
            raise ValueError("portfolio liquidity must reconcile with position liquidity")
        if any(p.outstanding_financing_cost_cents is None for p in self.overdrafts):
            raise ValueError("a complete portfolio requires explicit paid/unpaid financing costs, even if zero")
        if v.liabilities_cents != sum(p.outstanding_principal_cents + p.outstanding_financing_cost_cents for p in self.overdrafts):
            raise ValueError("liabilities must equal outstanding principal plus unpaid financing costs exactly")
        for quote in (self.market_rates, self.market_prices):
            if quote is not None and (quote.time_basis != self.time_basis or quote.observed_at > self.as_of):
                raise ValueError("market quotes must share the portfolio time basis and cannot be from the future")
        if self.market_prices is not None:
            quote = self.market_prices
            for position in (*self.bond_positions, *self.equity_positions):
                price = quote.bond_price_index if position.tier == 2 else quote.equity_index_price
                if position.market_observation_timestamp != quote.observed_at or position.current_market_price_index != price:
                    raise ValueError("current position marks must match the supplied market price observation")
            if any(p.modified_duration != quote.bond_modified_duration_years for p in self.bond_positions):
                raise ValueError("bond duration must match the supplied market observation")
        if self.market_rates is not None:
            quote = self.market_rates
            if any(p.supplied_yield_pct != quote.bond_yield_pct for p in self.bond_positions) or any(
                    p.supplied_volatility_pct != quote.equity_volatility_pct for p in self.equity_positions):
                raise ValueError("current bond yield/equity volatility must match supplied risk observations")
        return self


# Alias, not a second portfolio definition.
PortfolioTreasuryContext = PortfolioState


class TierAllocationLimit(Contract):
    tier: Literal[0, 1, 2, 3]
    max_allocation_bps: Bps
    min_allocation_bps: Bps = 0

    @field_validator("tier", mode="before")
    @classmethod
    def strict_tier(cls, value):
        if type(value) is not int:
            raise ValueError("tier must be an integer")
        return value

    @model_validator(mode="after")
    def ordered_bounds(self):
        if self.min_allocation_bps > self.max_allocation_bps:
            raise ValueError("minimum tier allocation cannot exceed maximum")
        return self


class FourTierTreasuryPolicy(TreasuryPolicy):
    repo_sweep_window_open: bool = Field(strict=True)
    allow_early_repo_redemption: bool = Field(default=False, strict=True)
    allow_bond_liquidation: bool = Field(default=False, strict=True)
    allow_emergency_equity_liquidation: bool = Field(default=False, strict=True)
    tier_limits: tuple[TierAllocationLimit, ...] = ()
    minimum_liquid_reserve_cents: Cents = 0
    max_estimated_loss_cents: Cents | None = None
    allow_overdraft: StrictBool = False
    max_overdraft_cents: Cents = 0
    bond_risk_method: Literal["observed_index_with_separate_duration_stress"] = "observed_index_with_separate_duration_stress"

    @model_validator(mode="after")
    def unique_limits(self):
        if len({limit.tier for limit in self.tier_limits}) != len(self.tier_limits):
            raise ValueError("tier allocation limits must be unique")
        if len(self.tier_limits) == 4 and not sum(v.min_allocation_bps for v in self.tier_limits) <= 10000 <= sum(v.max_allocation_bps for v in self.tier_limits):
            raise ValueError("the four exposure bounds must permit a full allocation")
        if not self.allow_overdraft and self.max_overdraft_cents:
            raise ValueError("disabled overdraft cannot have a positive policy limit")
        return self


class CostBreakdown(Contract):
    liquidation_fee_cents: Cents = 0
    repo_break_fee_cents: Cents = 0
    transaction_cost_cents: Cents = 0
    funding_cost_cents: Cents = 0

    @property
    def total_cents(self):
        return self.liquidation_fee_cents + self.repo_break_fee_cents + self.transaction_cost_cents + self.funding_cost_cents


class AllocationTargets(Contract):
    tier0_target_cents: Cents
    tier1_allocation_cents: Cents
    tier2_allocation_cents: Cents
    tier3_allocation_cents: Cents

    @property
    def amounts(self):
        return (self.tier0_target_cents, self.tier1_allocation_cents, self.tier2_allocation_cents, self.tier3_allocation_cents)


class InstrumentReturnEstimate(Contract):
    instrument: InstrumentId
    horizon_hours: PositiveInt
    expected_income_cents: SignedCents
    expected_price_change_cents: SignedCents
    expected_costs: CostBreakdown
    estimated_stress_loss_cents: Cents
    estimate_basis: Name
    realized: Literal[False] = False

    @field_validator("realized", mode="before")
    @classmethod
    def not_realized(cls, value):
        if value is not False:
            raise ValueError("expected return estimates cannot be labeled realized")
        return value


class ForecastRiskMetadata(TimedPortfolioContract):
    model_version: Name
    generated_at: Timestamp
    training_data_through: Timestamp
    granularity_hours: Literal[1] = 1
    net_flow_target: Literal["source_net_flow_usd"] = "source_net_flow_usd"
    uncertainty_status: Literal["not_evaluated", "provisional_uncalibrated", "evaluated"]
    evaluation_reference: Name | None = None
    notes: tuple[Name, ...] = ()

    @field_validator("granularity_hours", mode="before")
    @classmethod
    def strict_granularity(cls, value):
        if type(value) is not int:
            raise ValueError("native forecast granularity is integer 1 hour")
        return value

    @model_validator(mode="after")
    def honest_metadata(self):
        if self.training_data_through > self.generated_at:
            raise ValueError("training data cannot come from the future")
        if (self.uncertainty_status == "evaluated") != (self.evaluation_reference is not None):
            raise ValueError("only evaluated status has a supplied evaluation reference")
        return self


class HourlyForecastPoint(TimedPortfolioContract):
    start_at: Timestamp
    predicted_deposits_cents: Cents
    predicted_withdrawals_cents: Cents
    predicted_net_flow_cents: SignedCents
    supplied_uncertainty_buffer_cents: Cents

    @field_validator("start_at")
    @classmethod
    def hourly(cls, value):
        if value.minute or value.second or value.microsecond:
            raise ValueError("forecast input remains on native hourly boundaries")
        return value


class FourTierRecommendationRequest(BaseModel):
    model_config = Contract.model_config
    request_id: Name
    portfolio: PortfolioState
    history: Annotated[tuple[OrganizerHourlyObservation, ...], Field(min_length=1)]
    policy: FourTierTreasuryPolicy
    metadata: ForecastRiskMetadata
    forecast: Annotated[tuple[HourlyForecastPoint, ...], Field(min_length=1)]
    # Caller attestation: the entire supplied historical batch was available then.
    history_available_at: Timestamp

    @model_validator(mode="after")
    def causal_history(self):
        p = self.portfolio
        if p.source_type != "ORGANIZER_HISTORICAL":
            raise ValueError("this source-history envelope is organizer historical only")
        if self.history_available_at.tzinfo is not None:
            raise ValueError("source availability uses the same unspecified historical clock")
        if not self.history[-1].timestamp <= self.history_available_at <= p.as_of:
            raise ValueError("caller must attest that the full history was available by decision time")
        if self.history[-1].timestamp != p.source_observation_timestamp:
            raise ValueError("latest history and portfolio source reference must agree")
        if p.market_rates is None or p.market_prices is None:
            raise ValueError("historical recommendation input requires source-backed market quotes")
        last = self.history[-1]
        rates, prices = p.market_rates, p.market_prices
        if (rates.observed_at != last.timestamp or prices.observed_at != last.timestamp
                or rates.repo_apy_pct != last.tier1_repo_rate_apy
                or rates.bond_yield_pct != last.tier2_bond_yield_pct
                or rates.equity_volatility_pct != last.tier3_stock_volatility_pct
                or rates.overdraft_apr_pct != last.emergency_overdraft_penalty_apr_pct
                or prices.bond_price_index != last.tier2_bond_price_index
                or prices.bond_modified_duration_years != last.tier2_bond_mod_duration
                or prices.equity_index_price != last.tier3_stock_index_price):
            raise ValueError("market quotes must preserve the latest referenced source observation")
        if any(b.timestamp - a.timestamp != timedelta(hours=1) for a, b in zip(self.history, self.history[1:])):
            raise ValueError("source history must be ordered and contiguous hourly observations")
        if (self.metadata.time_basis != p.time_basis or self.metadata.generated_at != p.as_of
                or self.metadata.training_data_through > self.history[-1].timestamp):
            raise ValueError("metadata must match the portfolio clock and available history")
        if any(f.time_basis != p.time_basis or f.start_at < p.as_of for f in self.forecast):
            raise ValueError("forecast input must share the source clock and cannot be in the past")
        if any(b.start_at - a.start_at != timedelta(hours=1) for a, b in zip(self.forecast, self.forecast[1:])):
            raise ValueError("forecast inputs must be contiguous hourly points")
        return self


class FourTierReserveResult(ReserveResult):
    """Reuse v1 reserve components/identity, but make timestamp basis explicit."""
    as_of: Timestamp
    time_basis: TimeBasis

    @field_validator("*", mode="after")
    @classmethod
    def utc_only(cls, value):
        return value

    @model_validator(mode="after")
    def explicit_time_basis(self):
        return _check_times(self)


class RecommendedOrder(PortfolioSource):
    id: UUID
    as_of: Timestamp
    recommendation_only: Literal[True] = True
    action: Literal["INVEST_REPO", "REDEEM_REPO", "BUY_BONDS", "SELL_BONDS", "BUY_EQUITIES",
                    "SELL_EQUITIES", "BORROW_OVERDRAFT", "REPAY_OVERDRAFT"]
    tier: Literal[0, 1, 2, 3]
    position_id: UUID | None = None
    amount_cents: Annotated[StrictInt, Field(gt=0)]
    quantity: PositiveDecimal | None = None
    estimated_cost_cents: Cents | None = None
    expected_proceeds_cents: Cents | None = None
    reason: Name
    execution_status: Literal["NOT_EXECUTED"] = "NOT_EXECUTED"
    earliest_execution_at: Timestamp | None = None
    expected_settlement_at: Timestamp | None = None
    expected_maturity_at: Timestamp | None = None
    expected_costs: CostBreakdown | None = None

    @field_validator("tier", mode="before")
    @classmethod
    def strict_tier(cls, value):
        if type(value) is not int:
            raise ValueError("tier must be an integer")
        return value

    @model_validator(mode="after")
    def instrument_action(self):
        tiers = {"INVEST_REPO": 1, "REDEEM_REPO": 1, "BUY_BONDS": 2, "SELL_BONDS": 2,
                 "BUY_EQUITIES": 3, "SELL_EQUITIES": 3, "BORROW_OVERDRAFT": 0, "REPAY_OVERDRAFT": 0}
        if self.tier != tiers[self.action]:
            raise ValueError("order action and tier must identify the same instrument")
        if self.action in ("REDEEM_REPO", "SELL_BONDS", "SELL_EQUITIES", "REPAY_OVERDRAFT") and self.position_id is None:
            raise ValueError("redemptions/sales/repayments require an existing position or liability ID")
        if self.quantity is not None and self.tier not in (2, 3):
            raise ValueError("quantity applies only to market instruments")
        if self.expected_costs is not None and (self.estimated_cost_cents is None or self.estimated_cost_cents != self.expected_costs.total_cents):
            raise ValueError("supplied total cost must equal the fee/funding breakdown, excluding market P&L")
        start, end = self.earliest_execution_at, self.expected_settlement_at
        if (start is None) != (end is None):
            raise ValueError("execution and settlement estimates must be supplied together")
        if start is not None and (start < self.as_of or end < start):
            raise ValueError("execution cannot precede decision; settlement cannot precede execution")
        if self.expected_maturity_at is not None and self.action != "INVEST_REPO":
            raise ValueError("only a new repo investment specifies a new maturity")
        if self.action == "INVEST_REPO" and self.source_type == "ORGANIZER_HISTORICAL" and start is None:
            raise ValueError("organizer repo investment requires explicit entry, settlement and maturity")
        if self.action == "INVEST_REPO" and start is not None:
            if self.expected_maturity_at is None or self.expected_maturity_at <= end:
                raise ValueError("scheduled repo order requires maturity after settlement")
            if self.source_type == "ORGANIZER_HISTORICAL" and (start.time() != time(17) or end != start
                    or self.expected_maturity_at != start + timedelta(hours=15)):
                raise ValueError("organizer repo order enters at 17:00 and matures next-day 08:00")
        if self.expected_maturity_at is not None and start is None:
            raise ValueError("maturity estimate requires the matching execution/settlement schedule")
        return self


class FourTierDecisionResult(PortfolioSource):
    as_of: Timestamp
    recommendation_only: Literal[True] = True
    action: Literal["HOLD", "ALLOCATE", "LIQUIDITY_WARNING"]
    reserve: FourTierReserveResult
    orders: tuple[RecommendedOrder, ...] = ()
    reason: Name
    execution_status: Literal["NOT_EXECUTED"] = "NOT_EXECUTED"
    request_id: Name | None = None
    feasible: StrictBool | None = None
    allocation_budget_cents: Cents | None = None
    targets: AllocationTargets | None = None
    target_overdraft_principal_cents: Cents | None = None
    expected_costs: CostBreakdown | None = None
    estimated_market_risk_loss_cents: Cents | None = None
    instrument_returns: tuple[InstrumentReturnEstimate, ...] = ()
    policy: FourTierTreasuryPolicy | None = None
    metadata: ForecastRiskMetadata | None = None
    explanations: tuple[Name, ...] = ()

    @model_validator(mode="after")
    def recommendation_plan(self):
        if self.reserve.as_of != self.as_of or self.reserve.time_basis != self.time_basis:
            raise ValueError("decision and reserve time/basis must agree")
        if bool(self.orders) != (self.action == "ALLOCATE"):
            raise ValueError("only ALLOCATE has orders; HOLD/warnings cannot imply execution")
        if len({order.id for order in self.orders}) != len(self.orders):
            raise ValueError("recommended order IDs must be unique")
        for order in self.orders:
            _same_source(self, order)
            if order.as_of != self.as_of:
                raise ValueError("order and decision times must agree")
        if (self.targets is None) != (self.allocation_budget_cents is None):
            raise ValueError("targets and their supplied gross asset budget must be given together")
        if self.targets is not None and sum(self.targets.amounts) != self.allocation_budget_cents:
            raise ValueError("four asset targets must sum to budget; borrowing is a separate liability")
        if self.action == "LIQUIDITY_WARNING" and self.feasible is True or self.action == "ALLOCATE" and self.feasible is False:
            raise ValueError("action cannot contradict the supplied feasibility assessment")
        if len({r.instrument for r in self.instrument_returns}) != len(self.instrument_returns):
            raise ValueError("instrument return estimates must be unique")
        if self.metadata is not None and (self.metadata.time_basis != self.time_basis or self.metadata.generated_at != self.as_of
                or self.source_observation_timestamp is not None and self.metadata.training_data_through > self.source_observation_timestamp):
            raise ValueError("recommendation metadata must match its time, basis and source cutoff")
        if self.feasible is True:
            if self.targets is None or self.target_overdraft_principal_cents is None or self.policy is None:
                raise ValueError("feasibility requires explicit asset targets, debt target and policy")
            minimum = max(self.reserve.required_reserve_cents, self.policy.minimum_liquid_reserve_cents if self.policy else 0)
            if self.targets.tier0_target_cents < minimum:
                raise ValueError("feasible cash target must cover the supplied minimum reserve")
            if self.policy is not None:
                for limit in self.policy.tier_limits:
                    amount = self.targets.amounts[limit.tier]
                    if not limit.min_allocation_bps * self.allocation_budget_cents <= amount * 10000 <= limit.max_allocation_bps * self.allocation_budget_cents:
                        raise ValueError("feasible target violates a supplied exposure bound")
                if self.target_overdraft_principal_cents > self.policy.max_overdraft_cents:
                    raise ValueError("feasible debt target exceeds the explicit overdraft policy")
                if self.policy.max_estimated_loss_cents is not None and (self.estimated_market_risk_loss_cents is None
                        or self.estimated_market_risk_loss_cents > self.policy.max_estimated_loss_cents):
                    raise ValueError("feasibility requires a supplied risk estimate within policy")
        return self


def recommend_portfolio_allocation(request: FourTierRecommendationRequest) -> FourTierDecisionResult:
    """Shared declaration only; no optimizer, legacy-vault adapter or execution."""
    raise NotImplementedError("RJ-M1-06 defines four-tier contracts only")
