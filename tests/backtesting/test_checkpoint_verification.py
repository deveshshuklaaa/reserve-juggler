"""Independent release-gate probes against real PostgreSQL and the shared engine.

Expected-failure annotations, when present, name defects, not accepted behavior.
Run with --runxfail to reproduce the unmasked failures for Agent 1.
"""
from datetime import datetime
from decimal import Decimal
import sys
from uuid import uuid4

import pytest
from sqlalchemy import select
from fastapi.testclient import TestClient

from app.backtesting.contracts import ScenarioSpec
from app.backtesting.protocol import DecisionFrame, ExecutionFrame, RunSpec
from app.backtesting.reports import BacktestReportService
from app.backtesting.runtime import SharedRuntimeFactory, execute_persisted_hour
from app.backtesting.service import EngineContractError, observation_digest
from app.database import get_db
from app.main import app
from app.persistence.models import (
    BondPosition, CashAccount, EquityPosition, InvestmentMovement, LedgerEntry,
    OrganizerObservation, OverdraftLiability, PortfolioValuation, PositionValuation,
    SimulationRun, TreasuryDecision,
)
from app.services.hourly_engine import execute_hourly_step
from app.services.run_service import apply_simulation_scenario
from app.services.treasury_adapter import hydrate_portfolio_state
from app.v1_contracts import ScenarioRequest
from .test_runtime_persistence import runtime_database, runtime_session, create_run


def run_spec(dataset, **changes):
    values = dict(
        comparison_id=uuid4(), run_id=uuid4(), strategy="STATIC",
        start=datetime(2026, 1, 1), end_exclusive=datetime(2026, 1, 8), steps=168,
        initial_capital_cents=100_000_000_000, seed=42, scenario=ScenarioSpec(),
        policy_json="{}", dataset_id=dataset.metadata.dataset_id,
        dataset_sha256=dataset.metadata.content_hash, conditions_sha256="a" * 64,
    )
    return RunSpec(**(values | changes))


@pytest.fixture
def runtime_client(runtime_session):
    previous = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = lambda: runtime_session
    try:
        with TestClient(app) as client:
            yield client
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous


def test_optimizer_order_reaches_real_repo_ledger(runtime_session):
    from treasury_intelligence.optimizer import recommend_four_tier_allocation
    session = runtime_session
    run = create_run(session, initial=100_000_000_000, buffer=5_000_000_000)
    results = []
    def trace(frame, event, arg):
        if frame.f_code is recommend_four_tier_allocation.__code__ and event == "return":
            results.append(arg)
    previous = sys.getprofile()
    try:
        sys.setprofile(trace)
        for step in range(18):
            execute_hourly_step(session, run.id, step, strategy="RESERVE_JUGGLER")
    finally:
        sys.setprofile(previous)
    assert len(results) == 18
    orders = [o for r in results for o in r.decision.orders if o.action == "INVEST_REPO"]
    assert orders, "The eligible 17:00 fixture must produce a real optimizer order"
    decisions = list(session.scalars(select(TreasuryDecision).where(TreasuryDecision.run_id == run.id)))
    executed = [o for d in decisions for o in d.decision_details_json["orders_executed"] if "order_id" in o]
    assert executed
    for fill in executed:
        order = next(o for o in orders if str(o.id) == fill["order_id"])
        assert 0 < fill["amount_cents"] <= order.amount_cents
    movements = list(session.scalars(select(InvestmentMovement).where(
        InvestmentMovement.run_id == run.id, InvestmentMovement.kind == "INVESTMENT")))
    assert sum(m.principal_cents for m in movements) == sum(o["amount_cents"] for o in executed)
    for movement in movements:
        ledger = session.get(LedgerEntry, movement.ledger_entry_id)
        assert ledger.amount_cents == movement.principal_cents == -movement.cash_delta_cents


def test_reactive_first_decision_is_invariant_to_unavailable_current_flow(runtime_session):
    session = runtime_session
    left, right = create_run(session), create_run(session)
    execute_hourly_step(session, left.id, 0, strategy="REACTIVE")
    row = session.scalar(select(OrganizerObservation).where(
        OrganizerObservation.dataset_id == right.dataset_id,
        OrganizerObservation.timestamp == right.source_start_timestamp))
    row.withdrawals_usd += Decimal("1000000.00")
    session.flush()
    execute_hourly_step(session, right.id, 0, strategy="REACTIVE")
    reserves = [session.scalar(select(TreasuryDecision.required_reserve_cents).where(
        TreasuryDecision.run_id == r.id)) for r in (left, right)]
    assert reserves[0] == reserves[1], f"Current unpublished flow changed earlier reserve: {reserves}"


