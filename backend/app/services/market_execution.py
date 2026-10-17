"""Whole-position emergency sales used ONLY by the shared hourly executor.

Member 1's scalar economics helpers supply market marks and source haircuts.
These functions post real financial evidence; they are not a backtest simulator.
"""
from datetime import timedelta
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, localcontext
from uuid import uuid4, uuid5

from sqlalchemy import select

from app.persistence.models import BondPosition, EquityPosition, InvestmentMovement, LedgerEntry, PositionValuation
from app.services.accounting import market_cost_basis
from treasury_intelligence.instrument_economics import (
    calculate_bond_economics, calculate_equity_economics, percentage_cost_cents, usd_to_ledger_cents,
)
from treasury_intelligence.portfolio import CostBreakdown, RecommendedOrder

SAFE_CENTS = 2**53 - 1


class TradeRejected(ValueError):
    """A recommendation could not be filled; no financial legs were posted."""


def record_market_valuation(session, run, position, observation, realized_delta=0):
    """One closing mark per lot/hour; sale P&L is an event delta, not a stock."""
    bond = isinstance(position, BondPosition)
    link = dict(tier=2 if bond else 3, bond_position_id=position.id if bond else None,
                equity_position_id=None if bond else position.id)
    column = PositionValuation.bond_position_id if bond else PositionValuation.equity_position_id
    close = observation.timestamp + timedelta(hours=1)
    value = session.scalar(select(PositionValuation).where(
        PositionValuation.run_id == run.id, column == position.id, PositionValuation.valued_at == close))
    if value is None:
        value = PositionValuation(id=uuid4(), run_id=run.id, **link,
            source_type=run.source_type, dataset_id=run.dataset_id,
            source_observation_timestamp=observation.timestamp, valued_at=close,
            reference_id=f"market-mark-{position.id}-{close.isoformat()}", realized_pnl_cents=0)
        session.add(value)
    value.market_price_index = position.current_market_price_index
    value.market_value_cents = position.current_market_value_cents
    value.unrealized_pnl_cents = position.unrealized_pnl_cents
    value.realized_pnl_cents = (value.realized_pnl_cents or 0) + realized_delta
    session.flush()


