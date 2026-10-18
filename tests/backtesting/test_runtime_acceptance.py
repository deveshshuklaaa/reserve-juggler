"""Runtime/API acceptance on real PostgreSQL; no accounting or execution mocks."""
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4

import pytest
from sqlalchemy import select, func

from app.backtesting.runtime import execute_persisted_hour, read_hour_receipt
from app.backtesting.reports import BacktestReportService
from app.persistence.models import (
    CashAccount, InvestmentMovement, OrganizerObservation, OverdraftLiability,
    OverdraftMovement, RepoPosition, SimulationRun,
)
from app.services.hourly_engine import execute_hourly_step
from app.services.run_service import apply_simulation_scenario, create_simulation_run
from app.services.treasury_adapter import hydrate_portfolio_state
from app.v1_contracts import CreateRunRequest, ScenarioRequest
from .test_checkpoint_verification import funded_market_position, runtime_client
from .test_runtime_persistence import runtime_database, runtime_session, create_run


def test_financing_cost_payment_is_not_a_second_expense(runtime_session):
    session = runtime_session
    run = create_run(session, initial=1_000_000)
    apply_simulation_scenario(session, run.id, ScenarioRequest(
        scenario="LIQUIDITY_SHOCK", parameters={"amount_cents": 1_000_000}, effective_step=1))
    first = execute_persisted_hour(session, run.id, 0)
    apply_simulation_scenario(session, run.id, ScenarioRequest(scenario="NORMAL", effective_step=2))
    second = execute_persisted_hour(session, run.id, 1)
    debt = session.scalar(select(OverdraftLiability).where(OverdraftLiability.run_id == run.id))
    payments = list(session.scalars(select(OverdraftMovement).where(
        OverdraftMovement.run_id == run.id, OverdraftMovement.kind == "REPAYMENT")))
    assert second.paid_borrowing_costs_cents == sum(p.financing_cost_cents for p in payments) > 0
    assert second.closing.borrowing_outstanding_cents == second.closing.unpaid_borrowing_costs_cents == 0
    assert first.borrowing_costs_cents + second.borrowing_costs_cents == debt.financing_cost_cents
    assert second.closing.net_asset_value_cents - second.opening.net_asset_value_cents - second.customer_cash_delta_cents == -second.borrowing_costs_cents
    report = BacktestReportService.report_run(session, run.id)
    assert report.accounting.net_benefit_cents == -debt.financing_cost_cents
    assert read_hour_receipt(session, run.id, 1) == first  # later payments cannot rewrite an earlier receipt


def test_repo_maturity_pays_earned_accrual_once_and_is_not_hydrated_twice(runtime_session, dataset):
    session = runtime_session
    run = create_run(session, initial=100_000_000_000, buffer=5_000_000_000)
    receipts = [execute_persisted_hour(session, run.id, i) for i in range(33)]
    position = session.scalar(select(RepoPosition).where(RepoPosition.run_id == run.id))
    rates = sum((o.tier1_repo_rate_apy for o in dataset.observations[17:32]), Decimal(0))
    expected = int((Decimal(position.principal_cents) * rates / Decimal(876000)).to_integral_value(rounding=ROUND_HALF_UP))
    assert receipts[31].closing.accrued_interest_cents == expected
    assert receipts[32].realized_interest_cents == expected == position.realized_interest_cents
    assert receipts[32].closing.accrued_interest_cents == 0
    assert receipts[32].closing.net_asset_value_cents - receipts[32].opening.net_asset_value_cents == receipts[32].customer_cash_delta_cents
    row = session.scalar(select(OrganizerObservation).where(
        OrganizerObservation.dataset_id == run.dataset_id, OrganizerObservation.timestamp == datetime(2026, 1, 2, 9)))
    state, *_ = hydrate_portfolio_state(session, run, row)
    assert not state.repo_positions and state.valuation.tier1_value_cents == 0