def test_first_two_observations_are_executed_once(runtime_session):
    run = create_run(runtime_session)
    receipts = [execute_persisted_hour(runtime_session, run.id, i) for i in range(2)]
    assert [r.timestamp for r in receipts] == [datetime(2026, 1, 1), datetime(2026, 1, 1, 1)]
    assert receipts[1].opening == receipts[0].closing
    assert set(receipts[0].event_ids).isdisjoint(receipts[1].event_ids)


def funded_market_position(session, instrument):
    """Seed a funded opening balance sheet; this is not a trading executor."""
    run = create_run(session)
    row = session.scalar(select(OrganizerObservation).where(
        OrganizerObservation.dataset_id == run.dataset_id, OrganizerObservation.timestamp == run.source_start_timestamp))
    price = row.tier2_bond_price_index if instrument == "BOND" else row.tier3_stock_index_price
    cost = int(price * 100)
    common = dict(run_id=run.id, source_type=run.source_type, dataset_id=run.dataset_id,
        source_observation_timestamp=row.timestamp, quantity=Decimal("1"), acquired_at=row.timestamp,
        acquisition_price_index=price, current_market_price_index=price, current_market_value_cents=cost, status="OPEN")
    if instrument == "BOND":
        position = BondPosition(**common, supplied_yield_pct=row.tier2_bond_yield_pct,
            modified_duration=row.tier2_bond_mod_duration, liquidation_haircut_pct=row.tier2_bond_liquidation_haircut_pct)
    else:
        position = EquityPosition(**common, supplied_volatility_pct=row.tier3_stock_volatility_pct,
            liquidation_haircut_pct=row.tier3_stock_liquidation_haircut_pct)
    session.add(position)
    cash = session.scalar(select(CashAccount).where(CashAccount.run_id == run.id))
    cash.balance_cents -= cost
    initial = session.scalar(select(PortfolioValuation).where(
        PortfolioValuation.run_id == run.id, PortfolioValuation.valued_at == row.timestamp))
    initial.tier0_cash_cents -= cost
    initial.immediately_available_cents -= cost
    setattr(initial, "tier2_market_value_cents" if instrument == "BOND" else "tier3_market_value_cents", cost)
    session.flush()
    return run, position


@pytest.mark.parametrize("instrument", ["BOND", "EQUITY"])
def test_funded_market_marks_reconcile_signed_pnl_and_report(runtime_session, instrument):
    run, position = funded_market_position(runtime_session, instrument)
    first, second = [execute_persisted_hour(runtime_session, run.id, i) for i in range(2)]
    report = BacktestReportService.report_run(runtime_session, run.id)
    assert first.closing.unrealized_market_pnl_cents == 0
    assert second.closing.unrealized_market_pnl_cents != 0
    assert (second.closing.unrealized_market_pnl_cents < 0) == (instrument == "BOND")
    assert report.accounting.unrealized_market_pnl_cents == second.closing.unrealized_market_pnl_cents
    assert report.accounting.realized_market_pnl_cents == report.accounting.realized_interest_cents == 0
    assert report.accounting.net_benefit_cents == report.accounting.unrealized_market_pnl_cents
    assert len(list(runtime_session.scalars(select(PositionValuation).where(
        PositionValuation.run_id == run.id)))) == 2


