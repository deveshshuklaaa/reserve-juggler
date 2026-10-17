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
    BondPosition, CashAccount, EquityPosition, InvestmentMovement, LedgerEntry,
    LiquidityBreach, OrganizerObservation, OverdraftLiability, OverdraftMovement,
    PortfolioValuation, PositionValuation, RepoPosition, SimulationRun, TreasuryDecision,
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


def create_run(session, *, initial=2_000_000_000, buffer=50_000_000, duration_steps=720):
    created = create_simulation_run(session, CreateRunRequest(
        initial_cash_cents=initial, duration_steps=duration_steps,
        policy=TreasuryPolicy(operational_buffer_cents=buffer)))
    return session.get(SimulationRun, created.run_id)


def test_real_complete_hour_persists_cash_decision_and_valuation(runtime_session):
    session = runtime_session
    run = create_run(session)
    result = execute_hourly_step(session, run.id, expected_step=0)
    assert isinstance(result, dict) and result["step"] == 1
    assert run.current_step == 1
    entries = list(session.scalars(select(LedgerEntry).where(LedgerEntry.run_id == run.id, LedgerEntry.step == 1)))
    assert {row.entry_type for row in entries} >= {"CUSTOMER_DEPOSIT_INFLOW", "CUSTOMER_WITHDRAWAL_OUTFLOW"}
    assert all(row.source_observation_timestamp == datetime(2026, 1, 1, 0) for row in entries)
    valuation = session.scalar(select(PortfolioValuation).where(
        PortfolioValuation.run_id == run.id, PortfolioValuation.valued_at == datetime(2026, 1, 1, 1)))
    assert valuation.tier0_cash_cents == result["checking_cents"]
    with pytest.raises(StepConflictError):
        execute_hourly_step(session, run.id, expected_step=0)


def test_real_repo_sweep_then_maturity_has_auditable_interest(runtime_session):
    session = runtime_session
    run = create_run(session, initial=100_000_000_000, buffer=5_000_000_000)
    for step in range(18):
        execute_hourly_step(session, run.id, expected_step=step)
    position = session.scalar(select(RepoPosition).where(RepoPosition.run_id == run.id))
    assert position.entered_at == datetime(2026, 1, 1, 17)
    assert position.scheduled_maturity_at == datetime(2026, 1, 2, 8)
    assert position.status == "LOCKED"
    for step in range(18, 33):
        execute_hourly_step(session, run.id, expected_step=step)
    assert position.status == "MATURED"
    movements = list(session.scalars(select(InvestmentMovement).where(InvestmentMovement.run_id == run.id)))
    assert {m.kind for m in movements} >= {"INVESTMENT", "MATURITY"}
    maturity = next(m for m in movements if m.kind == "MATURITY")
    assert maturity.interest_cents > 0
    assert maturity.cash_delta_cents == maturity.principal_cents + maturity.interest_cents


def test_real_shock_has_shortfall_borrowing_and_financing_records(runtime_session):
    session = runtime_session
    run = create_run(session, initial=1_000_000)
    apply_simulation_scenario(session, run.id, ScenarioRequest(
        scenario="LIQUIDITY_SHOCK", parameters={"amount_cents": 5_000_000_000}, effective_step=1))
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
    assert report.history[0].timestamp == datetime(2026, 1, 1, 0)
    assert report.execution_provenance == "NOT_RECORDED_BY_RUNTIME"
    assert report.metrics.model_dump()["net_benefit_cents"] == 0


def test_real_repo_receipts_are_shared_with_report_aggregator(runtime_session):
    from app.backtesting.runtime import execute_persisted_hour
    from app.backtesting.reports import BacktestReportService
    session = runtime_session
    run = create_run(session, initial=100_000_000_000, buffer=5_000_000_000)
    receipts = [execute_persisted_hour(session, run.id, step) for step in range(33)]
    assert receipts[17].sweeps == 1
    assert receipts[-1].realized_interest_cents > 0
    assert receipts[-1].closing.tier1_value_cents == 0
    report = BacktestReportService.report_run(session, run.id, history_limit=5)
    assert len(report.history) == 5 and report.accounting.sweeps == 1
    assert "history" not in report.model_dump(mode="json")["accounting"]
    assert report.history[0].timestamp == datetime(2026, 1, 1, 0)
    assert report.history[-1].timestamp == datetime(2026, 1, 2, 8)
    assert report.accounting.realized_interest_cents == receipts[-1].realized_interest_cents
    assert report.metrics.net_benefit_cents == report.metrics.realized_interest_cents


