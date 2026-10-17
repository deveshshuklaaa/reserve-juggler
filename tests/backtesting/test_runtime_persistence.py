"""Real persisted runtime probes; no execution function or financial formula is mocked."""
import os
from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.persistence.migrations import apply_migrations
from app.persistence.models import (
    CashAccount, InvestmentMovement, LedgerEntry, LiquidityBreach, OverdraftLiability,
    OverdraftMovement, PortfolioValuation, RepoPosition, SimulationRun,
)
from app.persistence.repositories import DatasetRepository
from app.services.hourly_engine import StepConflictError, execute_hourly_step
from app.services.run_service import apply_simulation_scenario, create_simulation_run
from app.v1_contracts import CreateRunRequest, ScenarioRequest, TreasuryPolicy


@pytest.fixture(scope="module")
def runtime_database(dataset):
    raw = os.getenv("BACKTEST_TEST_DATABASE_URL")
    if not raw:
        pytest.skip("Set BACKTEST_TEST_DATABASE_URL to a disposable reserve_juggler_m2_test* database")
    url = make_url(raw)
    if not (url.database or "").startswith("reserve_juggler_m2_test"):
        pytest.fail("Runtime probes require a dedicated reserve_juggler_m2_test* database")
    name = "reserve_juggler_m2_test_bt_" + uuid4().hex[:12]
    admin = create_engine(url, isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.exec_driver_sql(f'CREATE DATABASE "{name}"')
    engine = create_engine(url.set(database=name))
    try:
        apply_migrations(engine)
        with Session(engine) as session, session.begin():
            DatasetRepository(session).store(dataset)
        yield engine
    finally:
        engine.dispose()
        with admin.connect() as connection:
            connection.exec_driver_sql(f'DROP DATABASE "{name}"')
        admin.dispose()


@pytest.fixture
def runtime_session(runtime_database):
    with runtime_database.connect() as connection:
        outer = connection.begin()
        with Session(connection, join_transaction_mode="create_savepoint") as session:
            yield session
        outer.rollback()


def create_run(session, *, initial=2_000_000_000, buffer=50_000_000):
    created = create_simulation_run(session, CreateRunRequest(
        initial_cash_cents=initial, duration_steps=720,
        policy=TreasuryPolicy(operational_buffer_cents=buffer)))
    return session.get(SimulationRun, created.run_id)


def test_real_complete_hour_persists_cash_decision_and_valuation(runtime_session):
    session = runtime_session
    run = create_run(session)
    result = execute_hourly_step(session, run.id, expected_step=0)
    assert isinstance(result, dict) and result["step"] == 1
    assert run.current_step == 1
    entries = list(session.scalars(select(LedgerEntry).where(LedgerEntry.run_id == run.id, LedgerEntry.step == 1)))
    assert {row.entry_type for row in entries} >= {"CUSTOMER_DEPOSIT_INFLOW","CUSTOMER_WITHDRAWAL_OUTFLOW"}
    assert all(row.source_observation_timestamp == datetime(2026,1,1,1) for row in entries)
    valuation = session.scalar(select(PortfolioValuation).where(
        PortfolioValuation.run_id == run.id, PortfolioValuation.valued_at == datetime(2026,1,1,1)))
    assert valuation.tier0_cash_cents == result["checking_cents"]
    with pytest.raises(StepConflictError):
        execute_hourly_step(session, run.id, expected_step=0)


def test_real_repo_sweep_then_maturity_has_auditable_interest(runtime_session):
    session = runtime_session
    run = create_run(session, initial=100_000_000_000, buffer=5_000_000_000)
    for step in range(17):
        execute_hourly_step(session, run.id, expected_step=step)
    position = session.scalar(select(RepoPosition).where(RepoPosition.run_id == run.id))
    assert position.entered_at == datetime(2026,1,1,17)
    assert position.scheduled_maturity_at == datetime(2026,1,2,8)
    assert position.status == "LOCKED"
    for step in range(17,32):
        execute_hourly_step(session, run.id, expected_step=step)
    assert position.status == "MATURED"
    movements = list(session.scalars(select(InvestmentMovement).where(InvestmentMovement.run_id == run.id)))
    assert {m.kind for m in movements} >= {"INVESTMENT","MATURITY"}
    maturity = next(m for m in movements if m.kind == "MATURITY")
    assert maturity.interest_cents > 0
    assert maturity.cash_delta_cents == maturity.principal_cents + maturity.interest_cents


def test_real_shock_has_shortfall_borrowing_and_financing_records(runtime_session):
    session = runtime_session
    run = create_run(session, initial=1_000_000)
    apply_simulation_scenario(session, run.id, ScenarioRequest(
        scenario="LIQUIDITY_SHOCK", parameters={"amount_cents":5_000_000_000}, effective_step=1))
    result = execute_hourly_step(session, run.id, expected_step=0)
    breach = session.scalar(select(LiquidityBreach).where(LiquidityBreach.run_id == run.id))
    debt = session.scalar(select(OverdraftLiability).where(OverdraftLiability.run_id == run.id))
    movement = session.scalar(select(OverdraftMovement).where(OverdraftMovement.run_id == run.id))
    assert result["checking_cents"] == 0
    assert breach.shortfall_cents == debt.outstanding_principal_cents == movement.principal_cents > 0
    assert debt.breach_id == breach.id and movement.liability_id == debt.id
    assert movement.kind == "BORROW" and debt.financing_cost_cents > 0


def test_real_receipt_bridge_and_persisted_report(runtime_session):
    from app.backtesting.runtime import execute_persisted_hour, read_hour_receipt
    from app.backtesting.reports import BacktestReportService
    session = runtime_session
    run = create_run(session)
    before = BacktestReportService.report_run(session, run.id)
    assert before.metrics is None and before.accounting is None and before.history == ()
    receipt = execute_persisted_hour(session, run.id, 0)
    assert receipt == read_hour_receipt(session, run.id, 1)
    report = BacktestReportService.report_run(session, run.id)
    assert report.metrics.average_checking_cents == receipt.closing.checking_cents
    assert report.accounting.net_benefit_cents == 0
    assert report.model_evaluation is None
    assert report.history[0].timestamp == datetime(2026,1,1,1)
    assert report.execution_provenance == "NOT_RECORDED_BY_RUNTIME"
    assert report.metrics.model_dump()["net_benefit_cents"] == 0


def test_real_repo_receipts_are_shared_with_report_aggregator(runtime_session):
    from app.backtesting.runtime import execute_persisted_hour
    from app.backtesting.reports import BacktestReportService
    session = runtime_session
    run = create_run(session, initial=100_000_000_000, buffer=5_000_000_000)
    receipts = [execute_persisted_hour(session, run.id, step) for step in range(32)]
    assert receipts[16].sweeps == 1
    assert receipts[-1].realized_interest_cents > 0
    assert receipts[-1].closing.tier1_value_cents == 0
    report = BacktestReportService.report_run(session, run.id, history_limit=5)
    assert len(report.history) == 5 and report.accounting.sweeps == 1
    assert "history" not in report.model_dump(mode="json")["accounting"]
    assert report.history[0].timestamp == datetime(2026,1,1,1)
    assert report.history[-1].timestamp == datetime(2026,1,2,8)
    assert report.accounting.realized_interest_cents == receipts[-1].realized_interest_cents
    assert report.metrics.net_benefit_cents == report.metrics.realized_interest_cents


def test_incomplete_shock_receipt_rolls_back_atomic_execution(runtime_session):
    from app.backtesting.runtime import execute_persisted_hour, RuntimeReceiptUnavailable
    session = runtime_session
    run = create_run(session, initial=1_000_000)
    apply_simulation_scenario(session, run.id, ScenarioRequest(
        scenario="LIQUIDITY_SHOCK", parameters={"amount_cents":5_000_000_000}, effective_step=1))
    with pytest.raises(RuntimeReceiptUnavailable, match="Financing expense"):
        execute_persisted_hour(session, run.id, 0)
    session.refresh(run)
    assert run.current_step == 0
    assert session.scalar(select(LiquidityBreach.id).where(LiquidityBreach.run_id == run.id)) is None
    assert session.scalar(select(OverdraftLiability.id).where(OverdraftLiability.run_id == run.id)) is None


def test_run_state_is_isolated_and_receipt_reader_rejects_missing_evidence(runtime_session):
    from app.backtesting.runtime import execute_persisted_hour, read_hour_receipt, RuntimeReceiptUnavailable
    session = runtime_session
    left, right = create_run(session), create_run(session)
    assert left.id != right.id and left.seed == right.seed
    assert left.initial_cash_cents == right.initial_cash_cents and left.policy_json == right.policy_json
    execute_persisted_hour(session, left.id, 0)
    assert left.current_step == 1 and right.current_step == 0
    cash = session.scalar(select(CashAccount).where(CashAccount.run_id == right.id))
    assert cash.balance_cents == right.initial_cash_cents
    session.delete(session.scalar(select(LedgerEntry).where(
        LedgerEntry.run_id == left.id, LedgerEntry.step == 1,
        LedgerEntry.entry_type == "CUSTOMER_WITHDRAWAL_OUTFLOW")))
    session.flush()
    with pytest.raises(RuntimeReceiptUnavailable, match="settled-payout"):
        read_hour_receipt(session, left.id, 1)


def test_runtime_repayment_postgresql_blocker_is_reproducible(runtime_session):
    """Diagnosis, not a claim that repayment works: executor emits invalid kind REPAY."""
    from sqlalchemy.exc import IntegrityError
    session = runtime_session
    run = create_run(session, initial=1_000_000)
    apply_simulation_scenario(session, run.id, ScenarioRequest(
        scenario="LIQUIDITY_SHOCK", parameters={"amount_cents":5_000_000_000}, effective_step=1))
    execute_hourly_step(session, run.id, 0)
    apply_simulation_scenario(session, run.id, ScenarioRequest(scenario="NORMAL", effective_step=2))
    with pytest.raises(IntegrityError) as failure:
        with session.begin_nested():
            execute_hourly_step(session, run.id, 1)
    assert failure.value.orig.diag.sqlstate == "23514"
    assert "overdraft_movements" in str(failure.value.orig)


def test_runtime_early_repo_break_blocker_is_reproducible(runtime_session):
    """Diagnosis: ORM has haircut_pct; executor accesses nonexistent early_break_fee_bps."""
    session = runtime_session
    run = create_run(session, initial=100_000_000_000, buffer=5_000_000_000)
    for step in range(17):
        execute_hourly_step(session, run.id, step)
    apply_simulation_scenario(session, run.id, ScenarioRequest(
        scenario="LIQUIDITY_SHOCK", parameters={"amount_cents":100_000_000_000}, effective_step=18))
    with pytest.raises(AttributeError, match="early_break_fee_bps"):
        with session.begin_nested():
            execute_hourly_step(session, run.id, 17)


def test_actual_forecast_query_uses_future_observations_so_comparisons_stay_blocked(runtime_session):
    from app.services.treasury_adapter import get_hourly_forecasts_from_db
    from app.persistence.models import OrganizerObservation
    from app.backtesting.runtime import SharedRuntimeFactory
    session = runtime_session
    run = create_run(session)
    points = get_hourly_forecasts_from_db(session, run.dataset_id, datetime(2026,1,1,1))
    future = session.scalar(select(OrganizerObservation).where(
        OrganizerObservation.dataset_id == run.dataset_id, OrganizerObservation.timestamp == datetime(2026,1,1,4)))
    assert points[-1].predicted_withdrawals_cents == int(future.withdrawals_usd * 100)
    assert SharedRuntimeFactory.capabilities.strategies == ()
