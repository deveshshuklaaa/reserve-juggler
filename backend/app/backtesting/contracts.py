"""Immutable, cents-safe service and hourly-receipt contracts."""
from datetime import datetime, timedelta
import json
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator

JS_MAX = 9_007_199_254_740_991
Money = Annotated[StrictInt, Field(ge=-JS_MAX, le=JS_MAX)]
Cash = Annotated[StrictInt, Field(ge=0, le=JS_MAX)]
Count = Annotated[StrictInt, Field(ge=0, le=JS_MAX)]
Strategy = Literal["STATIC", "REACTIVE", "RESERVE_JUGGLER"]
Scenario = Literal["NORMAL", "HIGH_WITHDRAWAL", "LOW_DEPOSIT", "SETTLEMENT_DELAY", "LIQUIDITY_SHOCK"]
STRATEGIES = ("STATIC", "REACTIVE", "RESERVE_JUGGLER")
SCENARIOS = ("NORMAL", "HIGH_WITHDRAWAL", "LOW_DEPOSIT", "SETTLEMENT_DELAY", "LIQUIDITY_SHOCK")


def canonical_config(value: str) -> str:
    def pairs(items):
        result = {}
        for key, item in items:
            if key in result:
                raise ValueError("Duplicate configuration key")
            result[key] = item
        return result

    parsed = json.loads(value, object_pairs_hook=pairs)
    if not isinstance(parsed, dict):
        raise ValueError("Configuration must be a JSON object")

    def check(item):
        if item is None or isinstance(item, (str, bool)):
            return
        if type(item) is int and abs(item) <= JS_MAX:
            return
        if isinstance(item, list):
            for child in item:
                check(child)
            return
        if isinstance(item, dict):
            for child in item.values():
                check(child)
            return
        raise ValueError("Configuration numbers must be safe integers; encode exact Decimal inputs as strings")

    check(parsed)
    return json.dumps(parsed, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class Contract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", validate_default=True, revalidate_instances="always")

    @field_validator("*", mode="before")
    @classmethod
    def explicit_timestamp(cls, value, info):
        if info.field_name in {"start", "end_exclusive", "timestamp"} and not isinstance(value, (str, datetime)):
            raise ValueError("Use an explicit naive ISO timestamp or datetime")
        return value

    @field_validator("*", mode="after")
    @classmethod
    def source_clock(cls, value):
        if isinstance(value, datetime) and (
            value.tzinfo is not None or value.minute or value.second or value.microsecond
        ):
            raise ValueError("Organizer time is naive and hourly; do not attach a timezone")
        return value


class ScenarioSpec(Contract):
    name: Scenario = "NORMAL"
    parameters_json: str = "{}"

    @field_validator("parameters_json")
    @classmethod
    def canonical_parameters(cls, value):
        return canonical_config(value)


class BacktestRequest(Contract):
    comparison_id: UUID
    start: datetime
    days: Literal[7, 14, 30]
    initial_capital_cents: Cash
    seed: Count
    scenario: ScenarioSpec = Field(default_factory=ScenarioSpec)
    policy_json: str = "{}"
    strategies: tuple[Strategy, ...] = STRATEGIES

    @field_validator("strategies")
    @classmethod
    def selected_strategies(cls, value):
        if not value or len(set(value)) != len(value):
            raise ValueError("Select one or more unique strategies in the desired order")
        return value

    @field_validator("days", mode="before")
    @classmethod
    def strict_days(cls, value):
        if type(value) is not int:
            raise ValueError("days must be integer 7, 14 or 30")
        return value

    @field_validator("policy_json")
    @classmethod
    def canonical_policy(cls, value):
        return canonical_config(value)

    @property
    def steps(self):
        return self.days * 24

    @property
    def end_exclusive(self):
        return self.start + timedelta(hours=self.steps)


class EngineState(Contract):
    checking_cents: Cash
    tier1_value_cents: Cash
    tier2_value_cents: Cash
    tier3_value_cents: Cash
    borrowing_outstanding_cents: Cash
    unpaid_borrowing_costs_cents: Cash
    accrued_interest_cents: Money
    unrealized_market_pnl_cents: Money
    net_asset_value_cents: Money

    @model_validator(mode="after")
    def balance_sheet(self):
        gross = self.checking_cents + self.tier1_value_cents + self.tier2_value_cents + self.tier3_value_cents
        if gross > JS_MAX:
            raise ValueError("Gross assets exceed safe integer range")
        if self.net_asset_value_cents != gross - self.borrowing_outstanding_cents - self.unpaid_borrowing_costs_cents:
            raise ValueError("NAV must deduct outstanding principal and unpaid financing cost")
        return self


class HourReceipt(Contract):
    """Actual deltas, never cumulative earnings; state fields are closing stocks."""
    timestamp: datetime
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    opening: EngineState
    closing: EngineState
    customer_cash_delta_cents: Money
    investment_cash_delta_cents: Money
    financing_cash_delta_cents: Money
    realized_interest_cents: Money
    realized_market_pnl_cents: Money
    contractual_penalties_cents: Cash
    liquidation_losses_cents: Cash
    transaction_costs_cents: Cash
    borrowing_costs_cents: Cash
    paid_borrowing_costs_cents: Cash
    reserve_breaches: Count
    emergency_events: Count
    failed_payouts: Count
    unpaid_payouts_cents: Cash
    sweeps: Count
    event_ids: tuple[str, ...]

    @model_validator(mode="after")
    def accounting(self):
        a, b = self.opening, self.closing
        fees = self.contractual_penalties_cents + self.liquidation_losses_cents + self.transaction_costs_cents
        cash = (a.checking_cents + self.customer_cash_delta_cents + self.investment_cash_delta_cents
                + self.financing_cash_delta_cents + self.realized_interest_cents
                - fees - self.paid_borrowing_costs_cents)
        if b.checking_cents != cash:
            raise ValueError("Cash delta does not reconcile with posted cash legs")
        if b.borrowing_outstanding_cents != a.borrowing_outstanding_cents + self.financing_cash_delta_cents:
            raise ValueError("Borrowing/repayment cash must reconcile to principal, never income")
        if b.unpaid_borrowing_costs_cents != a.unpaid_borrowing_costs_cents + self.borrowing_costs_cents - self.paid_borrowing_costs_cents:
            raise ValueError("Financing cost incurred/paid/unpaid does not reconcile")
        benefit = (self.realized_interest_cents + self.realized_market_pnl_cents
                   + b.accrued_interest_cents - a.accrued_interest_cents
                   + b.unrealized_market_pnl_cents - a.unrealized_market_pnl_cents
                   - fees - self.borrowing_costs_cents)
        if b.net_asset_value_cents - a.net_asset_value_cents - self.customer_cash_delta_cents != benefit:
            raise ValueError("Economic result does not reconcile to NAV excluding customer flows")
        if len(set(self.event_ids)) != len(self.event_ids) or any(not key.strip() for key in self.event_ids):
            raise ValueError("Audit event IDs must be nonblank and unique")
        deltas = (self.customer_cash_delta_cents, self.investment_cash_delta_cents,
                  self.financing_cash_delta_cents, self.realized_interest_cents,
                  self.realized_market_pnl_cents, fees, self.borrowing_costs_cents,
                  self.paid_borrowing_costs_cents, self.reserve_breaches,
                  self.emergency_events, self.failed_payouts, self.unpaid_payouts_cents, self.sweeps)
        if not self.event_ids and (a != b or any(deltas)):
            raise ValueError("Financial changes and counted events require audit event IDs")
        return self


class HistoryPoint(Contract):
    timestamp: datetime
    checking_cents: Cash


class AccountingTotals(Contract):
    realized_interest_cents: Money
    average_checking_cents: Cash
    average_invested_cents: Cash
    penalties_cents: Cash
    borrowing_costs_cents: Cash
    borrowing_outstanding_cents: Cash
    reserve_breaches: Count
    emergency_events: Count
    failed_payouts: Count
    unpaid_payouts_cents: Cash
    sweeps: Count
    net_benefit_cents: Money
    # Honest supplementary accounting: no debt draw or market gain disguised as interest.
    contractual_penalties_cents: Cash
    liquidation_losses_cents: Cash
    transaction_costs_cents: Cash
    realized_market_pnl_cents: Money
    accrued_interest_cents: Money
    unrealized_market_pnl_cents: Money
    unpaid_borrowing_costs_cents: Cash
    ending_net_asset_value_cents: Money
    customer_cash_delta_cents: Money
    model_evaluation: None = None

    @model_validator(mode="after")
    def metric_identities(self):
        if self.penalties_cents != self.contractual_penalties_cents + self.liquidation_losses_cents:
            raise ValueError("Total penalties must retain separate contractual and liquidation costs")
        expected = (self.realized_interest_cents + self.accrued_interest_cents
                    + self.realized_market_pnl_cents + self.unrealized_market_pnl_cents
                    - self.penalties_cents - self.transaction_costs_cents - self.borrowing_costs_cents)
        if self.net_benefit_cents != expected:
            raise ValueError("Net benefit must include P&L and all incurred costs, not borrowing principal")
        return self


class AccountingMetrics(AccountingTotals):
    history: tuple[HistoryPoint, ...]

    @model_validator(mode="after")
    def checking_average(self):
        if not self.history:
            raise ValueError("Metrics need hourly checking history")
        quotient, remainder = divmod(sum(p.checking_cents for p in self.history), len(self.history))
        if self.average_checking_cents != quotient + int(2 * remainder >= len(self.history)):
            raise ValueError("Average checking must be the half-up rounded hourly closing mean")
        return self


class StrategyMetrics(AccountingMetrics):
    strategy: Strategy
    run_id: UUID


class ComparisonResult(Contract):
    comparison_id: UUID
    dataset_id: str
    dataset_sha256: str
    start: datetime
    end_exclusive: datetime
    steps: Literal[168, 336, 720]
    native_interval_seconds: Literal[3600] = 3600
    time_basis: Literal["UNSPECIFIED"] = "UNSPECIFIED"
    initial_capital_cents: Cash
    seed: Count
    scenario: ScenarioSpec
    policy_json: str
    conditions_sha256: str
    engine_version: str
    engine_integration_sha: str | None
    execution_kind: Literal["SHARED", "TEST_DOUBLE"]
    results: tuple[StrategyMetrics, ...]
    strategies: tuple[Strategy, ...] = STRATEGIES

    @model_validator(mode="after")
    def comparable(self):
        if (not self.strategies or len(set(self.strategies)) != len(self.strategies)
                or tuple(item.strategy for item in self.results) != self.strategies):
            raise ValueError("Return exactly the requested unique strategies in their declared order")
        if len({item.run_id for item in self.results}) != len(self.strategies):
            raise ValueError("Strategy runs must be isolated")
        if self.end_exclusive - self.start != timedelta(hours=self.steps):
            raise ValueError("Window length and steps must agree")
        expected_times = tuple(self.start + timedelta(hours=i) for i in range(self.steps))
        for item in self.results:
            if tuple(p.timestamp for p in item.history) != expected_times:
                raise ValueError("History must contain exactly one closing point for each source hour")
            if item.ending_net_asset_value_cents - self.initial_capital_cents - item.customer_cash_delta_cents != item.net_benefit_cents:
                raise ValueError("Net benefit must reconcile with the comparison's initial capital")
        return self