def test_shock_receipt_and_atomic_execution(runtime_session):
    from app.backtesting.runtime import execute_persisted_hour
    session = runtime_session
    run = create_run(session, initial=1_000_000)
    apply_simulation_scenario(session, run.id, ScenarioRequest(
        scenario="LIQUIDITY_SHOCK", parameters={"amount_cents": 5_000_000_000}, effective_step=1))
    receipt = execute_persisted_hour(session, run.id, 0)
    assert receipt.borrowing_costs_cents > 0
    assert receipt.closing.borrowing_outstanding_cents > 0
    session.refresh(run)
    assert run.current_step == 1
    with pytest.raises(StepConflictError):
        execute_persisted_hour(session, run.id, 0)


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


def test_runtime_repayment_uses_schema_kind_and_preserves_principal_identity(runtime_session):
    session = runtime_session
    run = create_run(session, initial=1_000_000)
    apply_simulation_scenario(session, run.id, ScenarioRequest(
        scenario="LIQUIDITY_SHOCK", parameters={"amount_cents": 5_000_000_000}, effective_step=1))
    execute_hourly_step(session, run.id, 0)
    debt = session.scalar(select(OverdraftLiability).where(OverdraftLiability.run_id == run.id))
    prior_principal = debt.outstanding_principal_cents
    apply_simulation_scenario(session, run.id, ScenarioRequest(scenario="NORMAL", effective_step=2))
    execute_hourly_step(session, run.id, 1)
    repayment = session.scalar(select(OverdraftMovement).where(
        OverdraftMovement.run_id == run.id, OverdraftMovement.kind == "REPAYMENT"))
    assert repayment is not None and repayment.principal_cents > 0
    ledger = session.get(LedgerEntry, repayment.ledger_entry_id)
    assert ledger.balance_before_cents - ledger.balance_after_cents == repayment.principal_cents
    assert repayment.cash_delta_cents == -repayment.principal_cents
    assert debt.outstanding_principal_cents == prior_principal - repayment.principal_cents
    assert debt.borrowed_cents == debt.outstanding_principal_cents + debt.repaid_principal_cents


def test_runtime_repo_fee_field_mapping_no_longer_raises_attribute_error(runtime_session):
    session = runtime_session
    run = create_run(session, initial=100_000_000_000, buffer=5_000_000_000)
    for step in range(18):
        execute_hourly_step(session, run.id, step)
    apply_simulation_scenario(session, run.id, ScenarioRequest(
        scenario="LIQUIDITY_SHOCK", parameters={"amount_cents": 100_000_000_000}, effective_step=19))
    execute_hourly_step(session, run.id, 18)
    position = session.scalar(select(RepoPosition).where(RepoPosition.run_id == run.id))
    movement = session.scalar(select(InvestmentMovement).where(
        InvestmentMovement.run_id == run.id, InvestmentMovement.kind == "REDEMPTION"))
    assert position.status == "REDEEMED"
    assert movement.haircut_cost_cents == int(position.principal_cents * position.early_redemption_haircut_pct / 100)
    assert movement.cash_delta_cents == position.principal_cents - movement.haircut_cost_cents


def test_forecast_cutoff_is_invariant_to_current_and_future_source_flows(runtime_session):
    from datetime import timedelta
    from decimal import Decimal
    from app.services.treasury_adapter import get_hourly_forecasts_from_db, get_information_cutoff
    session = runtime_session
    run = create_run(session)
    as_of = datetime(2026, 1, 3, 2)
    assert get_information_cutoff(as_of) == as_of - timedelta(hours=1)
    baseline = get_hourly_forecasts_from_db(session, run.dataset_id, as_of)
    future_rows = list(session.scalars(select(OrganizerObservation).where(
        OrganizerObservation.dataset_id == run.dataset_id,
        OrganizerObservation.timestamp >= as_of,
        OrganizerObservation.timestamp <= as_of + timedelta(hours=6))))
    assert len(future_rows) == 7
    for row in future_rows:
        row.deposits_usd = Decimal("999999999.99")
        row.withdrawals_usd = Decimal("888888888.88")
        row.net_flow_usd = Decimal("111111111.11")
    session.flush()
    assert get_hourly_forecasts_from_db(session, run.dataset_id, as_of) == baseline