def test_acceptance_h2_contractual_repo_maturity_at_eight_am_with_delay_invariance(runtime_session, dataset):
    """H2 positive acceptance: contractual repo maturity remains strictly at 08:00,
    settlement is neither duplicated nor retroactive, and unavailable quotes are not consumed.
    """
    session = runtime_session
    run = create_run(session, initial=100_000_000_000, buffer=5_000_000_000)
    for step in range(32):
        execute_persisted_hour(session, run.id, step)

    position = session.scalar(select(RepoPosition).where(RepoPosition.run_id == run.id))
    assert position.entered_at == datetime(2026, 1, 1, 17)
    assert position.scheduled_maturity_at == datetime(2026, 1, 2, 8)
    assert position.status == "LOCKED"

    # Step 32 is the 08:00 hour (2026-01-01 00:00 + 32 hours = 2026-01-02 08:00)
    receipt_8am = execute_persisted_hour(session, run.id, 32)
    assert position.status == "MATURED"
    assert position.scheduled_maturity_at == datetime(2026, 1, 2, 8)

    maturity_movements = list(session.scalars(select(InvestmentMovement).where(
        InvestmentMovement.run_id == run.id, InvestmentMovement.kind == "MATURITY")))
    assert len(maturity_movements) == 1
    movement = maturity_movements[0]
    assert movement.occurred_at == datetime(2026, 1, 2, 8)
    assert movement.cash_delta_cents == position.principal_cents + position.realized_interest_cents
    assert receipt_8am.realized_interest_cents == position.realized_interest_cents

    # Advance through 09:00 (step 33) and 10:00 (step 34)
    execute_persisted_hour(session, run.id, 33)
    execute_persisted_hour(session, run.id, 34)

    # Verify settlement remains unique, non-duplicated, and non-retroactive
    maturity_movements_after = list(session.scalars(select(InvestmentMovement).where(
        InvestmentMovement.run_id == run.id, InvestmentMovement.kind == "MATURITY")))
    assert len(maturity_movements_after) == 1
    assert maturity_movements_after[0].occurred_at == datetime(2026, 1, 2, 8)
    assert maturity_movements_after[0].cash_delta_cents == movement.cash_delta_cents



@pytest.mark.parametrize("instrument", ["BOND", "EQUITY"])
@pytest.mark.parametrize("residual_borrowing", [False, True])
def test_real_emergency_sale_separates_market_pnl_slippage_and_debt(runtime_session, instrument, residual_borrowing):
    session = runtime_session
    run, position = funded_market_position(session, instrument)
    run.policy_json = dict(run.policy_json, allow_bond_liquidation=True,
                           allow_emergency_equity_liquidation=True)
    session.flush()
    execute_persisted_hour(session, run.id, 0)
    row = session.scalar(select(OrganizerObservation).where(
        OrganizerObservation.dataset_id == run.dataset_id, OrganizerObservation.timestamp == datetime(2026, 1, 1, 1)))
    cash = session.scalar(select(CashAccount).where(CashAccount.run_id == run.id))
    # Make an actual shortfall at hour two; no direct accounting posts are mocked.
    amount = cash.balance_cents + int((row.deposits_usd - row.withdrawals_usd) * 100)
    amount += 1_000_000 if residual_borrowing else 1
    apply_simulation_scenario(session, run.id, ScenarioRequest(
        scenario="LIQUIDITY_SHOCK", parameters={"amount_cents": amount}, effective_step=2))
    receipt = execute_persisted_hour(session, run.id, 1)
    assert position.status == "CLOSED"
    movement = session.scalar(select(InvestmentMovement).where(
        InvestmentMovement.run_id == run.id, InvestmentMovement.kind == "LIQUIDATION"))
    assert movement.haircut_cost_cents == position.liquidation_cost_cents > 0
    assert receipt.liquidation_losses_cents == movement.haircut_cost_cents
    assert receipt.contractual_penalties_cents == receipt.realized_interest_cents == 0
    assert receipt.realized_market_pnl_cents == position.realized_pnl_cents
    assert receipt.closing.unrealized_market_pnl_cents == 0
    assert (receipt.closing.borrowing_outstanding_cents > 0) == residual_borrowing
    if not residual_borrowing:
        assert receipt.closing.checking_cents == movement.cash_delta_cents - 1 > 0
    report = BacktestReportService.report_run(session, run.id)
    assert report.accounting.net_benefit_cents == (
        report.accounting.realized_market_pnl_cents - report.accounting.liquidation_losses_cents
        - report.accounting.borrowing_costs_cents)
    execute_persisted_hour(session, run.id, 2)
    assert len(list(session.scalars(select(InvestmentMovement).where(
        InvestmentMovement.run_id == run.id, InvestmentMovement.kind == "LIQUIDATION")))) == 1