def execute_market_order(session, run, cash, instruction, observation, step, minimum_cash_cents=0):
    """Fill a canonical market order atomically in the caller's transaction.

    One USD per index-point per unit matches the existing canonical adapter.
    Buys round debit up, sales round gross proceeds down; costs round up.
    Source liquidation haircuts also apply to recommendation-driven sales.
    """
    try:
        instruction = RecommendedOrder.model_validate(instruction.model_dump())
    except (ValueError, TypeError, AttributeError) as error:
        raise TradeRejected(f"Invalid canonical recommendation: {error}") from error
    o = instruction
    if o.action not in {"BUY_BONDS", "SELL_BONDS", "BUY_EQUITIES", "SELL_EQUITIES"}:
        raise TradeRejected("Not a market trade")
    if (o.run_id != run.id or cash.run_id != run.id or o.dataset_id != run.dataset_id
            or o.source_type != run.source_type or observation.dataset_id != run.dataset_id
            or o.time_basis != "UNSPECIFIED" or o.as_of > observation.timestamp
            or o.source_observation_timestamp is None
            or o.source_observation_timestamp > observation.timestamp):
        raise TradeRejected("Run, source, or decision-time mismatch")
    if (o.earliest_execution_at is not None and
            (o.earliest_execution_at > observation.timestamp or o.expected_settlement_at > observation.timestamp)):
        raise TradeRejected("Deferred market settlement is not implemented")
    if o.amount_cents > SAFE_CENTS or (o.estimated_cost_cents or 0) > SAFE_CENTS:
        raise TradeRejected("Unsafe integer-cent amount")
    costs = o.expected_costs or CostBreakdown()
    if o.expected_costs is None and o.estimated_cost_cents:
        raise TradeRejected("A nonzero estimated fee needs an explicit cost breakdown")
    if costs.repo_break_fee_cents or costs.funding_cost_cents:
        raise TradeRejected("Non-market costs cannot be silently charged as trade fees")
    reference = f"market-order-{o.id}"
    if session.scalar(select(InvestmentMovement.id).where(
            InvestmentMovement.run_id == run.id, InvestmentMovement.reference_id == reference)):
        raise TradeRejected("Recommendation already executed")
    bond = o.tier == 2
    model = BondPosition if bond else EquityPosition
    price = observation.tier2_bond_price_index if bond else observation.tier3_stock_index_price
    haircut = (observation.tier2_bond_liquidation_haircut_pct if bond
               else observation.tier3_stock_liquidation_haircut_pct)
    fee = costs.transaction_cost_cents
    buy = o.action.startswith("BUY_")
    with localcontext() as context:
        context.prec = 100
        if buy:
            if o.position_id is not None:
                raise TradeRejected("Purchases create distinct lots; existing-lot augmentation is unsupported")
            quantity = o.quantity if o.quantity is not None else (
                Decimal(o.amount_cents) / (price * 100)).quantize(Decimal("1e-18"), rounding=ROUND_FLOOR)
            principal = int((quantity * price * 100).to_integral_value(rounding=ROUND_CEILING))
            if quantity <= 0 or principal > o.amount_cents or principal + fee > cash.balance_cents - minimum_cash_cents:
                raise TradeRejected("Purchase exceeds its budget or available cash")
            gross, cost, released, realized = 0, 0, 0, 0
            remaining_basis = principal
            position = model(id=uuid5(run.id, str(o.id)), run_id=run.id,
                source_type=run.source_type, dataset_id=run.dataset_id,
                source_observation_timestamp=observation.timestamp,
                quantity=quantity, acquisition_price_index=price, acquired_at=observation.timestamp,
                current_market_price_index=price, current_market_value_cents=usd_to_ledger_cents(quantity * price),
                realized_pnl_cents=0, liquidation_haircut_pct=haircut,
                liquidation_cost_cents=0, liquidation_proceeds_cents=0,
                market_observation_timestamp=observation.timestamp, status="OPEN")
            position.unrealized_pnl_cents = position.current_market_value_cents - principal
            if bond:
                position.supplied_yield_pct = observation.tier2_bond_yield_pct
                position.modified_duration = observation.tier2_bond_mod_duration
            else:
                position.supplied_volatility_pct = observation.tier3_stock_volatility_pct
            delta = -principal
        else:
            position = session.get(model, o.position_id)
            if (position is None or position.run_id != run.id or position.status != "OPEN"
                    or position.acquired_at > observation.timestamp):
                raise TradeRejected("Sale requires an owned open position")
            quantity = o.quantity if o.quantity is not None else position.quantity
            if quantity > position.quantity:
                raise TradeRejected("Sale exceeds position quantity")
            whole_value = usd_to_ledger_cents(position.quantity * price)
            gross = int((Decimal(whole_value) * quantity / position.quantity).to_integral_value(rounding=ROUND_FLOOR))
            cost = percentage_cost_cents(gross, haircut)
            basis = market_cost_basis(session, position)
            released = basis if quantity == position.quantity else int(
                (Decimal(basis) * quantity / position.quantity).to_integral_value(rounding=ROUND_HALF_UP))
            remaining_basis = basis - released
            realized = gross - released
            principal = released
            delta = gross - cost
            if gross <= 0 or gross > o.amount_cents or delta < fee:
                raise TradeRejected("Sale exceeds its requested gross amount or cannot fund its fee")
        if any(abs(value) > SAFE_CENTS for value in (principal, gross, cost, delta, cash.balance_cents + delta - fee)):
            raise TradeRejected("Fill exceeds safe integer-cent range")
        # Validation is complete. No rejected order can leave partial financial legs.
        if buy:
            session.add(position)
        else:
            left = position.quantity - quantity
            position.status = "OPEN" if left else "CLOSED"
            if left:
                position.quantity = left
            position.current_market_price_index = price
            position.current_market_value_cents = usd_to_ledger_cents(left * price)
            position.unrealized_pnl_cents = position.current_market_value_cents - remaining_basis
            position.realized_pnl_cents = (position.realized_pnl_cents or 0) + realized
            position.liquidation_cost_cents = (position.liquidation_cost_cents or 0) + cost
            position.liquidation_proceeds_cents = (position.liquidation_proceeds_cents or 0) + delta
            position.market_observation_timestamp = observation.timestamp
        source = dict(run_id=run.id, source_type=run.source_type, dataset_id=run.dataset_id,
                      source_observation_timestamp=observation.timestamp)
        ledger_ids = []
        fill_ledger_id = None
        for entry_type, cash_delta, suffix in [
                ("MARKET_PURCHASE_DEBIT" if buy else "MARKET_LIQUIDATION_CREDIT", delta, "fill"),
                ("MARKET_TRANSACTION_FEE", -fee, "fee")]:
            if suffix == "fee" and not fee:
                continue
            before = cash.balance_cents
            cash.balance_cents += cash_delta
            entry = LedgerEntry(**source, id=uuid4(), step=step, timestamp=None,
                entry_type=entry_type, amount_cents=abs(cash_delta), balance_before_cents=before,
                balance_after_cents=cash.balance_cents, reference_id=f"{reference}-{suffix}",
                event_at=observation.timestamp)
            session.add(entry)
            session.flush()
            cash.last_ledger_entry_id = entry.id
            ledger_ids.append(str(entry.id))
            if suffix == "fill":
                fill_ledger_id = entry.id
        link = dict(tier=o.tier, bond_position_id=position.id if bond else None,
                    equity_position_id=None if bond else position.id)
        movement = InvestmentMovement(**source, **link, id=uuid4(),
            kind="INVESTMENT" if buy else "LIQUIDATION", occurred_at=observation.timestamp,
            cash_delta_cents=delta, principal_cents=principal, interest_cents=0,
            haircut_cost_cents=cost, ledger_entry_id=fill_ledger_id, reference_id=reference)
        session.add(movement)
        session.flush()
        record_market_valuation(session, run, position, observation, realized)
        return dict(receipt_version="runtime-execution-v1",
            run_id=str(run.id), step=step, order_id=str(o.id), recommendation_reference=str(o.id), action=o.action,
            position_id=position.id, requested_amount_cents=o.amount_cents,
            executed_amount_cents=principal if buy else gross, status="EXECUTED", reason="Validated full fill",
            quantity=str(quantity), price_index=str(price), principal_cents=principal, gross_cents=gross,
            cash_delta_cents=delta-fee, transaction_cost_cents=fee, liquidation_cost_cents=cost,
            realized_market_pnl_cents=realized, remaining_cost_basis_cents=remaining_basis,
            ledger_entry_ids=ledger_ids, movement_id=str(movement.id))