def test_shock_has_complete_payout_and_financing_nav_receipts(runtime_session):
    """H2 positive verification: settled customer payouts, financing receipts, and NAV deduction."""
    session = runtime_session
    run = create_run(session, initial=1_000_000)
    apply_simulation_scenario(session, run.id, ScenarioRequest(
        scenario="LIQUIDITY_SHOCK", parameters={"amount_cents": 5_000_000_000}, effective_step=1))
    execute_hourly_step(session, run.id, 0)
    decision = session.scalar(select(TreasuryDecision).where(TreasuryDecision.run_id == run.id))
    ledgers = list(session.scalars(select(LedgerEntry).where(LedgerEntry.run_id == run.id, LedgerEntry.step == 1)))
    debt = session.scalar(select(OverdraftLiability).where(OverdraftLiability.run_id == run.id))
    value = session.scalar(select(PortfolioValuation).where(
        PortfolioValuation.run_id == run.id, PortfolioValuation.valued_at == datetime(2026, 1, 1, 1)))
    paid = sum(row.amount_cents for row in ledgers if row.entry_type == "CUSTOMER_WITHDRAWAL_OUTFLOW")
    assert paid == decision.expected_outflow_cents
    assert debt.financing_cost_cents > 0
    financing_movement = session.scalar(select(OverdraftMovement).where(
        OverdraftMovement.run_id == run.id, OverdraftMovement.kind == "FINANCING_COST"))
    assert financing_movement is not None and (financing_movement.financing_cost_cents or financing_movement.principal_cents) == debt.financing_cost_cents
    assert value.liabilities_cents == debt.outstanding_principal_cents + debt.financing_cost_cents
    assert value.net_portfolio_value_cents == value.total_portfolio_value_cents - value.liabilities_cents


def test_repo_redemption_preserves_proceeds_beyond_customer_shortfall(runtime_session):
    """H3 positive verification: unused net proceeds remain in Tier 0 checking cash."""
    session = runtime_session
    run = create_run(session, initial=100_000_000_000, buffer=5_000_000_000)
    for step in range(18):
        execute_hourly_step(session, run.id, step)
    position = session.scalar(select(RepoPosition).where(RepoPosition.run_id == run.id))
    cash_before = session.scalar(select(CashAccount).where(CashAccount.run_id == run.id)).balance_cents
    row = session.scalar(select(OrganizerObservation).where(
        OrganizerObservation.dataset_id == run.dataset_id, OrganizerObservation.timestamp == datetime(2026, 1, 1, 18)))
    shock = cash_before + int((row.deposits_usd - row.withdrawals_usd) * 100) + position.principal_cents // 4
    apply_simulation_scenario(session, run.id, ScenarioRequest(
        scenario="LIQUIDITY_SHOCK", parameters={"amount_cents": shock}, effective_step=19))
    execute_hourly_step(session, run.id, 18)
    redemption = session.scalar(select(InvestmentMovement).where(
        InvestmentMovement.run_id == run.id, InvestmentMovement.kind == "REDEMPTION"))
    repo_payout = session.scalar(select(LedgerEntry.amount_cents).where(
        LedgerEntry.run_id == run.id, LedgerEntry.step == 19,
        LedgerEntry.reference_id == f"FLOW-OUT-REPO-19-{position.id}"))
    assert repo_payout is not None
    assert redemption.cash_delta_cents > repo_payout > 0
    cash = session.scalar(select(CashAccount).where(CashAccount.run_id == run.id))
    assert cash.balance_cents == redemption.cash_delta_cents - repo_payout
    assert cash.balance_cents > 0
    assert session.scalar(select(OverdraftLiability.id).where(OverdraftLiability.run_id == run.id)) is None