def test_repaid_principal_does_not_hide_unpaid_financing_liability(runtime_session):
    session = runtime_session
    run = create_run(session, initial=1_000_000)
    apply_simulation_scenario(session, run.id, ScenarioRequest(
        scenario="LIQUIDITY_SHOCK", parameters={"amount_cents": 1_000_000}, effective_step=1))
    execute_persisted_hour(session, run.id, 0)
    principal = session.scalar(select(OverdraftLiability.outstanding_principal_cents).where(
        OverdraftLiability.run_id == run.id))
    next_row = session.scalar(select(OrganizerObservation).where(
        OrganizerObservation.dataset_id == run.dataset_id, OrganizerObservation.timestamp == datetime(2026, 1, 1, 1)))
    shock = int((next_row.deposits_usd - next_row.withdrawals_usd) * 100) - principal
    apply_simulation_scenario(session, run.id, ScenarioRequest(
        scenario="LIQUIDITY_SHOCK", parameters={"amount_cents": shock}, effective_step=2))
    receipt = execute_persisted_hour(session, run.id, 1)
    debt = session.scalar(select(OverdraftLiability).where(OverdraftLiability.run_id == run.id))
    assert debt.outstanding_principal_cents == 0 and debt.financing_cost_cents > 0
    assert receipt.closing.unpaid_borrowing_costs_cents == debt.financing_cost_cents
    row = session.scalar(select(OrganizerObservation).where(
        OrganizerObservation.dataset_id == run.dataset_id, OrganizerObservation.timestamp == datetime(2026, 1, 1, 2)))
    state, *_ = hydrate_portfolio_state(session, run, row)
    assert state.valuation.liabilities_cents == debt.financing_cost_cents, (
        "Canonical optimizer hydration discarded unpaid financing expense after principal repayment")


def test_repo_accrual_grows_over_two_held_hours(runtime_session):
    session = runtime_session
    run = create_run(session, initial=100_000_000_000, buffer=5_000_000_000)
    receipts = [execute_persisted_hour(session, run.id, i) for i in range(20)]
    assert receipts[19].closing.accrued_interest_cents > receipts[18].closing.accrued_interest_cents, (
        "Closing repo accrual is only a single-hour amount rather than accumulated earned interest")


def test_public_report_retains_owned_accounting_and_history(runtime_session, runtime_client):
    run = create_run(runtime_session)
    execute_persisted_hour(runtime_session, run.id, 0)
    response = runtime_client.get(f"/api/v1/runs/{run.id}/report")
    assert response.status_code == 200, response.text
    data = response.json()
    required = {"accounting", "history", "model_evaluation", "scenario_settings_json", "execution_provenance"}
    assert required <= data.keys(), f"Public response dropped required service fields: {required - data.keys()}"
    assert data["model_evaluation"] is None
    assert len(data["history"]) == 1


def test_public_backtest_retains_fields_and_honors_requested_subset(runtime_session, runtime_client):
    run = create_run(runtime_session, duration_steps=168)
    response = runtime_client.post(f"/api/v1/runs/{run.id}/backtest", json={"strategies": ["STATIC_RESERVE"]})
    assert response.status_code == 200, response.text
    data = response.json()
    violations = []
    if [r["strategy"] for r in data["results"]] != ["STATIC_RESERVE"]:
        violations.append("requested strategy subset ignored")
    for result in data["results"]:
        for name in ("history", "accounting", "model_evaluation"):
            if name not in result:
                violations.append(f"{result['strategy']} lost {name}")
    from app.backtesting.runtime import RUNTIME_SHA
    if data.get("engine_integration_sha") != RUNTIME_SHA:
        violations.append("missing or incorrect checkpoint provenance")
    assert not violations, "; ".join(violations)


def test_factory_does_not_silently_discard_scenario_schedule(runtime_session, dataset):
    spec = run_spec(dataset, policy_json='{"scenarios":[{"effective_step":2,"parameters":{"amount_cents":12345},"scenario":"LIQUIDITY_SHOCK"}]}')
    run = SharedRuntimeFactory(session=runtime_session).start(spec)
    try:
        stored = runtime_session.get(SimulationRun, spec.run_id)
        assert stored.policy_json["scenarios"] == [
            {"effective_step":2, "parameters":{"amount_cents":12345}, "scenario":"LIQUIDITY_SHOCK"}]
    finally:
        run.close()


def test_factory_initial_scenario_is_not_applied_twice(runtime_session, dataset):
    spec = run_spec(dataset, scenario=ScenarioSpec(name="LIQUIDITY_SHOCK", parameters_json='{"amount_cents":12345}'),
        policy_json='{"scenarios":[{"effective_step":1,"parameters":{"amount_cents":12345},"scenario":"LIQUIDITY_SHOCK"}]}')
    run = SharedRuntimeFactory(session=runtime_session).start(spec)
    try:
        stored = runtime_session.get(SimulationRun, spec.run_id)
        assert len(stored.policy_json["scenarios"]) == 1
    finally:
        run.close()


