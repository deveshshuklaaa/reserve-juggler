"""Opening trades precede unpublished interval flows (real PostgreSQL/optimizer)."""
from datetime import datetime, timedelta
from decimal import Decimal
import json
import os
from pathlib import Path

import pytest
from sqlalchemy import event, select

from app.persistence.models import (
    CashAccount, InvestmentMovement, LedgerEntry, LiquidityBreach, OrganizerObservation,
    OverdraftLiability, PortfolioValuation, RepoPosition, SimulationRun, TreasuryDecision,
)
from app.services import treasury_adapter
from app.services.hourly_engine import StepConflictError, execute_hourly_step
from app.services.run_service import create_simulation_run
from app.v1_contracts import CreateRunRequest, TreasuryPolicy
from .test_runtime_persistence import runtime_database, runtime_session

OPENING = 13_245_535_717
AT = datetime(2026, 1, 1, 17)


def run_case(session, monkeypatch, *, delay, extra_cents, early=False, overdraft=True, extra_deposit_cents=0):
    created = create_simulation_run(session, CreateRunRequest(
        initial_cash_cents=OPENING, duration_steps=20,
        policy=TreasuryPolicy(publication_delay_seconds=delay,
            early_redemption_allowed=early, allow_overdraft=overdraft,
            max_overdraft_cents=5_000_000_000 if overdraft else 0)),
        source_start_timestamp=AT)
    run = session.get(SimulationRun, created.run_id)
    row = session.get(OrganizerObservation, (run.dataset_id, AT))
    original = row.withdrawals_usd
    original_deposit = row.deposits_usd
    row.deposits_usd += Decimal(extra_deposit_cents) / 100
    row.withdrawals_usd = original + Decimal(extra_cents) / 100
    session.flush()
    requests, responses, entries = [], [], []
    actual = treasury_adapter.recommend_four_tier_allocation
    def capture(request):
        requests.append(request)
        response = actual(request)
        responses.append(response)
        return response
    def track(session, flush_context, instances):
        entries.extend(e for e in session.new if isinstance(e, LedgerEntry) and e.run_id == run.id)
    monkeypatch.setattr(treasury_adapter, 'recommend_four_tier_allocation', capture)
    event.listen(session, 'before_flush', track)
    try:
        # Production SessionLocal disables autoflush; correctness must not rely on it.
        with session.no_autoflush:
            execute_hourly_step(session, run.id, 0, strategy='RESERVE_JUGGLER')
    finally:
        event.remove(session, 'before_flush', track)
        monkeypatch.setattr(treasury_adapter, 'recommend_four_tier_allocation', actual)
        row.withdrawals_usd = original
        row.deposits_usd = original_deposit
        session.flush()
    assert requests[0].liquidity.portfolio.cash.balance_cents == OPENING
    cutoff = AT-timedelta(hours=1, seconds=delay)
    assert all(q is None or q.observed_at <= cutoff for q in (
        requests[0].liquidity.portfolio.market_rates, requests[0].liquidity.portfolio.market_prices))
    order = next(o for o in responses[0].decision.orders if o.action == 'INVEST_REPO')
    decision = session.scalar(select(TreasuryDecision).where(TreasuryDecision.run_id == run.id, TreasuryDecision.step == 1))
    movement = session.scalar(select(InvestmentMovement).where(
        InvestmentMovement.run_id == run.id, InvestmentMovement.kind == 'INVESTMENT'))
    cash = session.scalar(select(CashAccount).where(CashAccount.run_id == run.id))
    value = session.scalar(select(PortfolioValuation).where(PortfolioValuation.run_id == run.id, PortfolioValuation.valued_at == AT+timedelta(hours=1)))
    evidence = dict(run_id=str(run.id), delay=delay, extra_withdrawals_cents=extra_cents,
        extra_deposits_cents=extra_deposit_cents,
        request=requests[0].model_dump(mode='json'), response=responses[0].model_dump(mode='json'),
        request_id=requests[0].request_id, order_id=str(order.id), decision_receipt_id=str(decision.id),
        movement_id=str(movement.id), ledger_entry_id=str(movement.ledger_entry_id),
        recommended_repo_cents=order.amount_cents, executed_repo_cents=movement.principal_cents,
        opening_cash_cents=OPENING, reserve_cents=responses[0].decision.targets.tier0_target_cents,
        closing_cash_cents=cash.balance_cents, nav_cents=value.net_portfolio_value_cents,
        liabilities_cents=value.liabilities_cents, payout=decision.decision_details_json['payout'],
        reserve_check=decision.decision_details_json.get('reserve_check'),
        financing=decision.decision_details_json['financing'],
        ledger_trace=[dict(id=str(e.id), kind=e.entry_type, before=e.balance_before_cents,
                           after=e.balance_after_cents, amount=e.amount_cents) for e in entries])
    out = os.getenv('RJ16_EVIDENCE_DIR')
    if out:
        Path(out).mkdir(parents=True, exist_ok=True)
        Path(out, f'chronology-{delay}-{extra_cents}-{extra_deposit_cents}-{early}-{overdraft}.json').write_text(
            json.dumps(evidence, indent=2), encoding='utf-8')
    print('CHRONOLOGY_EVIDENCE', json.dumps({k:v for k,v in evidence.items() if k not in ('request','response','ledger_trace','financing')}), flush=True)
    return run, order, decision, movement, cash, value, entries