def test_all_dispatches_have_equal_independent_initial_conditions(runtime_session):
    session = runtime_session
    runs = {strategy: create_run(session) for strategy in ("STATIC", "REACTIVE", "RESERVE_JUGGLER")}
    assert len({run.id for run in runs.values()}) == 3
    assert len({run.seed for run in runs.values()}) == 1
    assert len({run.initial_cash_cents for run in runs.values()}) == 1
    policies = [run.policy_json for run in runs.values()]
    assert policies[0] == policies[1] == policies[2]
    for strategy, run in runs.items():
        before = session.scalar(select(CashAccount).where(CashAccount.run_id == run.id)).balance_cents
        assert before == run.initial_cash_cents and run.current_step == 0
        result = execute_hourly_step(session, run.id, 0, strategy=strategy)
        assert result["strategy"] == strategy
        decision = session.scalar(select(TreasuryDecision).where(TreasuryDecision.run_id == run.id))
        assert decision.decision_details_json["strategy"] == strategy
        others = [other for other in runs.values() if other.current_step == 0]
        for other in others:
            assert session.scalar(select(CashAccount).where(CashAccount.run_id == other.id)).balance_cents == other.initial_cash_cents
    reserves = {strategy: session.scalar(select(TreasuryDecision).where(
        TreasuryDecision.run_id == run.id)).required_reserve_cents for strategy, run in runs.items()}
    assert reserves["STATIC"] == 50_000_000
    assert reserves["REACTIVE"] != reserves["STATIC"]
    ledger_ids = [set(session.scalars(select(LedgerEntry.id).where(LedgerEntry.run_id == run.id))) for run in runs.values()]
    assert all(a.isdisjoint(b) for i, a in enumerate(ledger_ids) for b in ledger_ids[i + 1:])


def test_reserve_juggler_executes_canonical_allocation_optimizer(runtime_session):
    """H1 positive verification: RESERVE_JUGGLER invokes canonical recommend_four_tier_allocation."""
    import sys
    from treasury_intelligence.optimizer import recommend_four_tier_allocation
    from treasury_intelligence.liquidity_risk import calculate_four_tier_liquidity_risk
    session = runtime_session
    run = create_run(session, initial=100_000_000_000, buffer=5_000_000_000)
    counts = {"optimizer": 0, "risk": 0}

    def trace(frame, event, arg):
        if event == "call":
            if frame.f_code is recommend_four_tier_allocation.__code__:
                counts["optimizer"] += 1
            if frame.f_code is calculate_four_tier_liquidity_risk.__code__:
                counts["risk"] += 1

    previous = sys.getprofile()
    try:
        sys.setprofile(trace)
        for step in range(18):  # covers the actual 17:00 sweep decision
            execute_hourly_step(session, run.id, step, strategy="RESERVE_JUGGLER")
    finally:
        sys.setprofile(previous)
    assert counts["risk"] == 18
    assert counts["optimizer"] > 0


@pytest.mark.parametrize("method,suffix,body", [("POST", "backtest", {}), ("GET", "report", None)])
def test_backtest_and_report_routes_succeed(runtime_session, method, suffix, body):
    """H6 positive verification: routes return 200 with validated response schema."""
    from fastapi.testclient import TestClient
    from app.database import get_db
    from app.main import app

    app.dependency_overrides[get_db] = lambda: runtime_session
    try:
        run = create_run(runtime_session, duration_steps=168)
        client = TestClient(app)
        response = client.request(method, f"/api/v1/runs/{run.id}/{suffix}",
                                  **({"json": body} if body is not None else {}))
        assert response.status_code == 200, response.json()
        data = response.json()
        assert "run_id" in data
        assert data["run_id"] == str(run.id)
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.parametrize("instrument", ["BOND", "EQUITY"])
def test_open_market_positions_succeed_with_canonical_hydration(runtime_session, instrument):
    """H5 positive verification: canonical hydration succeeds and persists position valuation."""
    from decimal import Decimal
    session = runtime_session
    run = create_run(session)
    values = dict(run_id=run.id, source_type=run.source_type, dataset_id=run.dataset_id,
                  source_observation_timestamp=run.source_start_timestamp,
                  quantity=Decimal("1"), acquired_at=run.source_start_timestamp,
                  status="OPEN")
    if instrument == "BOND":
        position = BondPosition(**values, acquisition_price_index=Decimal("100"),
            current_market_price_index=Decimal("100"), current_market_value_cents=10_000,
            supplied_yield_pct=Decimal("4.8"), modified_duration=Decimal("1.92"),
            liquidation_haircut_pct=Decimal("2"))
    else:
        position = EquityPosition(**values, acquisition_price_index=Decimal("4988.59"),
            current_market_price_index=Decimal("4988.59"), current_market_value_cents=498_859,
            supplied_volatility_pct=Decimal("18"), liquidation_haircut_pct=Decimal("15"))
    session.add(position)
    session.flush()

    execute_hourly_step(session, run.id, 0)
    assert run.current_step == 1
    assert session.scalar(select(PortfolioValuation.id).where(
        PortfolioValuation.run_id == run.id, PortfolioValuation.valued_at == datetime(2026, 1, 1, 1))) is not None
    assert session.scalar(select(PositionValuation.id).where(PositionValuation.run_id == run.id)) is not None