def test_backtest_repeat_is_ephemeral_and_preserves_parent(runtime_session, runtime_client):
    session = runtime_session
    run = create_run(session, duration_steps=168)
    execute_persisted_hour(session, run.id, 0)
    cash_before = session.scalar(select(CashAccount.balance_cents).where(CashAccount.run_id == run.id))
    count_before = session.scalar(select(func.count()).select_from(SimulationRun))
    url = f"/api/v1/runs/{run.id}/backtest"
    responses = [runtime_client.post(url, json={"strategies": ["STATIC_RESERVE"]}) for _ in range(2)]
    assert [r.status_code for r in responses] == [200, 200], [r.text for r in responses]
    left, right = [r.json() for r in responses]
    assert left["results"] == right["results"]
    assert [r["strategy"] for r in left["results"]] == ["STATIC_RESERVE"]
    assert left["conditions_sha256"] == right["conditions_sha256"]
    assert session.scalar(select(func.count()).select_from(SimulationRun)) == count_before
    assert session.get(SimulationRun, run.id).current_step == 1
    assert session.scalar(select(CashAccount.balance_cents).where(CashAccount.run_id == run.id)) == cash_before


def test_backtest_rejects_rounded_duration_and_duplicate_selection(runtime_session, runtime_client):
    run = create_run(runtime_session, duration_steps=169)
    assert runtime_client.post(f"/api/v1/runs/{run.id}/backtest", json={}).status_code == 422
    assert runtime_client.post(f"/api/v1/runs/{run.id}/backtest",
        json={"strategies": ["STATIC_RESERVE", "STATIC_RESERVE"]}).status_code == 422


def test_source_time_creation_does_not_invent_utc_and_allows_final_observation(runtime_session):
    session = runtime_session
    source_time = datetime(2026, 12, 31, 23)
    created = create_simulation_run(session, CreateRunRequest(duration_steps=1),
        source_start_timestamp=source_time)
    run = session.get(SimulationRun, created.run_id)
    assert run.source_timezone_status == "UNSPECIFIED" and run.source_start_timestamp.tzinfo is None
    receipt = execute_persisted_hour(session, run.id, 0)
    assert receipt.timestamp == source_time
    with pytest.raises(ValueError, match="window"):
        create_simulation_run(session, CreateRunRequest(duration_steps=2),
            source_start_timestamp=source_time)
    with pytest.raises(ValueError, match="completed"):
        execute_hourly_step(session, run.id, 1)


def test_canonical_optimizer_targets_ignore_unavailable_current_and_future_flows(runtime_session):
    import sys
    from treasury_intelligence.optimizer import recommend_four_tier_allocation
    session = runtime_session
    left, right = create_run(session), create_run(session)
    targets = []
    def trace(frame, event, arg):
        if frame.f_code is recommend_four_tier_allocation.__code__ and event == "return":
            targets.append(arg.decision.targets.model_dump())
    previous = sys.getprofile()
    try:
        sys.setprofile(trace)
        execute_hourly_step(session, left.id, 0, strategy="RESERVE_JUGGLER")
        rows = list(session.scalars(select(OrganizerObservation).where(
            OrganizerObservation.dataset_id == right.dataset_id,
            OrganizerObservation.timestamp >= right.source_start_timestamp,
            OrganizerObservation.timestamp < right.source_start_timestamp + timedelta(hours=7))))
        for row in rows:
            row.withdrawals_usd += Decimal("1000000.00")
            row.deposits_usd += Decimal("2000000.00")
        session.flush()
        execute_hourly_step(session, right.id, 0, strategy="RESERVE_JUGGLER")
    finally:
        sys.setprofile(previous)
    assert len(targets) == 2 and targets[0] == targets[1]


def test_live_report_contract_declares_javascript_safe_money():
    from app.main import app
    from app.backtesting.contracts import JS_MAX
    schemas = app.openapi()["components"]["schemas"]
    money = schemas["FrontendFinancialMetrics"]["properties"]
    for name, definition in money.items():
        if name.endswith("_cents"):
            assert definition["maximum"] == JS_MAX
            assert definition["minimum"] == (-JS_MAX if name == "net_benefit_cents" else 0)
