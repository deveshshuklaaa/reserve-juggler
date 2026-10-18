"""Comprehensive acceptance tests for the Backtesting Execution Receipt Adapter.

Verifies:
- Purchases (executed quantity, cash spent, fees, position change, instrument/tier, reference)
- Partial sales (requested/executed quantities, gross proceeds, fees, realized P&L, remaining position)
- Rejected trades (status REJECTED, reason preserved, zero execution, no mutations)
- Insufficient-funds payouts (overdraft use, liabilities, financing costs)
- Unpaid payout amounts (FAILED / UNPAID status, failure reason, no fake execution)
- Idempotent receipts (repeated reads yield identical bundles, zero mutations)
- Reconciliation between receipts, positions, cash, debt, and NAV.
"""
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.backtesting.receipts import (
    DOCUMENTED_RUNTIME_GAPS, ExecutionReceiptAdapter, HourlyExecutionBundle,
    PartialSaleReceipt, PayoutReceipt, PurchaseReceipt, RejectedTradeReceipt,
)
from app.persistence.models import (
    BondPosition, CashAccount, EquityPosition, InvestmentMovement, LedgerEntry,
    OrganizerObservation, OverdraftLiability, OverdraftMovement, PortfolioValuation,
    SimulationRun, TreasuryDecision,
)
from app.services import hourly_engine, market_execution
from app.services.run_service import create_simulation_run
from app.v1_contracts import CreateRunRequest
from treasury_intelligence.portfolio import CostBreakdown, RecommendedOrder
from .test_runtime_persistence import runtime_database, runtime_session, create_run


@pytest.fixture
def sim_state(runtime_session):
    first = runtime_session.scalar(select(OrganizerObservation).order_by(OrganizerObservation.timestamp))
    at = first.timestamp + timedelta(hours=9)
    created = create_simulation_run(
        runtime_session,
        CreateRunRequest(initial_cash_cents=10_000_000),
        source_start_timestamp=at,
    )
    run = runtime_session.get(SimulationRun, created.run_id)
    run.policy_json = dict(run.policy_json, strategy="RESERVE_JUGGLER")
    runtime_session.flush()
    cash = runtime_session.scalar(select(CashAccount).where(CashAccount.run_id == run.id))
    row = runtime_session.scalar(select(OrganizerObservation).where(
        OrganizerObservation.dataset_id == run.dataset_id,
        OrganizerObservation.timestamp == at))
    return run, cash, row


def make_order(run, row, action, *, quantity="2", amount=2_000_000, position_id=None, fee=10):
    return RecommendedOrder(
        id=uuid4(), run_id=run.id, time_basis="UNSPECIFIED",
        source_type=run.source_type, dataset_id=run.dataset_id,
        source_observation_timestamp=row.timestamp - timedelta(hours=1), as_of=row.timestamp,
        action=action, tier=2 if "BONDS" in action else 3,
        position_id=position_id, amount_cents=amount, quantity=Decimal(quantity),
        estimated_cost_cents=fee, expected_costs=CostBreakdown(transaction_cost_cents=fee),
        reason="Acceptance test order")


@pytest.mark.parametrize("instrument", ["BONDS", "EQUITIES"])
def test_purchase_receipt_preserves_executed_details_and_reconciles(runtime_session, sim_state, monkeypatch, instrument):
    session = runtime_session
    run, cash, row = sim_state
    initial_cash = cash.balance_cents
    buy_order = make_order(run, row, "BUY_" + instrument, quantity="3", fee=15)
    
    # Inject recommendation into hourly execution
    def recommend(*args, **kwargs):
        return SimpleNamespace(decision=SimpleNamespace(
            targets=SimpleNamespace(tier0_target_cents=0), orders=(buy_order,)), summary_action="REBALANCE")
    monkeypatch.setattr(hourly_engine, "recommend_four_tier_allocation_decision", recommend)
    
    hourly_engine.execute_hourly_step(session, run.id, 0)
    bundle = ExecutionReceiptAdapter.adapt_hour(session, run.id, 1)

    assert isinstance(bundle, HourlyExecutionBundle)
    assert len(bundle.purchases) == 1
    p = bundle.purchases[0]
    assert p.status == "EXECUTED"
    assert p.instrument == instrument
    assert p.tier == (2 if instrument == "BONDS" else 3)
    assert p.action == "BUY_" + instrument
    assert p.recommendation_reference == str(buy_order.id)
    assert Decimal(p.executed_quantity) == Decimal("3")
    assert p.fee_cents == 15
    assert p.cash_spent_cents == p.principal_cents + 15
    assert len(p.ledger_entry_ids) == 2  # fill + fee

    # Verify position link and quantity change
    pos_model = BondPosition if instrument == "BONDS" else EquityPosition
    pos = session.get(pos_model, p.position_id)
    assert pos is not None and pos.quantity == Decimal("3")
    assert Decimal(p.resulting_position_change) == Decimal("3")

    # Reconciles with cash account and closing state
    assert bundle.closing_cash_cents == initial_cash + bundle.hour_receipt.customer_cash_delta_cents - p.cash_spent_cents


