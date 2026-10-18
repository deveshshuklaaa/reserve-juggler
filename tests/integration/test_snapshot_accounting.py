"""Read projections must not invent a second balance sheet or consume future quotes."""
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select

from test_four_tier_runtime import dataset, pg_engine, pg_url, session
from app.persistence.models import CashAccount, OrganizerObservation, PortfolioValuation, SimulationRun
from app.services.hourly_engine import execute_hourly_step
from app.services.run_service import create_simulation_run, get_simulation_snapshot
from app.v1_contracts import CreateRunRequest


def test_initial_snapshot_has_no_unpublished_source_quote(session):
    created = create_simulation_run(session, CreateRunRequest())
    snapshot = get_simulation_snapshot(session, created.run_id)
    assert snapshot.four_tier.market_data_available is False
    assert snapshot.four_tier.tier2.current_price is None
    assert snapshot.four_tier.tier3.current_price is None
    assert snapshot.four_tier.tier1.repo_apy_bps is None


def test_snapshot_does_not_read_next_unprocessed_hour(session):
    created = create_simulation_run(session, CreateRunRequest())
    run = session.get(SimulationRun, created.run_id)
    execute_hourly_step(session, run.id, 0)
    before = get_simulation_snapshot(session, run.id)
    unavailable = session.get(OrganizerObservation, (run.dataset_id, run.source_start_timestamp+timedelta(hours=1)))
    unavailable.tier2_bond_price_index *= Decimal(10)
    unavailable.tier3_stock_index_price *= Decimal(20)
    unavailable.tier1_repo_rate_apy *= Decimal(2)
    session.flush()
    after = get_simulation_snapshot(session, run.id)
    assert before.four_tier == after.four_tier


def test_snapshot_nav_includes_financing_costs_and_matches_persisted_execution(session):
    created = create_simulation_run(session, CreateRunRequest(initial_cash_cents=0))
    run = session.get(SimulationRun, created.run_id)
    row = session.get(OrganizerObservation, (run.dataset_id, run.source_start_timestamp))
    row.deposits_usd, row.withdrawals_usd = Decimal(0), Decimal(10000)
    session.flush()
    execute_hourly_step(session, run.id, 0)
    stored = session.scalar(select(PortfolioValuation).where(
        PortfolioValuation.run_id == run.id, PortfolioValuation.reference_id == f"val-{run.id}-1"))
    snapshot = get_simulation_snapshot(session, run.id)
    assert stored.liabilities_cents > 1_000_000
    assert snapshot.four_tier.aggregates.total_liabilities_cents == stored.liabilities_cents
    assert snapshot.four_tier.aggregates.net_portfolio_value_cents == stored.net_portfolio_value_cents


def test_snapshot_repo_accrual_matches_actual_closing_nav(session):
    created = create_simulation_run(session, CreateRunRequest(initial_cash_cents=100_000_000_000))
    run = session.get(SimulationRun, created.run_id)
    for row in session.scalars(select(OrganizerObservation).where(
            OrganizerObservation.dataset_id == run.dataset_id,
            OrganizerObservation.timestamp < run.source_start_timestamp+timedelta(hours=21))):
        row.deposits_usd = row.withdrawals_usd = Decimal(0)
    session.flush()
    for step in range(20):
        execute_hourly_step(session, run.id, step, strategy="STATIC")
    stored = session.scalar(select(PortfolioValuation).where(
        PortfolioValuation.run_id == run.id, PortfolioValuation.reference_id == f"val-{run.id}-20"))
    snapshot = get_simulation_snapshot(session, run.id)
    assert snapshot.four_tier.tier1.accrued_interest_cents == stored.tier1_value_cents-stored.tier1_principal_cents
    assert snapshot.four_tier.aggregates.gross_assets_cents == stored.total_portfolio_value_cents
    assert snapshot.four_tier.aggregates.net_portfolio_value_cents == stored.net_portfolio_value_cents


def test_snapshot_partial_sale_pnl_and_benefit_reconcile_actual_cash(session):
    from test_market_order_execution import order
    from app.services.market_execution import execute_market_order
    from app.persistence.models import BondPosition, LedgerEntry
    first = session.scalar(select(OrganizerObservation).order_by(OrganizerObservation.timestamp))
    start = first.timestamp+timedelta(hours=1)
    created = create_simulation_run(session, CreateRunRequest(), source_start_timestamp=start)
    run = session.get(SimulationRun, created.run_id)
    cash = session.scalar(select(CashAccount).where(CashAccount.run_id == run.id))
    row = session.get(OrganizerObservation, (run.dataset_id, start))
    fill = execute_market_order(session, run, cash, order(run, row, "BUY_BONDS", quantity="3", fee=3), row, 1)
    execute_hourly_step(session, run.id, 0, strategy="STATIC")
    next_row = session.get(OrganizerObservation, (run.dataset_id, start+timedelta(hours=1)))
    execute_market_order(session, run, cash, order(run, next_row, "SELL_BONDS", quantity="1",
        fee=2, position_id=fill["position_id"]), next_row, 2)
    execute_hourly_step(session, run.id, 1, strategy="STATIC")
    position = session.get(BondPosition, fill["position_id"])
    snapshot = get_simulation_snapshot(session, run.id).four_tier
    assert snapshot.tier2.realized_pnl_cents == position.realized_pnl_cents
    customer_delta = sum((e.balance_after_cents-e.balance_before_cents)
        for e in session.scalars(select(LedgerEntry).where(
            LedgerEntry.run_id == run.id,
            LedgerEntry.entry_type.in_(["CUSTOMER_DEPOSIT_INFLOW", "CUSTOMER_WITHDRAWAL_OUTFLOW"]))))
    benefit = snapshot.aggregates.net_portfolio_value_cents-run.initial_cash_cents-customer_delta
    assert snapshot.aggregates.net_financial_benefit_cents == benefit
    assert benefit == position.realized_pnl_cents+position.unrealized_pnl_cents-position.liquidation_cost_cents-5
