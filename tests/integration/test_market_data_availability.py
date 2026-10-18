"""Conservative publication gates for actual runtime decisions and snapshots."""
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from test_four_tier_runtime import dataset, pg_engine, pg_url, session
from app.persistence.models import OrganizerObservation, SimulationRun
from app.services.hourly_engine import execute_hourly_step
from app.services.run_service import create_simulation_run
from app.v1_contracts import CreateRunRequest
from app.services.treasury_adapter import (
    build_four_tier_policy, evaluate_liquidity_risk, get_hourly_forecasts_from_db,
    get_information_cutoff, hydrate_decision_portfolio, hydrate_portfolio_state,
    recommend_four_tier_allocation_decision,
)
from treasury_intelligence.liquidity_risk import CalibratedForecastAllowance


def test_canonical_decisions_use_only_closed_market_hours(session, monkeypatch):
    from app.services import treasury_adapter
    actual = treasury_adapter.recommend_four_tier_allocation
    requests, results = [], []
    def capture(request):
        requests.append(request)
        result = actual(request)
        results.append(result)
        return result
    monkeypatch.setattr(treasury_adapter, "recommend_four_tier_allocation", capture)
    first = session.scalar(select(OrganizerObservation).order_by(OrganizerObservation.timestamp))
    at = first.timestamp + timedelta(hours=1)
    left = create_simulation_run(session, CreateRunRequest(), source_start_timestamp=at)
    right = create_simulation_run(session, CreateRunRequest(), source_start_timestamp=at)
    execute_hourly_step(session, left.run_id, 0)
    for row in session.scalars(select(OrganizerObservation).where(
            OrganizerObservation.dataset_id == first.dataset_id,
            OrganizerObservation.timestamp >= at,
            OrganizerObservation.timestamp <= at + timedelta(hours=3))):
        row.tier2_bond_price_index *= Decimal("3")
        row.tier3_stock_index_price *= Decimal("4")
        row.tier1_repo_rate_apy = Decimal("70")
        row.tier2_bond_yield_pct = Decimal("60")
        row.tier3_stock_volatility_pct = Decimal("90")
    session.flush()
    execute_hourly_step(session, right.run_id, 0)
    assert len(requests) == 2
    for request in requests:
        state = request.liquidity.portfolio
        assert state.as_of == at
        assert state.market_prices.observed_at == first.timestamp
        assert state.market_rates.observed_at == first.timestamp
        assert request.rewards.assumptions_available_at <= at
    assert requests[0].liquidity.portfolio.market_prices == requests[1].liquidity.portfolio.market_prices
    assert requests[0].liquidity.portfolio.market_rates == requests[1].liquidity.portfolio.market_rates
    assert results[0].decision.targets == results[1].decision.targets


def test_first_source_hour_has_no_published_market_quote(session, monkeypatch):
    from app.services import treasury_adapter
    actual = treasury_adapter.recommend_four_tier_allocation
    seen = []
    def capture(request):
        seen.append(request)
        return actual(request)
    monkeypatch.setattr(treasury_adapter, "recommend_four_tier_allocation", capture)
    created = create_simulation_run(session, CreateRunRequest())
    result = execute_hourly_step(session, created.run_id, 0)
    assert result["step"] == 1  # no skipped first row
    assert len(seen) == 1  # canonical optimizer remains the real path, even with no quote
    state = seen[0].liquidity.portfolio
    assert state.market_prices is None and state.market_rates is None
    assert seen[0].rewards.assumptions_available_at <= state.as_of-timedelta(hours=1)