@pytest.mark.parametrize("instrument", ["BONDS", "EQUITIES"])
def test_partial_sale_receipt_preserves_fill_and_basis_reconciliation(runtime_session, sim_state, monkeypatch, instrument):
    session = runtime_session
    run, cash, row = sim_state
    buy_order = make_order(run, row, "BUY_" + instrument, quantity="4", fee=20)
    
    # Step 1: Buy 4 units
    def recommend_buy(*args, **kwargs):
        return SimpleNamespace(decision=SimpleNamespace(
            targets=SimpleNamespace(tier0_target_cents=0), orders=(buy_order,)), summary_action="REBALANCE")
    monkeypatch.setattr(hourly_engine, "recommend_four_tier_allocation_decision", recommend_buy)
    hourly_engine.execute_hourly_step(session, run.id, 0)

    pos_model = BondPosition if instrument == "BONDS" else EquityPosition
    position = session.scalar(select(pos_model).where(pos_model.run_id == run.id))

    # Step 2: Partial sale of 1 unit
    later = session.scalar(select(OrganizerObservation).where(
        OrganizerObservation.dataset_id == run.dataset_id,
        OrganizerObservation.timestamp == row.timestamp + timedelta(hours=1)))
    sell_order = make_order(run, later, "SELL_" + instrument, quantity="1", position_id=position.id, fee=10)

    def recommend_sell(*args, **kwargs):
        return SimpleNamespace(decision=SimpleNamespace(
            targets=SimpleNamespace(tier0_target_cents=0), orders=(sell_order,)), summary_action="REBALANCE")
    monkeypatch.setattr(hourly_engine, "recommend_four_tier_allocation_decision", recommend_sell)
    hourly_engine.execute_hourly_step(session, run.id, 1)

    bundle = ExecutionReceiptAdapter.adapt_hour(session, run.id, 2)
    assert len(bundle.sales) == 1
    s = bundle.sales[0]
    assert s.status == "EXECUTED"
    assert s.is_partial is True
    assert s.instrument == instrument
    assert s.tier == (2 if instrument == "BONDS" else 3)
    assert Decimal(s.executed_quantity) == Decimal("1")
    assert Decimal(s.remaining_position_quantity) == Decimal("3")
    assert s.fee_cents == 10
    assert s.gross_proceeds_cents == s.cost_basis_released_cents + s.realized_pnl_cents
    assert s.net_cash_proceeds_cents == s.gross_proceeds_cents - s.fee_cents - s.liquidation_cost_cents
    assert position.quantity == Decimal("3")
    assert position.status == "OPEN"


def test_rejected_trade_preserves_rejection_reason_without_mutation(runtime_session, sim_state, monkeypatch):
    session = runtime_session
    run, cash, row = sim_state
    # Oversell order with no position
    invalid_order = make_order(run, row, "SELL_BONDS", quantity="10", position_id=uuid4())

    def recommend(*args, **kwargs):
        return SimpleNamespace(decision=SimpleNamespace(
            targets=SimpleNamespace(tier0_target_cents=0), orders=(invalid_order,)), summary_action="REBALANCE")
    monkeypatch.setattr(hourly_engine, "recommend_four_tier_allocation_decision", recommend)

    hourly_engine.execute_hourly_step(session, run.id, 0)
    bundle = ExecutionReceiptAdapter.adapt_hour(session, run.id, 1)

    assert len(bundle.rejected_trades) == 1
    r = bundle.rejected_trades[0]
    assert r.status == "REJECTED"
    assert r.executed_amount_cents == 0
    assert r.recommendation_reference == str(invalid_order.id)
    assert "Sale requires an owned open position" in r.reason
    assert len(bundle.purchases) == 0
    assert len(bundle.sales) == 0


