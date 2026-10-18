"""Focused real-PostgreSQL market-order regressions owned by the runtime workstream."""
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from test_four_tier_runtime import dataset, pg_engine, pg_url, session
from app.persistence.models import (
    BondPosition, CashAccount, EquityPosition, InvestmentMovement, LedgerEntry,
    OrganizerObservation, PositionValuation, SimulationRun,
)
from app.services import market_execution
from app.services.run_service import create_simulation_run
from app.v1_contracts import CreateRunRequest
from treasury_intelligence.portfolio import CostBreakdown, RecommendedOrder


@pytest.fixture
def market_state(session):
    first = session.scalar(select(OrganizerObservation).order_by(OrganizerObservation.timestamp))
    created = create_simulation_run(session, CreateRunRequest(),
        source_start_timestamp=first.timestamp + timedelta(hours=1))
    run = session.get(SimulationRun, created.run_id)
    cash = session.scalar(select(CashAccount).where(CashAccount.run_id == run.id))
    row = session.scalar(select(OrganizerObservation).where(
        OrganizerObservation.dataset_id == run.dataset_id,
        OrganizerObservation.timestamp == run.source_start_timestamp))
    return run, cash, row


def order(run, row, action, *, quantity="2", amount=2_000_000, position_id=None, fee=0):
    return RecommendedOrder(id=uuid4(), run_id=run.id, time_basis="UNSPECIFIED",
        source_type=run.source_type, dataset_id=run.dataset_id,
        source_observation_timestamp=row.timestamp-timedelta(hours=1), as_of=row.timestamp,
        action=action, tier=2 if "BONDS" in action else 3,
        position_id=position_id, amount_cents=amount, quantity=Decimal(quantity),
        estimated_cost_cents=fee, expected_costs=CostBreakdown(transaction_cost_cents=fee),
        reason="Explicit integration-test order, not an evaluated strategy")


def execute(session, state, instruction, step=1):
    assert hasattr(market_execution, "execute_market_order"), (
        "Shared runtime has no canonical purchase/partial-sale execution path")
    run, cash, row = state
    return market_execution.execute_market_order(session, run, cash, instruction, row, step)


@pytest.mark.parametrize("instrument", ["BONDS", "EQUITIES"])
def test_purchase_and_partial_sale_conserve_basis_and_account_for_fees(session, market_state, instrument):
    run, cash, row = market_state
    initial = cash.balance_cents
    buy = order(run, row, "BUY_" + instrument, quantity="3", fee=3)
    acquired = execute(session, market_state, buy)
    model = BondPosition if instrument == "BONDS" else EquityPosition
    position = session.get(model, acquired["position_id"])
    assert position.quantity == Decimal("3")
    assert cash.balance_cents == initial - acquired["principal_cents"] - 3
    later = session.scalar(select(OrganizerObservation).where(
        OrganizerObservation.dataset_id == run.dataset_id, OrganizerObservation.timestamp == row.timestamp + timedelta(hours=1)))
    sell = order(run, later, "SELL_" + instrument, quantity="1", position_id=position.id, fee=2)
    filled = execute(session, (run, cash, later), sell, step=2)
    assert position.quantity == Decimal("2") and position.status == "OPEN"
    movements = list(session.scalars(select(InvestmentMovement).where(InvestmentMovement.run_id == run.id)))
    bought_basis = next(m.principal_cents for m in movements if m.kind == "INVESTMENT")
    released_basis = sum(m.principal_cents for m in movements if m.kind == "LIQUIDATION")
    assert filled["remaining_cost_basis_cents"] + released_basis == bought_basis
    assert filled["realized_market_pnl_cents"] == filled["gross_cents"] - released_basis
    assert position.current_market_value_cents - position.unrealized_pnl_cents == filled["remaining_cost_basis_cents"]
    net_asset_value = cash.balance_cents + position.current_market_value_cents
    assert net_asset_value - initial == (
        filled["realized_market_pnl_cents"] + position.unrealized_pnl_cents
        - acquired["transaction_cost_cents"] - filled["transaction_cost_cents"] - filled["liquidation_cost_cents"])
    fees = list(session.scalars(select(LedgerEntry).where(
        LedgerEntry.run_id == run.id, LedgerEntry.entry_type == "MARKET_TRANSACTION_FEE")))
    assert sum(f.amount_cents for f in fees) == 5
    assert all(f.balance_after_cents == f.balance_before_cents - f.amount_cents for f in fees)