def emergency_liquidate(session, run, cash, position, observation, step):
    if position.run_id != run.id or position.status != "OPEN" or position.acquired_at > observation.timestamp:
        raise ValueError("Emergency liquidation requires an owned, open, already-acquired position")
    bond = isinstance(position, BondPosition)
    if bond:
        quote = calculate_bond_economics(position.quantity, position.acquisition_price_index,
            observation.tier2_bond_price_index, quoted_yield_pct=observation.tier2_bond_yield_pct,
            liquidation_haircut_pct=observation.tier2_bond_liquidation_haircut_pct,
            cost_basis_cents=market_cost_basis(session, position))
    else:
        quote = calculate_equity_economics(position.quantity, position.acquisition_price_index,
            observation.tier3_stock_index_price, annual_volatility_pct=observation.tier3_stock_volatility_pct,
            emergency_sale=True, slippage_pct=observation.tier3_stock_liquidation_haircut_pct,
            cost_basis_cents=market_cost_basis(session, position))
    before = cash.balance_cents
    cash.balance_cents += quote.net_liquidation_proceeds_cents
    # Realized MARKET P&L excludes the separately booked haircut/slippage.
    gross_pnl = quote.market_value_cents - quote.cost_basis_cents
    position.status = "CLOSED"
    position.current_market_price_index = quote.current_price_index
    position.current_market_value_cents = 0
    position.market_observation_timestamp = observation.timestamp
    position.unrealized_pnl_cents = 0
    position.realized_pnl_cents = (position.realized_pnl_cents or 0) + gross_pnl
    position.liquidation_cost_cents = (position.liquidation_cost_cents or 0) + quote.liquidation_cost_cents
    position.liquidation_proceeds_cents = (position.liquidation_proceeds_cents or 0) + quote.net_liquidation_proceeds_cents
    source = dict(run_id=run.id, source_type=run.source_type, dataset_id=run.dataset_id,
                  source_observation_timestamp=observation.timestamp)
    ledger = LedgerEntry(**source, id=uuid4(), step=step, timestamp=None,
        entry_type="MARKET_LIQUIDATION_CREDIT", amount_cents=quote.net_liquidation_proceeds_cents,
        balance_before_cents=before, balance_after_cents=cash.balance_cents,
        reference_id=f"MARKET-SELL-{step}-{position.id}", event_at=observation.timestamp)
    session.add(ledger)
    session.flush()
    link = dict(tier=2 if bond else 3, bond_position_id=position.id if bond else None,
                equity_position_id=None if bond else position.id)
    movement = InvestmentMovement(**source, **link, id=uuid4(), kind="LIQUIDATION",
        occurred_at=observation.timestamp, cash_delta_cents=quote.net_liquidation_proceeds_cents,
        principal_cents=quote.cost_basis_cents, interest_cents=0,
        haircut_cost_cents=quote.liquidation_cost_cents, ledger_entry_id=ledger.id,
        reference_id=f"market-sale-{step}-{position.id}")
    session.add(movement)
    record_market_valuation(session, run, position, observation, gross_pnl)
    session.flush()
    return quote