@pytest.mark.parametrize("delay,expected", [(0, 8), (1800, 7), (3600, 7), (7200, 6)])
def test_publication_boundary_for_training_and_market_quotes(session, delay, expected):
    first = session.scalar(select(OrganizerObservation).order_by(OrganizerObservation.timestamp))
    at = first.timestamp+timedelta(hours=9)
    created = create_simulation_run(session, CreateRunRequest(policy={"publication_delay_seconds": delay}),
        source_start_timestamp=at)
    run = session.get(SimulationRun, created.run_id)
    state, *_, published = hydrate_decision_portfolio(session, run,
        session.get(OrganizerObservation, (run.dataset_id, at)), delay)
    assert published.timestamp == first.timestamp+timedelta(hours=expected)
    assert published.timestamp+timedelta(hours=1, seconds=delay) <= at
    assert state.time_basis == "UNSPECIFIED" and state.as_of.tzinfo is None
    before = get_hourly_forecasts_from_db(session, run.dataset_id, at, publication_delay_seconds=delay)
    for row in session.scalars(select(OrganizerObservation).where(
            OrganizerObservation.dataset_id == run.dataset_id,
            OrganizerObservation.timestamp > get_information_cutoff(at, delay),
            OrganizerObservation.timestamp <= at+timedelta(hours=3))):
        row.withdrawals_usd += Decimal(10000)
    session.flush()
    after = get_hourly_forecasts_from_db(session, run.dataset_id, at, publication_delay_seconds=delay)
    assert before == after
    policy = build_four_tier_policy(run.policy_json)
    artifact = CalibratedForecastAllowance(time_basis="UNSPECIFIED", amount_cents=1,
        confidence=Decimal("0.95"), calibration_reference="test-only",
        calibrated_through=published.timestamp+timedelta(hours=1))
    with pytest.raises(ValueError, match="lookahead breach"):
        recommend_four_tier_allocation_decision(state, policy, published,
            calibrated_allowance=artifact, publication_delay_seconds=delay)


def test_risk_rejects_unpublished_market_inputs(session):
    first = session.scalar(select(OrganizerObservation).order_by(OrganizerObservation.timestamp))
    created = create_simulation_run(session, CreateRunRequest())
    run = session.get(SimulationRun, created.run_id)
    raw_state = hydrate_portfolio_state(session, run, first)[0]
    with pytest.raises(ValueError, match="publication cutoff"):
        evaluate_liquidity_risk(raw_state, build_four_tier_policy(run.policy_json), observation=first)


def test_delayed_closing_market_mark_uses_last_published_quote(session):
    from test_market_order_execution import order
    from app.persistence.models import BondPosition, CashAccount, PortfolioValuation
    from app.services.market_execution import execute_market_order
    first = session.scalar(select(OrganizerObservation).order_by(OrganizerObservation.timestamp))
    at = first.timestamp+timedelta(hours=9)
    created = create_simulation_run(session, CreateRunRequest(policy={"publication_delay_seconds": 3600}),
        source_start_timestamp=at)
    run = session.get(SimulationRun, created.run_id)
    run.policy_json = dict(run.policy_json, strategy="STATIC")
    cash = session.scalar(select(CashAccount).where(CashAccount.run_id == run.id))
    current = session.get(OrganizerObservation, (run.dataset_id, at))
    instruction = order(run, current, "BUY_BONDS").model_copy(update={
        "source_observation_timestamp": at-timedelta(hours=2)})
    fill = execute_market_order(session, run, cash, instruction, current, 1, publication_delay_seconds=3600)
    current.tier2_bond_price_index *= Decimal(10)  # unavailable until 11:00
    session.flush()
    execute_hourly_step(session, run.id, 0)
    position = session.get(BondPosition, fill["position_id"])
    eligible = session.get(OrganizerObservation, (run.dataset_id, at-timedelta(hours=1)))
    assert position.market_observation_timestamp == eligible.timestamp
    assert position.current_market_price_index == eligible.tier2_bond_price_index
    value = session.scalar(select(PortfolioValuation).where(
        PortfolioValuation.run_id == run.id, PortfolioValuation.reference_id == f"val-{run.id}-1"))
    assert value.tier2_market_value_cents == position.current_market_value_cents