@pytest.mark.parametrize("invalid", ["cash", "budget", "oversell", "future", "duplicate"])
def test_invalid_trade_leaves_no_partial_financial_posts(session, market_state, invalid):
    run, cash, row = market_state
    good = order(run, row, "BUY_BONDS", quantity="2", amount=20_000)
    if invalid in ("oversell", "duplicate"):
        acquired = execute(session, market_state, good)
    count = session.scalar(select(func.count()).select_from(LedgerEntry).where(LedgerEntry.run_id == run.id))
    before = cash.balance_cents
    if invalid == "cash":
        instruction = order(run, row, "BUY_BONDS", quantity="100000000")
    elif invalid == "budget":
        instruction = order(run, row, "BUY_BONDS", quantity="2", amount=1)
    elif invalid == "oversell":
        instruction = order(run, row, "SELL_BONDS", quantity="3", position_id=acquired["position_id"])
    elif invalid == "future":
        instruction = order(run, row, "BUY_BONDS").model_copy(update={"as_of": row.timestamp + timedelta(hours=1)})
    else:
        instruction = good
    assert hasattr(market_execution, "TradeRejected"), "Execution must reject unsupported financial instructions explicitly"
    with pytest.raises(market_execution.TradeRejected):
        execute(session, market_state, instruction)
    assert cash.balance_cents == before
    assert session.scalar(select(func.count()).select_from(LedgerEntry).where(LedgerEntry.run_id == run.id)) == count


def test_full_sale_releases_every_basis_cent_after_partial_sale(session, market_state):
    run, cash, row = market_state
    acquired = execute(session, market_state, order(run, row, "BUY_BONDS", quantity="3.000000000000000001"))
    position = session.get(BondPosition, acquired["position_id"])
    execute(session, market_state, order(run, row, "SELL_BONDS", quantity="0.333333333333333333", position_id=position.id))
    final = execute(session, market_state, order(run, row, "SELL_BONDS", quantity=str(position.quantity), position_id=position.id))
    assert position.status == "CLOSED" and final["remaining_cost_basis_cents"] == 0
    released = session.scalar(select(func.sum(InvestmentMovement.principal_cents)).where(
        InvestmentMovement.run_id == run.id, InvestmentMovement.kind == "LIQUIDATION"))
    assert released == acquired["principal_cents"]
    values = list(session.scalars(select(PositionValuation).where(PositionValuation.run_id == run.id)))
    assert len(values) == 1  # same-hour fills aggregate, they do not duplicate P&L
    assert values[0].market_value_cents == values[0].unrealized_pnl_cents == 0


def test_canonical_optional_costs_are_not_required_for_a_zero_fee_trade(session, market_state):
    instruction = order(*market_state[::2], "BUY_BONDS").model_copy(update={
        "expected_costs": None, "estimated_cost_cents": None})
    filled = execute(session, market_state, instruction)
    assert filled["transaction_cost_cents"] == 0


@pytest.mark.parametrize("instrument", ["BONDS", "EQUITIES"])
def test_shared_hourly_engine_posts_recommendation_and_partial_sale(session, market_state, monkeypatch, instrument):
    from app.services import hourly_engine
    from app.persistence.models import PortfolioValuation, TreasuryDecision
    from app.services.treasury_adapter import hydrate_portfolio_state
    run, cash, row = market_state
    # Only the recommendation boundary is injected; all execution and storage is real.
    recommendations = [order(run, row, "BUY_" + instrument, quantity="3", fee=3)]
    def recommend(*args, **kwargs):
        return SimpleNamespace(decision=SimpleNamespace(
            targets=SimpleNamespace(tier0_target_cents=0), orders=tuple(recommendations)), summary_action="REBALANCE")
    monkeypatch.setattr(hourly_engine, "recommend_four_tier_allocation_decision", recommend)
    first = hourly_engine.execute_hourly_step(session, run.id, 0)
    decision = session.scalar(select(TreasuryDecision).where(TreasuryDecision.run_id == run.id, TreasuryDecision.step == 1))
    receipt = decision.decision_details_json["orders_executed"][0]
    assert receipt["action"] == "BUY_" + instrument and receipt["status"] == "EXECUTED"
    model = BondPosition if instrument == "BONDS" else EquityPosition
    position = session.scalar(select(model).where(model.run_id == run.id))
    later = session.scalar(select(OrganizerObservation).where(
        OrganizerObservation.dataset_id == run.dataset_id, OrganizerObservation.timestamp == row.timestamp + timedelta(hours=1)))
    recommendations[:] = [order(run, later, "SELL_" + instrument, quantity="1", position_id=position.id, fee=2)]
    second = hourly_engine.execute_hourly_step(session, run.id, 1)
    assert position.quantity == Decimal("2")
    state = hydrate_portfolio_state(session, run, later)[0]
    canonical = (state.bond_positions if instrument == "BONDS" else state.equity_positions)[0]
    assert canonical.acquisition_cost_cents == position.current_market_value_cents - position.unrealized_pnl_cents
    value = session.scalar(select(PortfolioValuation).where(
        PortfolioValuation.run_id == run.id, PortfolioValuation.reference_id == f"val-{run.id}-2"))
    assert value.total_portfolio_value_cents == value.tier0_cash_cents + value.tier1_value_cents + value.tier2_market_value_cents + value.tier3_market_value_cents
    assert value.net_portfolio_value_cents == value.total_portfolio_value_cents - value.liabilities_cents
    marks = list(session.scalars(select(PositionValuation).where(
        PositionValuation.run_id == run.id, PositionValuation.valued_at == later.timestamp + timedelta(hours=1))))
    assert len(marks) == 1 and marks[0].realized_pnl_cents == position.realized_pnl_cents
    assert first["step"] == 1 and second["step"] == 2
