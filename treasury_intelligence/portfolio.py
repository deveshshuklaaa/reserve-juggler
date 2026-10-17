"""Canonical four-tier wire contracts; supplied state, never financial execution.

Field names/units follow Member 2 migration 003. The v1 generic-vault engine is
deliberately not an implicit adapter for these instrument-specific contracts.
"""
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, BeforeValidator, Field, StrictInt, field_validator, model_validator

from .types import Bps, Cents, Contract, Name, ReserveResult, TreasuryPolicy


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

    @model_validator(mode="after")
    def repo_schedule(self):
        if self.scheduled_maturity_at <= self.entered_at:
            raise ValueError("repo maturity must follow entry; no generic 24-hour lock is assumed")
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
    breach_id: UUID
    reference_id: Name

    @model_validator(mode="after")
    def principal_identity(self):
        if self.borrowed_cents != self.outstanding_principal_cents + self.repaid_principal_cents:
            raise ValueError("borrowed principal must equal outstanding plus repaid principal")
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

    @model_validator(mode="after")
    def coherent_snapshot(self):
        if self.source_type == "ORGANIZER_HISTORICAL" and self.native_interval_seconds != 3600:
            raise ValueError("organizer historical observations remain hourly; never fabricate 15-minute rows")
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
        if v.liabilities_cents < sum(p.outstanding_principal_cents for p in self.overdrafts):
            raise ValueError("portfolio valuation cannot omit outstanding overdraft principal")
        return self


# Alias, not a second portfolio definition.
PortfolioTreasuryContext = PortfolioState


class TierAllocationLimit(Contract):
    tier: Literal[1, 2, 3]
    max_allocation_bps: Bps

    @field_validator("tier", mode="before")
    @classmethod
    def strict_tier(cls, value):
        if type(value) is not int:
            raise ValueError("tier must be an integer")
        return value


class FourTierTreasuryPolicy(TreasuryPolicy):
    repo_sweep_window_open: bool = Field(strict=True)
    allow_early_repo_redemption: bool = Field(default=False, strict=True)
    allow_bond_liquidation: bool = Field(default=False, strict=True)
    allow_emergency_equity_liquidation: bool = Field(default=False, strict=True)
    tier_limits: tuple[TierAllocationLimit, ...] = ()

    @model_validator(mode="after")
    def unique_limits(self):
        if len({limit.tier for limit in self.tier_limits}) != len(self.tier_limits):
            raise ValueError("tier allocation limits must be unique")
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
        return self


class FourTierDecisionResult(PortfolioSource):
    as_of: Timestamp
    recommendation_only: Literal[True] = True
    action: Literal["HOLD", "ALLOCATE", "LIQUIDITY_WARNING"]
    reserve: FourTierReserveResult
    orders: tuple[RecommendedOrder, ...] = ()
    reason: Name

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
        return self
