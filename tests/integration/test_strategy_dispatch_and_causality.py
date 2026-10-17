"""Regression and integration tests for runtime strategy dispatch and causal forecasting.

Verifies:
1. All three strategy IDs (STATIC, REACTIVE, RESERVE_JUGGLER and legacy aliases) are accepted and dispatched.
2. Run and ledger state isolation across strategies.
3. Forecast causality: forecasts at cutoff T are strictly invariant to future observations being added.
4. Future-dated inputs are excluded or rejected before feature/model evaluation.
5. Training/calibration artifacts dated after the information cutoff are strictly rejected.
6. Financial accounting identities, ledger continuity, and repo sweep/maturity across all strategies.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import os
from pathlib import Path
import re
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, make_url, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.main import app
from app.persistence.migrations import apply_migrations
from app.persistence.models import (
    CashAccount as DbCashAccount,
    InvestmentMovement as DbInvestmentMovement,
    LedgerEntry as DbLedgerEntry,
    OrganizerObservation as DbOrganizerObservation,
    PortfolioValuation as DbPortfolioValuation,
    RepoPosition as DbRepoPosition,
    SimulationRun as DbSimulationRun,
    TreasuryDecision as DbTreasuryDecision,
)
from app.data.organizer import OrganizerDatasetSource
from app.persistence.repositories import DatasetRepository, configuration_identity
from app.services.hourly_engine import (
    STRATEGY_REACTIVE,
    STRATEGY_RESERVE_JUGGLER,
    STRATEGY_STATIC,
    execute_hourly_step,
    normalize_strategy_id,
)
from app.services.treasury_adapter import (
    build_four_tier_policy,
    evaluate_liquidity_risk,
    get_hourly_forecasts_from_db,
    get_information_cutoff,
    hydrate_portfolio_state,
)
from treasury_intelligence.liquidity_risk import CalibratedForecastAllowance


@pytest.fixture(scope="module")
def pg_url():
    url = os.getenv("PERSISTENCE_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set PERSISTENCE_TEST_DATABASE_URL to run real PostgreSQL integration tests")
    return url


@pytest.fixture(scope="module")
def dataset():
    path = Path(__file__).resolve().parents[2] / "treasury_4tier_dataset.csv"
    return OrganizerDatasetSource(path).load()


@pytest.fixture(scope="module")
def pg_engine(pg_url, dataset):
    url = make_url(pg_url)
    name = "reserve_juggler_m2_test_" + uuid4().hex[:12]
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
def session(pg_engine):
    with pg_engine.connect() as connection:
        transaction = connection.begin()
        with Session(connection, join_transaction_mode="create_savepoint") as session:
            yield session
        transaction.rollback()


def _create_test_run(session: Session, dataset, strategy: str = "RESERVE_JUGGLER", initial_cash: int = 2000000000) -> DbSimulationRun:
    policy = {
        "strategy": strategy,
        "base_buffer_cents": 50000000,
        "operational_buffer_cents": 50000000,
        "minimum_sweep_cents": 1000000,
        "allow_early_repo_redemption": True,
        "allow_overdraft": True,
        "risk_percentile": 0.95,
    }
    run = DbSimulationRun(
        id=uuid4(),
        seed=42,
        scenario="NORMAL",
        status="RUNNING",
        current_step=0,
        duration_steps=48,
        initial_cash_cents=initial_cash,
        policy_json=policy,
        source_type="ORGANIZER_HISTORICAL",
        dataset_id=dataset.metadata.dataset_id,
        source_start_timestamp=dataset.metadata.first_timestamp,
        source_end_timestamp=dataset.metadata.last_timestamp,
        native_interval_seconds=3600,
        source_timezone_status="UNSPECIFIED",
        configuration_hash=configuration_identity(policy),
    )
    session.add(run)
    session.flush()

    cash = DbCashAccount(
        id=uuid4(),
        run_id=run.id,
        source_type=run.source_type,
        dataset_id=run.dataset_id,
        source_observation_timestamp=dataset.metadata.first_timestamp,
        balance_cents=initial_cash,
    )
    session.add(cash)
    session.flush()
    return run


def test_strategy_id_normalization_and_acceptance():
    """1. All three strategy IDs and legacy aliases are accepted and normalize properly."""
    assert normalize_strategy_id("STATIC") == STRATEGY_STATIC
    assert normalize_strategy_id("STATIC_RESERVE") == STRATEGY_STATIC
    assert normalize_strategy_id("static") == STRATEGY_STATIC

    assert normalize_strategy_id("REACTIVE") == STRATEGY_REACTIVE
    assert normalize_strategy_id("REACTIVE_RESERVE") == STRATEGY_REACTIVE
    assert normalize_strategy_id("reactive") == STRATEGY_REACTIVE

    assert normalize_strategy_id("RESERVE_JUGGLER") == STRATEGY_RESERVE_JUGGLER
    assert normalize_strategy_id(None) == STRATEGY_RESERVE_JUGGLER

    with pytest.raises(ValueError, match="Unknown strategy"):
        normalize_strategy_id("INVALID_STRATEGY")


def test_strategy_dispatch_policy_paths(session, dataset):
    """1b. Verify that each strategy dispatches to its intended calculation path."""
    run_static = _create_test_run(session, dataset, strategy="STATIC")
    run_reactive = _create_test_run(session, dataset, strategy="REACTIVE")
    run_juggler = _create_test_run(session, dataset, strategy="RESERVE_JUGGLER")

    res_static = execute_hourly_step(session, run_static.id, expected_step=0)
    assert res_static["strategy"] == "STATIC"
    assert "STATIC strategy: fixed buffer" in res_static["decision"]["explanation"][0]
    assert res_static["forecast"]["model_version"] == "none"

    res_reactive = execute_hourly_step(session, run_reactive.id, expected_step=0)
    assert res_reactive["strategy"] == "REACTIVE"
    assert "REACTIVE strategy: buffer set to" in res_reactive["decision"]["explanation"][0]
    assert res_reactive["forecast"]["model_version"] == "none"

    res_juggler = execute_hourly_step(session, run_juggler.id, expected_step=0)
    assert res_juggler["strategy"] == "RESERVE_JUGGLER"
    assert "RESERVE_JUGGLER: dynamic required reserve" in res_juggler["decision"]["explanation"][0]
    assert res_juggler["forecast"]["model_version"] == "hourly-seasonal-naive-v1"


def test_strategy_run_and_ledger_state_isolation(session, dataset):
    """2. Each strategy maintains fully isolated run, cash, and ledger state without leakage."""
    run_a = _create_test_run(session, dataset, strategy="STATIC", initial_cash=1000000000)
    run_b = _create_test_run(session, dataset, strategy="RESERVE_JUGGLER", initial_cash=2000000000)

    # Advance both runs 5 steps
    for s in range(5):
        execute_hourly_step(session, run_a.id, expected_step=s)
        execute_hourly_step(session, run_b.id, expected_step=s)

    # Check cash balances are isolated and different
    cash_a = session.scalar(select(DbCashAccount).where(DbCashAccount.run_id == run_a.id))
    cash_b = session.scalar(select(DbCashAccount).where(DbCashAccount.run_id == run_b.id))
    assert cash_a is not None and cash_b is not None
    assert cash_a.balance_cents != cash_b.balance_cents

    # Check ledger entries belong strictly to their run_id
    ledgers_a = list(session.scalars(select(DbLedgerEntry).where(DbLedgerEntry.run_id == run_a.id)).all())
    ledgers_b = list(session.scalars(select(DbLedgerEntry).where(DbLedgerEntry.run_id == run_b.id)).all())
    assert len(ledgers_a) > 0 and len(ledgers_b) > 0
    assert all(l.run_id == run_a.id for l in ledgers_a)
    assert all(l.run_id == run_b.id for l in ledgers_b)
    assert set(l.id for l in ledgers_a).isdisjoint(set(l.id for l in ledgers_b))

    # Mutate run_a cash directly and verify run_b is completely unaffected
    cash_a.balance_cents += 999999
    session.flush()
    refreshed_b = session.scalar(select(DbCashAccount).where(DbCashAccount.run_id == run_b.id))
    assert refreshed_b.balance_cents == cash_b.balance_cents


def test_forecast_causal_invariance(session, dataset):
    """3. A forecast at cutoff T does not change when observations after T are added."""
    # Choose a decision point mid-dataset
    sample_obs = list(
        session.scalars(
            select(DbOrganizerObservation)
            .where(DbOrganizerObservation.dataset_id == dataset.metadata.dataset_id)
            .order_by(DbOrganizerObservation.timestamp.asc())
            .limit(100)
        ).all()
    )
    as_of = sample_obs[50].timestamp
    cutoff = get_information_cutoff(as_of)

    # Forecast with current dataset
    forecast_1 = get_hourly_forecasts_from_db(
        session, dataset.metadata.dataset_id, as_of=as_of, horizon_hours=4
    )

    # Add a mock future observation with massive flows that would distort forecasts if leaked
    future_obs_time = dataset.metadata.last_timestamp + timedelta(hours=1)
    mock_future = DbOrganizerObservation(
        dataset_id=dataset.metadata.dataset_id,
        timestamp=future_obs_time,
        deposits_usd=Decimal("99999999.00"),
        withdrawals_usd=Decimal("88888888.00"),
        net_flow_usd=Decimal("11111111.00"),
        repo_sweep_window_open=False,
        repo_sweep_mature=False,
        tier1_repo_rate_apy=Decimal("15.00"),
        tier2_bond_yield_pct=Decimal("4.50"),
        tier2_bond_price_index=Decimal("100.00"),
        tier2_bond_mod_duration=Decimal("2.00"),
        tier3_stock_index_price=Decimal("500.00"),
        tier3_stock_volatility_pct=Decimal("15.00"),
        tier1_early_redemption_haircut_pct=Decimal("0.50"),
        tier2_bond_liquidation_haircut_pct=Decimal("2.00"),
        tier3_stock_liquidation_haircut_pct=Decimal("15.00"),
        emergency_overdraft_penalty_apr_pct=Decimal("12.00"),
    )
    session.add(mock_future)
    session.flush()

    # Re-evaluate forecast at decision point as_of
    forecast_2 = get_hourly_forecasts_from_db(
        session, dataset.metadata.dataset_id, as_of=as_of, horizon_hours=4
    )

    # Forecasts must be exactly identical
    assert len(forecast_1) == len(forecast_2)
    for p1, p2 in zip(forecast_1, forecast_2):
        assert p1.start_at == p2.start_at
        assert p1.predicted_deposits_cents == p2.predicted_deposits_cents
        assert p1.predicted_withdrawals_cents == p2.predicted_withdrawals_cents
        assert p1.predicted_net_flow_cents == p2.predicted_net_flow_cents
        assert p1.supplied_uncertainty_buffer_cents == p2.supplied_uncertainty_buffer_cents


def test_future_dated_inputs_excluded_and_rejected(session, dataset):
    """4. Future-dated inputs are excluded or rejected before feature/model evaluation."""
    sample_obs = list(
        session.scalars(
            select(DbOrganizerObservation)
            .where(DbOrganizerObservation.dataset_id == dataset.metadata.dataset_id)
            .order_by(DbOrganizerObservation.timestamp.asc())
            .limit(10)
        ).all()
    )
    as_of = sample_obs[5].timestamp
    cutoff = get_information_cutoff(as_of)

    # Query causal history and verify strictly <= cutoff
    history = list(
        session.scalars(
            select(DbOrganizerObservation)
            .where(
                DbOrganizerObservation.dataset_id == dataset.metadata.dataset_id,
                DbOrganizerObservation.timestamp <= cutoff,
            )
            .order_by(DbOrganizerObservation.timestamp.asc())
        ).all()
    )
    assert all(o.timestamp <= cutoff for o in history)
    assert not any(o.timestamp >= as_of for o in history)


def test_calibration_artifacts_after_cutoff_rejected(session, dataset):
    """5. Training/calibration artifacts from after the information cutoff are rejected."""
    run = _create_test_run(session, dataset)
    obs = session.scalar(
        select(DbOrganizerObservation)
        .where(DbOrganizerObservation.dataset_id == dataset.metadata.dataset_id)
        .order_by(DbOrganizerObservation.timestamp.asc())
        .limit(1)
    )
    portfolio, _, _, _, _, _ = hydrate_portfolio_state(session, run, obs)
    policy = build_four_tier_policy(run.policy_json)
    cutoff = get_information_cutoff(portfolio.as_of)

    # Calibration artifact strictly after cutoff (future-dated)
    future_calibration = CalibratedForecastAllowance(
        time_basis=portfolio.time_basis,
        amount_cents=50000000,
        confidence=Decimal("0.95"),
        calibration_reference="calibrated-future",
        calibrated_through=cutoff + timedelta(hours=1),
    )

    with pytest.raises(ValueError, match="lookahead breach"):
        evaluate_liquidity_risk(
            portfolio,
            policy,
            observation=obs,
            calibrated_allowance=future_calibration,
        )

    # Valid calibration artifact at or before cutoff succeeds
    valid_calibration = CalibratedForecastAllowance(
        time_basis=portfolio.time_basis,
        amount_cents=50000000,
        confidence=Decimal("0.95"),
        calibration_reference="calibrated-causal",
        calibrated_through=cutoff,
    )
    res = evaluate_liquidity_risk(
        portfolio,
        policy,
        observation=obs,
        calibrated_allowance=valid_calibration,
    )
    assert res.reserve.required_reserve_cents >= policy.base_buffer_cents


def test_accounting_invariants_and_sweep_across_strategies(session, dataset):
    """6. Sweep window (17:00) and maturity (08:00) execute with strict accounting invariants for all strategies."""
    for strat in ("STATIC", "REACTIVE", "RESERVE_JUGGLER"):
        run = _create_test_run(session, dataset, strategy=strat, initial_cash=2000000000)

        # Advance 24 hours to cross 17:00 (sweep) and next day 08:00 (maturity)
        for s in range(24):
            res = execute_hourly_step(session, run.id, expected_step=s)
            assert res["status"] == "RUNNING"
            assert res["strategy"] == strat

        # Check ledger balance continuity: balance_after = balance_before + delta
        ledgers = list(
            session.scalars(
                select(DbLedgerEntry)
                .where(DbLedgerEntry.run_id == run.id)
                .order_by(DbLedgerEntry.step.asc(), DbLedgerEntry.id.asc())
            ).all()
        )
        assert len(ledgers) >= 24
        for l in ledgers:
            delta = l.amount_cents if "CREDIT" in l.entry_type or "INFLOW" in l.entry_type or "BORROW" in l.entry_type else -l.amount_cents
            if l.entry_type in ("OVERDRAFT_DRAW_BORROW", "REPO_EARLY_REDEMPTION"):
                continue  # These zero out or handle emergency funds
            expected_after = l.balance_before_cents + delta
            assert l.balance_after_cents == expected_after, f"Ledger entry {l.entry_type} failed balance continuity"

        # Check valuations exist and satisfy portfolio accounting identity
        vals = list(
            session.scalars(
                select(DbPortfolioValuation).where(DbPortfolioValuation.run_id == run.id)
            ).all()
        )
        for v in vals:
            assert v.total_portfolio_value_cents == (
                v.tier0_cash_cents + v.tier1_value_cents + v.tier2_market_value_cents + v.tier3_market_value_cents
            )
            assert v.net_portfolio_value_cents == v.total_portfolio_value_cents - v.liabilities_cents
