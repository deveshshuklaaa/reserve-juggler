"""Focused PostgreSQL H2 evidence, including explicit zero/one-hour delays."""
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
import json
from pathlib import Path
import sys

import pytest
from sqlalchemy import select

sys.path.insert(0, str(Path.cwd()/"tests"))
from backtesting.conftest import dataset
from backtesting.test_runtime_persistence import runtime_database, runtime_session
from app.persistence.models import (
    CashAccount, InvestmentMovement, LedgerEntry, OrganizerObservation,
    PortfolioValuation, RepoPosition, SimulationRun, TreasuryDecision,
)
from app.services import treasury_adapter
from app.services.hourly_engine import execute_hourly_step
from app.services.run_service import create_simulation_run, get_simulation_snapshot
from app.v1_contracts import CreateRunRequest, TreasuryPolicy
from treasury_intelligence.portfolio import PortfolioState


@pytest.mark.parametrize("delay_seconds", [0, 3600])
def test_eight_am_settlement_is_causal_unique_and_source_naive(runtime_session, monkeypatch, delay_seconds):
    session = runtime_session
    first = session.scalar(select(OrganizerObservation).order_by(OrganizerObservation.timestamp))
    start = first.timestamp+timedelta(hours=17)
    maturity = start+timedelta(hours=15)
    created = create_simulation_run(session, CreateRunRequest(
        initial_cash_cents=100_000_000_000, duration_steps=20,
        policy=TreasuryPolicy(operational_buffer_cents=1_000_000,
            minimum_sweep_cents=1, publication_delay_seconds=delay_seconds)),
        source_start_timestamp=start)
    run = session.get(SimulationRun, created.run_id)
    rows = list(session.scalars(select(OrganizerObservation).where(
        OrganizerObservation.dataset_id == run.dataset_id,
        OrganizerObservation.timestamp >= start-timedelta(hours=3),
        OrganizerObservation.timestamp <= maturity+timedelta(hours=3)
    ).order_by(OrganizerObservation.timestamp)))
    for i, row in enumerate(rows):
        # Rollback-only PG fixture; original organizer CSV is untouched.
        row.deposits_usd = row.withdrawals_usd = Decimal(0)
        row.tier1_repo_rate_apy = Decimal("1")+Decimal(i)/Decimal(10)
    by_time = {r.timestamp:r for r in rows}
    session.flush()
    for step in range(15):  # 17:00..07:00, closing at 08:00
        execute_hourly_step(session, run.id, step, strategy="STATIC")
    position = session.scalar(select(RepoPosition).where(RepoPosition.run_id == run.id))
    assert position.status == "LOCKED"
    assert position.entered_at == start and position.scheduled_maturity_at == maturity
    assert maturity.hour == 8
    expected_rates = []
    expected_times = []
    for offset in range(15):
        cutoff = start+timedelta(hours=offset)-timedelta(seconds=delay_seconds)
        selected = max((r for r in rows if r.timestamp <= cutoff), key=lambda r:r.timestamp)
        expected_times.append(selected.timestamp)
        expected_rates.append(selected.tier1_repo_rate_apy)
    expected_interest = int((Decimal(position.principal_cents)*sum(expected_rates)/Decimal(876000)).to_integral_value(rounding=ROUND_HALF_UP))
    assert position.accrued_interest_cents == expected_interest
    # At 08:00 this complete hour's price/APY has NOT yet been published.
    unavailable = by_time[maturity]
    unavailable.tier1_repo_rate_apy = Decimal("99.99")
    unavailable.tier2_bond_price_index = Decimal("999")
    unavailable.tier3_stock_index_price = Decimal("99999")
    unavailable.tier3_stock_volatility_pct = Decimal("99")
    session.flush()
    captured = []
    canonical = treasury_adapter.recommend_four_tier_allocation
    def capture(request):
        captured.append(request)
        return canonical(request)
    monkeypatch.setattr(treasury_adapter, "recommend_four_tier_allocation", capture)
    result = execute_hourly_step(session, run.id, 15, strategy="RESERVE_JUGGLER")
    assert len(captured) == 1
    context = captured[0].liquidity.portfolio
    cutoff = maturity-timedelta(hours=1, seconds=delay_seconds)
    assert context.as_of == maturity and context.time_basis == "UNSPECIFIED"
    assert context.market_rates.observed_at <= cutoff
    assert context.market_prices.observed_at <= cutoff
    assert context.market_rates.repo_apy_pct != Decimal("99.99")
    assert context.market_prices.bond_price_index != Decimal("999")
    assert all(p.time_basis == "UNSPECIFIED" and p.start_at.tzinfo is None
        for p in captured[0].liquidity.forecast)
    with pytest.raises(ValueError):
        PortfolioState.model_validate(context.model_dump() | {"time_basis":"UTC"})
    movements = list(session.scalars(select(InvestmentMovement).where(
        InvestmentMovement.run_id == run.id, InvestmentMovement.kind == "MATURITY")))
    credits = list(session.scalars(select(LedgerEntry).where(
        LedgerEntry.run_id == run.id, LedgerEntry.entry_type == "REPO_MATURITY_CREDIT")))
    assert len(movements) == len(credits) == 1
    movement, credit = movements[0], credits[0]
    assert movement.occurred_at == credit.event_at == position.scheduled_maturity_at == maturity
    assert movement.interest_cents == position.realized_interest_cents == expected_interest
    assert movement.cash_delta_cents == credit.amount_cents == position.principal_cents+expected_interest
    assert position.status == "MATURED" and position.accrued_interest_cents == 0
    value = session.scalar(select(PortfolioValuation).where(
        PortfolioValuation.run_id == run.id, PortfolioValuation.reference_id == f"val-{run.id}-16"))
    assert value.valued_at == maturity+timedelta(hours=1)
    assert value.tier1_value_cents == 0
    assert value.net_portfolio_value_cents == run.initial_cash_cents+expected_interest
    cash = session.scalar(select(CashAccount).where(CashAccount.run_id == run.id))
    assert cash.balance_cents == value.net_portfolio_value_cents
    decision = session.scalar(select(TreasuryDecision).where(
        TreasuryDecision.run_id == run.id, TreasuryDecision.step == 16))
    rate_evidence = next(e for e in decision.decision_details_json["orders_executed"]
        if e["action"] == "REDEEM_REPO")["hourly_rates"]
    assert [Decimal(e["apy_pct"]) for e in rate_evidence] == expected_rates
    assert [datetime.fromisoformat(e["rate_observed_at"]) for e in rate_evidence] == expected_times
    assert all(datetime.fromisoformat(e["rate_available_at"]) <= datetime.fromisoformat(e["accrual_cutoff"])
        for e in rate_evidence)
    source_times = [position.entered_at, position.scheduled_maturity_at, movement.occurred_at,
        credit.event_at, credit.source_observation_timestamp, value.valued_at]
    assert run.source_timezone_status == "UNSPECIFIED"
    assert all(t.tzinfo is None for t in source_times)
    snapshot = get_simulation_snapshot(session, run.id)
    assert datetime.fromisoformat(snapshot.four_tier.timestamp).tzinfo is None
    assert datetime.fromisoformat(snapshot.four_tier.market_observation_timestamp).tzinfo is None
    # Top-level timestamp is the current server operation clock, NOT source time.
    assert snapshot.timestamp.utcoffset() == timedelta(0)
    print("POSTGRES_H2_EVIDENCE", json.dumps({
        "run_id":str(run.id), "publication_delay_seconds":delay_seconds,
        "entered_at":position.entered_at.isoformat(),
        "scheduled_maturity_at":maturity.isoformat(),
        "maturity_event_at":movement.occurred_at.isoformat(),
        "credit_event_at":credit.event_at.isoformat(),
        "closing_valuation_at":value.valued_at.isoformat(),
        "principal_cents":position.principal_cents, "interest_cents":expected_interest,
        "settlement_cents":movement.cash_delta_cents,
        "decision_market_observed_at":context.market_prices.observed_at.isoformat(),
        "last_earning_rate_observed_at":expected_times[-1].isoformat(),
        "time_basis":context.time_basis,
        "snapshot_source_timestamp":snapshot.four_tier.timestamp,
        "snapshot_operation_timestamp":snapshot.timestamp.isoformat(),
        "net_asset_value_cents":value.net_portfolio_value_cents,
    }), flush=True)
    frozen = (movement.interest_cents, movement.cash_delta_cents, position.realized_interest_cents)
    execute_hourly_step(session, run.id, 16, strategy="STATIC")  # 09:00
    execute_hourly_step(session, run.id, 17, strategy="STATIC")  # 10:00
    assert (movement.interest_cents, movement.cash_delta_cents, position.realized_interest_cents) == frozen
    assert len(list(session.scalars(select(InvestmentMovement).where(
        InvestmentMovement.run_id == run.id, InvestmentMovement.kind == "MATURITY")))) == 1
    assert len(list(session.scalars(select(LedgerEntry).where(
        LedgerEntry.run_id == run.id, LedgerEntry.entry_type == "REPO_MATURITY_CREDIT")))) == 1
    assert not list(session.scalars(select(InvestmentMovement).where(
        InvestmentMovement.run_id == run.id, InvestmentMovement.kind == "INTEREST")))
    assert cash.balance_cents == run.initial_cash_cents+expected_interest
    print("NO_RETROACTIVE_TRUE_UP", delay_seconds, "PASS", flush=True)
