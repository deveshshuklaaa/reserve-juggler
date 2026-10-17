"""Actual capped financing and payout evidence, not a fake execution engine."""
from decimal import Decimal

import pytest
from sqlalchemy import select

from test_four_tier_runtime import dataset, pg_engine, pg_url, session
from app.persistence.models import (
    CashAccount, LedgerEntry, LiquidityBreach, OrganizerObservation,
    OverdraftLiability, OverdraftMovement, PortfolioValuation, SimulationRun, TreasuryDecision,
)
from app.services.hourly_engine import execute_hourly_step
from app.services.run_service import create_simulation_run
from app.v1_contracts import CreateRunRequest


@pytest.mark.parametrize("initial,cap,enabled,paid,status", [
    (2_000_000, 100_000, True, 1_000_000, "EXECUTED"),
    (400_000, 100_000, True, 500_000, "PARTIALLY_EXECUTED"),
    (0, 0, False, 0, "FAILED"),
    (400_000, 0, False, 400_000, "PARTIALLY_EXECUTED"),
])
def test_payout_records_only_funded_legs_and_respects_cap(session, initial, cap, enabled, paid, status):
    created = create_simulation_run(session, CreateRunRequest(initial_cash_cents=initial))
    run = session.get(SimulationRun, created.run_id)
    run.policy_json = dict(run.policy_json, strategy="STATIC", allow_overdraft=enabled, max_overdraft_cents=cap)
    row = session.scalar(select(OrganizerObservation).where(
        OrganizerObservation.dataset_id == run.dataset_id,
        OrganizerObservation.timestamp == run.source_start_timestamp))
    # Rollback-only PostgreSQL fixture; immutable source CSV is never edited.
    row.deposits_usd, row.withdrawals_usd = Decimal(0), Decimal(10000)
    session.flush()
    result = execute_hourly_step(session, run.id, 0)
    ledgers = list(session.scalars(select(LedgerEntry).where(LedgerEntry.run_id == run.id, LedgerEntry.step == 1)))
    actual_paid = sum(e.amount_cents for e in ledgers if e.entry_type == "CUSTOMER_WITHDRAWAL_OUTFLOW")
    borrowed = sum(e.amount_cents for e in ledgers if e.entry_type == "OVERDRAFT_DRAW_BORROW")
    assert borrowed <= cap, "Emergency execution exceeded the configured principal cap"
    assert actual_paid == paid
    assert all(e.amount_cents > 0 for e in ledgers)
    decision = session.scalar(select(TreasuryDecision).where(TreasuryDecision.run_id == run.id, TreasuryDecision.step == 1))
    payout = decision.decision_details_json["payout"]
    assert payout["receipt_version"] == "runtime-execution-v1"
    assert payout["status"] == status
    assert payout["requested_amount_cents"] == 1_000_000
    assert payout["executed_amount_cents"] == paid
    assert payout["unpaid_amount_cents"] == 1_000_000-paid
    assert payout["overdraft_draw_cents"] == borrowed
    assert payout["run_id"] == str(run.id) and payout["step"] == 1
    financing_receipts = decision.decision_details_json["financing"]
    movements = list(session.scalars(select(OverdraftMovement).where(OverdraftMovement.run_id == run.id)))
    assert {r["movement_id"] for r in financing_receipts} == {str(m.id) for m in movements}
    assert sum(r["cash_delta_cents"] for r in financing_receipts) == borrowed
    if paid < 1_000_000:
        assert decision.execution_status != "EXECUTED"
        assert decision.decision_details_json["executed"] is False
        assert payout["settlement_status"] == ("UNPAID" if paid == 0 else "PARTIALLY_PAID")
    liabilities = list(session.scalars(select(OverdraftLiability).where(OverdraftLiability.run_id == run.id)))
    assert sum(o.borrowed_cents for o in liabilities) == borrowed
    value = session.scalar(select(PortfolioValuation).where(
        PortfolioValuation.run_id == run.id, PortfolioValuation.reference_id == f"val-{run.id}-1"))
    financing = sum(o.financing_cost_cents or 0 for o in liabilities)
    assert value.liabilities_cents == borrowed + financing
    assert value.net_portfolio_value_cents == initial - paid - financing
    assert result["checking_cents"] >= 0
    if borrowed or paid < 1_000_000:
        assert session.scalar(select(LiquidityBreach.id).where(LiquidityBreach.run_id == run.id))


def test_disabled_overdraft_uses_zero_default_limit():
    from app.services.treasury_adapter import build_four_tier_policy
    policy = build_four_tier_policy({"allow_overdraft": False})
    assert not policy.allow_overdraft and policy.max_overdraft_cents == 0


def test_public_policy_can_configure_borrowing_capacity():
    request = CreateRunRequest.model_validate({"policy": {
        "allow_overdraft": True, "max_overdraft_cents": 12345}})
    assert request.policy.max_overdraft_cents == 12345
    disabled = CreateRunRequest.model_validate({"policy": {"allow_overdraft": False}})
    assert disabled.policy.max_overdraft_cents == 0
    with pytest.raises(ValueError):
        CreateRunRequest.model_validate({"policy": {"allow_overdraft": False, "max_overdraft_cents": 1}})


def test_second_shortfall_cannot_draw_past_existing_principal(session):
    created = create_simulation_run(session, CreateRunRequest(initial_cash_cents=0))
    run = session.get(SimulationRun, created.run_id)
    run.policy_json = dict(run.policy_json, strategy="STATIC", allow_overdraft=True, max_overdraft_cents=100_000)
    rows = list(session.scalars(select(OrganizerObservation).where(
        OrganizerObservation.dataset_id == run.dataset_id,
        OrganizerObservation.timestamp >= run.source_start_timestamp).order_by(OrganizerObservation.timestamp).limit(2)))
    for row in rows:
        row.deposits_usd, row.withdrawals_usd = Decimal(0), Decimal(10000)
    session.flush()
    execute_hourly_step(session, run.id, 0)
    execute_hourly_step(session, run.id, 1)
    debt = list(session.scalars(select(OverdraftLiability).where(OverdraftLiability.run_id == run.id)))
    assert sum(o.outstanding_principal_cents for o in debt) == 100_000
    assert len(debt) == 1
    second = session.scalar(select(TreasuryDecision).where(TreasuryDecision.run_id == run.id, TreasuryDecision.step == 2))
    assert second.decision_details_json["payout"]["executed_amount_cents"] == 0
    assert second.decision_details_json["payout"]["status"] == "FAILED"
    assert second.decision_details_json["payout"]["unpaid_financing_cost_cents"] > 0
