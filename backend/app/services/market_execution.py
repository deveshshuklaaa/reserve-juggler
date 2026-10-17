"""Whole-position emergency sales used ONLY by the shared hourly executor.

Member 1's scalar economics helpers supply market marks and source haircuts.
These functions post real financial evidence; they are not a backtest simulator.
"""
from datetime import timedelta
from uuid import uuid4

from app.persistence.models import BondPosition, InvestmentMovement, LedgerEntry, PositionValuation
from treasury_intelligence.instrument_economics import calculate_bond_economics, calculate_equity_economics


def emergency_liquidate(session, run, cash, position, observation, step):
    if position.run_id != run.id or position.status != "OPEN" or position.acquired_at > observation.timestamp:
        raise ValueError("Emergency liquidation requires an owned, open, already-acquired position")
    bond = isinstance(position, BondPosition)
    if bond:
        quote = calculate_bond_economics(position.quantity, position.acquisition_price_index,
            observation.tier2_bond_price_index, quoted_yield_pct=observation.tier2_bond_yield_pct,
            liquidation_haircut_pct=observation.tier2_bond_liquidation_haircut_pct)
    else:
        quote = calculate_equity_economics(position.quantity, position.acquisition_price_index,
            observation.tier3_stock_index_price, annual_volatility_pct=observation.tier3_stock_volatility_pct,
            emergency_sale=True, slippage_pct=observation.tier3_stock_liquidation_haircut_pct)
    before = cash.balance_cents
    cash.balance_cents += quote.net_liquidation_proceeds_cents
    # Realized MARKET P&L excludes the separately booked haircut/slippage.
    gross_pnl = quote.market_value_cents - quote.cost_basis_cents
    position.status = "CLOSED"
    position.current_market_price_index = quote.current_price_index
    position.current_market_value_cents = 0
    position.market_observation_timestamp = observation.timestamp
    position.unrealized_pnl_cents = 0
    position.realized_pnl_cents = gross_pnl
    position.liquidation_cost_cents = quote.liquidation_cost_cents
    position.liquidation_proceeds_cents = quote.net_liquidation_proceeds_cents
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
    session.add(PositionValuation(**source, **link, id=uuid4(),
        valued_at=observation.timestamp + timedelta(hours=1), market_price_index=quote.current_price_index,
        market_value_cents=0, unrealized_pnl_cents=0, realized_pnl_cents=gross_pnl,
        reference_id=f"market-close-{step}-{position.id}"))
    session.flush()
    return quote