@pytest.mark.parametrize("schedule", [
    '[{"scenario":"NORMAL"}]',
    '[{"effective_step":169,"scenario":"NORMAL"}]',
    '[{"effective_step":2,"scenario":"NORMAL"},{"effective_step":2,"scenario":"LOW_DEPOSIT"}]',
])
def test_factory_rejects_ambiguous_schedule_before_creating_run(runtime_session, dataset, schedule):
    spec = run_spec(dataset, policy_json='{"scenarios":' + schedule + '}')
    with pytest.raises(EngineContractError, match="schedule"):
        SharedRuntimeFactory(session=runtime_session).start(spec)
    assert runtime_session.get(SimulationRun, spec.run_id) is None



def test_factory_forwards_sorted_scenario_changes_to_shared_executor(runtime_session, dataset):
    spec = run_spec(dataset, policy_json='{"scenarios":[{"effective_step":2,"parameters":{"amount_cents":12345},"scenario":"LIQUIDITY_SHOCK"}]}')
    run = SharedRuntimeFactory(session=runtime_session).start(spec)
    try:
        for i in range(2):
            obs = dataset.observations[i]
            token = run.decide(DecisionFrame(i, obs.timestamp, dataset.observations[:i]))
            receipt = run.execute(ExecutionFrame(i, obs, observation_digest(obs)), token)
            assert receipt.timestamp == obs.timestamp
        decisions = list(runtime_session.scalars(select(TreasuryDecision).where(
            TreasuryDecision.run_id == spec.run_id).order_by(TreasuryDecision.step)))
        assert decisions[0].expected_outflow_cents == int(dataset.observations[0].withdrawals_usd * 100)
        assert decisions[1].expected_outflow_cents == int(dataset.observations[1].withdrawals_usd * 100) + 12345
    finally:
        run.close()


def test_factory_duplicate_id_is_explicit_and_does_not_poison_session(runtime_session, dataset):
    factory = SharedRuntimeFactory(session=runtime_session)
    spec = run_spec(dataset)
    first = factory.start(spec)
    first.close()
    with pytest.raises(EngineContractError, match="already exists"):
        factory.start(spec)
    assert runtime_session.get(SimulationRun, spec.run_id).current_step == 0
    second = factory.start(run_spec(dataset))
    second.close()


def test_factory_execute_rolls_back_a_rejected_receipt(runtime_session, dataset):
    from pydantic import ValidationError
    spec = run_spec(dataset)
    run = SharedRuntimeFactory(session=runtime_session).start(spec)
    try:
        # Corrupt only the seeded opening evidence, not the executor or CSV.
        opening = runtime_session.scalar(select(PortfolioValuation).where(
            PortfolioValuation.run_id == spec.run_id, PortfolioValuation.valued_at == spec.start))
        opening.tier0_cash_cents += 1
        opening.total_portfolio_value_cents += 1
        opening.net_portfolio_value_cents += 1
        runtime_session.flush()
        obs = dataset.observations[0]
        token = run.decide(DecisionFrame(0, obs.timestamp, ()))
        with pytest.raises(ValidationError, match="Cash delta"):
            run.execute(ExecutionFrame(0, obs, observation_digest(obs)), token)
        assert runtime_session.get(SimulationRun, spec.run_id).current_step == 0
        assert runtime_session.scalar(select(TreasuryDecision.id).where(TreasuryDecision.run_id == spec.run_id)) is None
        assert runtime_session.scalar(select(CashAccount.balance_cents).where(
            CashAccount.run_id == spec.run_id)) == spec.initial_capital_cents
    finally:
        run.close()


@pytest.mark.parametrize("error", ["digest", "token", "closed"])
def test_factory_rejects_invalid_execution_before_posting(runtime_session, dataset, error):
    spec = run_spec(dataset)
    run = SharedRuntimeFactory(session=runtime_session).start(spec)
    obs = dataset.observations[0]
    try:
        token = run.decide(DecisionFrame(0, obs.timestamp, ()))
        if error == "closed":
            run.close()
        with pytest.raises(EngineContractError):
            run.execute(ExecutionFrame(0, obs, "0" * 64 if error == "digest" else observation_digest(obs)),
                        None if error == "token" else token)
        assert runtime_session.get(SimulationRun, spec.run_id).current_step == 0
    finally:
        run.close()