def reconcile(session, run, decision, cash, value, entries):
    balance = OPENING
    for entry in entries:
        assert entry.balance_before_cents == balance
        balance = entry.balance_after_cents
        assert balance >= 0
        assert abs(entry.balance_after_cents-entry.balance_before_cents) == entry.amount_cents
    assert balance == cash.balance_cents
    payout = decision.decision_details_json['payout']
    assert payout['requested_amount_cents'] == payout['executed_amount_cents'] + payout['unpaid_amount_cents']
    debts = list(session.scalars(select(OverdraftLiability).where(OverdraftLiability.run_id == run.id)))
    assert value.liabilities_cents == sum(d.outstanding_principal_cents+d.financing_cost_cents for d in debts)
    assert value.net_portfolio_value_cents == value.total_portfolio_value_cents - value.liabilities_cents
    inflow = sum(e.amount_cents for e in entries if e.entry_type == 'CUSTOMER_DEPOSIT_INFLOW')
    fees = sum(m.haircut_cost_cents for m in session.scalars(select(InvestmentMovement).where(InvestmentMovement.run_id == run.id)))
    interest = value.tier1_value_cents-value.tier1_principal_cents
    assert value.net_portfolio_value_cents == OPENING+inflow-payout['executed_amount_cents']-fees-sum(d.financing_cost_cents for d in debts)+interest
    if cash.balance_cents < decision.required_reserve_cents:
        assert decision.decision_details_json['reserve_check']['reserve_breach'] is True
    before = (len(entries), cash.balance_cents, run.current_step)
    count = len(list(session.scalars(select(LedgerEntry).where(LedgerEntry.run_id == run.id))))
    with pytest.raises(StepConflictError):
        execute_hourly_step(session, run.id, 0, strategy='RESERVE_JUGGLER')
    assert len(list(session.scalars(select(LedgerEntry).where(LedgerEntry.run_id == run.id)))) == count
    assert (len(entries), cash.balance_cents, run.current_step) == before


@pytest.mark.parametrize('delay', [0, 3600])
def test_immediate_seventeen_repo_fill_ignores_unpublished_withdrawals(runtime_session, monkeypatch, delay):
    left = run_case(runtime_session, monkeypatch, delay=delay, extra_cents=0)
    right = run_case(runtime_session, monkeypatch, delay=delay, extra_cents=500_000_000)
    for run, order, decision, movement, cash, value, entries in (left, right):
        assert movement.principal_cents == order.amount_cents
        assert movement.principal_cents <= OPENING - decision.required_reserve_cents
        if delay == 0:
            assert decision.required_reserve_cents == 1_025_916_986
            assert movement.principal_cents == 12_219_618_731
        # Flush order is the actual native-hour execution sequence; no invented timestamps.
        types = [e.entry_type for e in entries]
        assert types.index('OVERNIGHT_REPO_SWEEP_DEBIT') < types.index('CUSTOMER_DEPOSIT_INFLOW')
        assert all(e.event_at == AT and e.event_at.tzinfo is None for e in entries)
        reconcile(runtime_session, run, decision, cash, value, entries)
    assert left[3].principal_cents == right[3].principal_cents
    assert right[4].balance_cents == left[4].balance_cents-500_000_000


