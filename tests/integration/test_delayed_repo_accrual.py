"""Confirmed simulation convention: delayed published APYs, fixed maturity."""
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import select

from test_four_tier_runtime import dataset, pg_engine, pg_url, session
from app.persistence.models import (
    CashAccount, InvestmentMovement, OrganizerObservation, PortfolioValuation, RepoPosition, SimulationRun, TreasuryDecision,
)
from app.services.hourly_engine import execute_hourly_step
from app.services.run_service import create_simulation_run
from app.v1_contracts import CreateRunRequest


def test_delayed_rates_settle_at_eight_once_without_later_true_up(session):
    first = session.scalar(select(OrganizerObservation).order_by(OrganizerObservation.timestamp))
    start = first.timestamp + timedelta(hours=16)
    created = create_simulation_run(session, CreateRunRequest(initial_cash_cents=100_000_000),
        source_start_timestamp=start)
    run = session.get(SimulationRun, created.run_id)
    run.policy_json = dict(run.policy_json, strategy="STATIC", operational_buffer_cents=0,
        minimum_sweep_cents=1, publication_delay_seconds=3600)
    rows = list(session.scalars(select(OrganizerObservation).where(
        OrganizerObservation.dataset_id == run.dataset_id,
        OrganizerObservation.timestamp >= start-timedelta(hours=3),
        OrganizerObservation.timestamp <= start+timedelta(hours=18)).order_by(OrganizerObservation.timestamp)))
    by_time = {r.timestamp: r for r in rows}
    for i, row in enumerate(rows):
        row.deposits_usd = row.withdrawals_usd = Decimal(0)
        row.tier1_repo_rate_apy = Decimal(i+1)
    session.flush()
    # 16:00 through 07:00: entry remains exactly 17:00, not shifted by publication delay.
    for step in range(16):
        execute_hourly_step(session, run.id, step)
    repo = session.scalar(select(RepoPosition).where(RepoPosition.run_id == run.id))
    assert repo.entered_at == start+timedelta(hours=1)
    assert repo.scheduled_maturity_at == start+timedelta(hours=16)
    assert repo.applicable_apy_pct == by_time[start-timedelta(hours=1)].tier1_repo_rate_apy
    expected_rates = [by_time[repo.entered_at+timedelta(hours=i-1)].tier1_repo_rate_apy for i in range(15)]
    expected = int((Decimal(repo.principal_cents)*sum(expected_rates)/Decimal(876000)).to_integral_value(rounding=ROUND_HALF_UP))
    assert repo.accrued_interest_cents == expected
    # The 07:00 rate is not available until 09:00. It cannot change 08:00 settlement.
    by_time[start+timedelta(hours=15)].tier1_repo_rate_apy = Decimal("9999")
    session.flush()
    execute_hourly_step(session, run.id, 16)
    maturity = session.scalar(select(InvestmentMovement).where(
        InvestmentMovement.run_id == run.id, InvestmentMovement.kind == "MATURITY"))
    assert maturity.occurred_at == repo.scheduled_maturity_at
    assert maturity.interest_cents == expected == repo.realized_interest_cents
    assert repo.status == "MATURED" and repo.accrued_interest_cents == 0
    cash = session.scalar(select(CashAccount).where(CashAccount.run_id == run.id))
    assert cash.balance_cents == 100_000_000+expected
    value = session.scalar(select(PortfolioValuation).where(
        PortfolioValuation.run_id == run.id, PortfolioValuation.reference_id == f"val-{run.id}-17"))
    assert value.tier1_value_cents == 0 and value.net_portfolio_value_cents == cash.balance_cents
    decision = session.scalar(select(TreasuryDecision).where(TreasuryDecision.run_id == run.id, TreasuryDecision.step == 17))
    evidence = next(r for r in decision.decision_details_json["orders_executed"] if r["action"] == "REDEEM_REPO")
    assert [Decimal(r["apy_pct"]) for r in evidence["hourly_rates"]] == expected_rates
    assert all(r["rate_available_at"] <= r["accrual_cutoff"] for r in evidence["hourly_rates"])
    frozen = maturity.interest_cents, maturity.cash_delta_cents
    execute_hourly_step(session, run.id, 17)  # the delayed quote is now published, no retroactive correction
    assert (maturity.interest_cents, maturity.cash_delta_cents) == frozen
    assert cash.balance_cents == 100_000_000+expected
    assert len(list(session.scalars(select(InvestmentMovement).where(
        InvestmentMovement.run_id == run.id, InvestmentMovement.kind == "MATURITY")))) == 1