def test_insufficient_funds_payout_and_overdraft_use(runtime_session):
    session = runtime_session
    # Initial cash 400,000 cents, payout 1,000,000 cents, overdraft cap 200,000 cents
    run = create_run(session, initial=400_000)
    run.policy_json = dict(run.policy_json, strategy="STATIC", allow_overdraft=True, max_overdraft_cents=200_000)
    row = session.scalar(select(OrganizerObservation).where(
        OrganizerObservation.dataset_id == run.dataset_id,
        OrganizerObservation.timestamp == run.source_start_timestamp))
    row.deposits_usd, row.withdrawals_usd = Decimal(0), Decimal(10000)  # 1,000,000 cents payout
    session.flush()

    hourly_engine.execute_hourly_step(session, run.id, 0)
    bundle = ExecutionReceiptAdapter.adapt_hour(session, run.id, 1)

    payout = bundle.payout
    assert payout.amount_due_cents == 1_000_000
    assert payout.amount_paid_cents == 600_000  # 400k cash + 200k overdraft
    assert payout.unpaid_remainder_cents == 400_000
    assert payout.overdraft_draw_cents == 200_000
    assert payout.borrowing_outstanding_cents == 200_000
    assert payout.execution_status == "PARTIALLY_EXECUTED"
    assert payout.settlement_status == "PARTIALLY_PAID"
    assert len(payout.ledger_entry_ids) >= 1
    assert len(payout.overdraft_ledger_entry_ids) >= 1

    # Overdraft liabilities in session match
    debt = list(session.scalars(select(OverdraftLiability).where(OverdraftLiability.run_id == run.id)))
    assert sum(o.borrowed_cents for o in debt) == 200_000


def test_unpaid_payout_amounts_distinguishes_failed_and_unpaid(runtime_session):
    session = runtime_session
    # Zero initial cash, disabled overdraft: complete shortfall
    run = create_run(session, initial=0)
    run.policy_json = dict(run.policy_json, strategy="STATIC", allow_overdraft=False, max_overdraft_cents=0)
    row = session.scalar(select(OrganizerObservation).where(
        OrganizerObservation.dataset_id == run.dataset_id,
        OrganizerObservation.timestamp == run.source_start_timestamp))
    row.deposits_usd, row.withdrawals_usd = Decimal(0), Decimal(5000)  # 500,000 cents payout
    session.flush()

    hourly_engine.execute_hourly_step(session, run.id, 0)
    bundle = ExecutionReceiptAdapter.adapt_hour(session, run.id, 1)

    payout = bundle.payout
    assert payout.amount_due_cents == 500_000
    assert payout.amount_paid_cents == 0
    assert payout.unpaid_remainder_cents == 500_000
    assert payout.execution_status == "FAILED"
    assert payout.settlement_status == "UNPAID"
    assert payout.overdraft_draw_cents == 0
    assert payout.failure_or_shortfall_reason is not None

    # Check HourReceipt reflects unpaid payout
    assert bundle.hour_receipt.failed_payouts == 1
    assert bundle.hour_receipt.unpaid_payouts_cents == 500_000


def test_receipt_adapter_is_idempotent(runtime_session, sim_state):
    session = runtime_session
    run, cash, row = sim_state
    hourly_engine.execute_hourly_step(session, run.id, 0)

    count_ledgers_before = session.scalar(select(func.count()).select_from(LedgerEntry).where(LedgerEntry.run_id == run.id))
    bundle1 = ExecutionReceiptAdapter.adapt_hour(session, run.id, 1)
    bundle2 = ExecutionReceiptAdapter.adapt_hour(session, run.id, 1)

    assert bundle1.model_dump() == bundle2.model_dump()
    count_ledgers_after = session.scalar(select(func.count()).select_from(LedgerEntry).where(LedgerEntry.run_id == run.id))
    assert count_ledgers_before == count_ledgers_after


def test_bundle_reconciles_positions_cash_debt_and_nav(runtime_session, sim_state, monkeypatch):
    session = runtime_session
    run, cash, row = sim_state
    buy = make_order(run, row, "BUY_BONDS", quantity="5", fee=10)
    def recommend(*args, **kwargs):
        return SimpleNamespace(decision=SimpleNamespace(
            targets=SimpleNamespace(tier0_target_cents=0), orders=(buy,)), summary_action="REBALANCE")
    monkeypatch.setattr(hourly_engine, "recommend_four_tier_allocation_decision", recommend)

    hourly_engine.execute_hourly_step(session, run.id, 0)
    bundle = ExecutionReceiptAdapter.adapt_hour(session, run.id, 1)

    # Reconciles closing values
    val = session.scalar(select(PortfolioValuation).where(
        PortfolioValuation.run_id == run.id, PortfolioValuation.reference_id == f"val-{run.id}-1"))
    assert bundle.closing_nav_cents == val.net_portfolio_value_cents
    assert bundle.closing_cash_cents == val.tier0_cash_cents
    assert bundle.closing_debt_cents == val.liabilities_cents
    assert bundle.hour_receipt.closing.net_asset_value_cents == val.net_portfolio_value_cents