@pytest.mark.parametrize('early,overdraft', [(False, True), (False, False), (True, False)])
def test_post_fill_shortfall_uses_real_waterfall_and_reconciles(runtime_session, monkeypatch, early, overdraft):
    run, order, decision, movement, cash, value, entries = run_case(
        runtime_session, monkeypatch, delay=0, extra_cents=2_000_000_000, early=early, overdraft=overdraft)
    assert movement.principal_cents == order.amount_cents == 12_219_618_731
    reconcile(runtime_session, run, decision, cash, value, entries)
    payout = decision.decision_details_json['payout']
    if early:
        assert any(e.entry_type == 'REPO_EARLY_REDEMPTION' for e in entries)
        assert value.tier1_principal_cents == 0
        assert sum(m.haircut_cost_cents for m in runtime_session.scalars(select(InvestmentMovement).where(
            InvestmentMovement.run_id == run.id))) == 61_098_094
        assert payout['unpaid_amount_cents'] == 0
    else:
        assert runtime_session.scalar(select(LiquidityBreach).where(LiquidityBreach.run_id == run.id)) is not None
        assert (value.liabilities_cents > 0) is overdraft
        assert (payout['unpaid_amount_cents'] > 0) is not overdraft


@pytest.mark.parametrize('delay', [0, 3600])
def test_eight_am_contractual_settlement_precedes_optimizer_once(runtime_session, monkeypatch, delay):
    session = runtime_session
    created = create_simulation_run(session, CreateRunRequest(
        initial_cash_cents=OPENING, duration_steps=20,
        policy=TreasuryPolicy(publication_delay_seconds=delay)), source_start_timestamp=AT)
    run = session.get(SimulationRun, created.run_id)
    for row in session.scalars(select(OrganizerObservation).where(
            OrganizerObservation.dataset_id == run.dataset_id,
            OrganizerObservation.timestamp >= AT,
            OrganizerObservation.timestamp <= AT+timedelta(hours=16))):
        row.deposits_usd = row.withdrawals_usd = Decimal(0)
    session.flush()
    for step in range(15):
        execute_hourly_step(session, run.id, step, strategy='RESERVE_JUGGLER')
    position = session.scalar(select(RepoPosition).where(RepoPosition.run_id == run.id))
    assert position.entered_at == AT and position.scheduled_maturity_at == AT+timedelta(hours=15)
    assert position.status == 'LOCKED'
    captured = []
    actual = treasury_adapter.recommend_four_tier_allocation
    def capture(request):
        captured.append(request)
        return actual(request)
    monkeypatch.setattr(treasury_adapter, 'recommend_four_tier_allocation', capture)
    execute_hourly_step(session, run.id, 15, strategy='RESERVE_JUGGLER')
    assert len(captured) == 1
    context = captured[0].liquidity.portfolio
    assert not context.repo_positions
    assert position.status == 'MATURED'
    assert context.cash.balance_cents == OPENING+position.realized_interest_cents
    assert context.as_of.hour == 8 and context.as_of.tzinfo is None and context.time_basis == 'UNSPECIFIED'
    with pytest.raises(StepConflictError):
        execute_hourly_step(session, run.id, 15, strategy='RESERVE_JUGGLER')
    execute_hourly_step(session, run.id, 16, strategy='RESERVE_JUGGLER')
    maturities = list(session.scalars(select(InvestmentMovement).where(
        InvestmentMovement.run_id == run.id, InvestmentMovement.kind == 'MATURITY')))
    assert len(maturities) == 1
    assert maturities[0].occurred_at == position.scheduled_maturity_at
    assert maturities[0].cash_delta_cents == position.principal_cents+position.realized_interest_cents


@pytest.mark.parametrize('delay', [0, 3600])
def test_unpublished_deposit_does_not_fund_opening_repo(runtime_session, monkeypatch, delay):
    left = run_case(runtime_session, monkeypatch, delay=delay, extra_cents=0)
    right = run_case(runtime_session, monkeypatch, delay=delay, extra_cents=0,
                     extra_deposit_cents=500_000_000)
    assert left[3].principal_cents == right[3].principal_cents == left[1].amount_cents
    assert right[4].balance_cents == left[4].balance_cents+500_000_000
    for run, order, decision, movement, cash, value, entries in (left, right):
        assert movement.principal_cents <= OPENING-decision.required_reserve_cents
        reconcile(runtime_session, run, decision, cash, value, entries)
