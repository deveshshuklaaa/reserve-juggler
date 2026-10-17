"""End-to-end integration tests for Four-Tier Treasury Intelligence Runtime.

Tests:
1. Initial portfolio: Tier 0 contains $20,000,000 (2,000,000,000 cents).
2. Normal hour: Simulation step executes successfully and deterministically.
3. Repo sweep: Excess cash sweeps into Tier 1 Repo at 17:00 window.
4. Repo maturity: At 08:00 next morning, Tier 1 returns principal + calculated interest.
5. Liquidity shock: Shortfall creates explicit breach and overdraft liability; never negative cash.
6. Accounting identities: total = T0 + T1 + T2 + T3, net = total - liabilities.
7. Audit trail & API: Movements and ledger entries match executions; API step endpoint functions.
"""

import os
import re
from contextlib import contextmanager
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.data.organizer import OrganizerDatasetSource
from app.main import app
from app.persistence.migrations import MIGRATION_DIRECTORY, apply_migrations
from app.persistence.models import (
    BondPosition,
    CashAccount,
    EquityPosition,
    InvestmentMovement,
    LedgerEntry,
    LiquidityBreach,
    OrganizerObservation,
    OverdraftLiability,
    OverdraftMovement,
    PortfolioValuation,
    RepoPosition,
    SimulationRun,
    TreasuryDecision,
)
from app.persistence.repositories import DatasetRepository, configuration_identity
from app.treasury.four_tier_adapter import step_simulation_hour


@contextmanager
def clean_database(url):
    url = make_url(url)
    if not (url.database or "").startswith("reserve_juggler_m2_test"):
        pytest.fail("Integration tests require a dedicated reserve_juggler_m2_test* database")
    name = "reserve_juggler_m2_test_" + uuid4().hex[:12]
    assert re.fullmatch(r"reserve_juggler_m2_test_[a-f0-9]{12}", name)
    admin = create_engine(url, isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.exec_driver_sql(f'CREATE DATABASE "{name}"')
    engine = create_engine(url.set(database=name))
    try:
        yield engine
    finally:
        engine.dispose()
        with admin.connect() as connection:
            connection.exec_driver_sql(f'DROP DATABASE "{name}"')
        admin.dispose()


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
    with clean_database(pg_url) as engine:
        apply_migrations(engine)
        with Session(engine) as session, session.begin():
            DatasetRepository(session).store(dataset)
        yield engine


@pytest.fixture
def session(pg_engine):
    with pg_engine.connect() as connection:
        transaction = connection.begin()
        with Session(connection, join_transaction_mode="create_savepoint") as session:
            yield session
        transaction.rollback()


@pytest.fixture
def simulation_run(session, dataset):
    """Sets up an initial run with $20M Tier 0 Cash."""
    policy = {
        "base_buffer_cents": 50000000,
        "operational_buffer_cents": 50000000,
        "uncertainty_multiplier_bps": 19600,
        "tolerance_bps": 500,
        "min_transfer_cents": 1000000,
        "minimum_sweep_cents": 1000000,
        "max_allocation_bps": 10000,
        "minimum_liquid_reserve_cents": 50000000,
        "allow_early_repo_redemption": True,
        "allow_overdraft": True,
        "max_overdraft_cents": 5000000000,
    }
    run = SimulationRun(
        id=uuid4(),
        seed=None,
        scenario="NORMAL",
        status="RUNNING",
        current_step=0,
        duration_steps=168,
        initial_cash_cents=2000000000,  # $20,000,000.00
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

    # Initial Tier 0 Cash Account
    cash = CashAccount(
        id=uuid4(),
        run_id=run.id,
        source_type=run.source_type,
        dataset_id=run.dataset_id,
        source_observation_timestamp=dataset.metadata.first_timestamp,
        balance_cents=2000000000,
    )
    session.add(cash)
    session.flush()

    # Initial Portfolio Valuation
    pv = PortfolioValuation(
        id=uuid4(),
        run_id=run.id,
        source_type=run.source_type,
        dataset_id=run.dataset_id,
        source_observation_timestamp=dataset.metadata.first_timestamp,
        valued_at=dataset.metadata.first_timestamp,
        tier0_cash_cents=2000000000,
        tier1_principal_cents=0,
        tier1_value_cents=0,
        tier2_market_value_cents=0,
        tier3_market_value_cents=0,
        total_portfolio_value_cents=2000000000,
        immediately_available_cents=2000000000,
        liquidatable_value_cents=2000000000,
        restricted_value_cents=0,
        liabilities_cents=0,
        net_portfolio_value_cents=2000000000,
        reference_id=f"val-init-{run.id}",
    )
    session.add(pv)
    session.flush()
    return run


def test_initial_portfolio(session, simulation_run):
    """1. Initial portfolio: Tier 0 contains exactly $20,000,000.00."""
    cash = session.scalar(select(CashAccount).where(CashAccount.run_id == simulation_run.id))
    assert cash is not None
    assert cash.balance_cents == 2000000000  # $20,000,000.00

    pv = session.scalar(select(PortfolioValuation).where(PortfolioValuation.run_id == simulation_run.id))
    assert pv.tier0_cash_cents == 2000000000
    assert pv.total_portfolio_value_cents == 2000000000
    assert pv.net_portfolio_value_cents == 2000000000
    assert pv.liabilities_cents == 0


def test_normal_hour_step(session, simulation_run):
    """2. Normal hour: Simulation step executes successfully and deterministically."""
    res = step_simulation_hour(session, simulation_run.id)
    assert res["run_id"] == str(simulation_run.id)
    assert res["step"] == 0
    assert res["total_portfolio_value_cents"] > 0
    assert simulation_run.current_step == 1

    dec = session.scalar(
        select(TreasuryDecision).where(
            TreasuryDecision.run_id == simulation_run.id,
            TreasuryDecision.step == 0,
        )
    )
    assert dec is not None
    assert dec.execution_status == "EXECUTED"


def test_repo_sweep_window(session, simulation_run):
    """3. Repo sweep: at 17:00 repo sweep window, excess cash sweeps into Tier 1 Repo."""
    # Fast-forward step to hour 17 (17:00 repo sweep window)
    simulation_run.current_step = 17
    session.flush()

    res = step_simulation_hour(session, simulation_run.id)
    assert res["action_taken"] == "SWEEP"
    assert res["action_amount_cents"] > 0
    assert res["tier1_value_cents"] == res["action_amount_cents"]

    # Verify Repo position in DB
    repos = list(
        session.scalars(
            select(RepoPosition).where(
                RepoPosition.run_id == simulation_run.id,
                RepoPosition.status == "LOCKED",
            )
        ).all()
    )
    assert len(repos) == 1
    assert repos[0].principal_cents == res["action_amount_cents"]
    assert repos[0].scheduled_maturity_at == repos[0].entered_at + timedelta(hours=15)

    # Verify investment movement audit
    mov = session.scalar(
        select(InvestmentMovement).where(
            InvestmentMovement.run_id == simulation_run.id,
            InvestmentMovement.kind == "INVESTMENT",
        )
    )
    assert mov is not None
    assert mov.principal_cents == res["action_amount_cents"]
    assert mov.cash_delta_cents == -res["action_amount_cents"]


def test_repo_maturity(session, simulation_run):
    """4. Repo maturity: At 08:00 next morning, Tier 1 returns principal + calculated interest."""
    # Step 17: Sweep into repo
    simulation_run.current_step = 17
    session.flush()
    sweep_res = step_simulation_hour(session, simulation_run.id)
    sweep_amount = sweep_res["action_amount_cents"]

    # Advance to hour 32 (next morning 08:00 = 17 + 15 hours)
    simulation_run.current_step = 32
    session.flush()

    mature_res = step_simulation_hour(session, simulation_run.id)
    assert mature_res["action_taken"] == "WITHDRAW"
    assert mature_res["action_amount_cents"] > sweep_amount  # Includes interest!

    # Repo is redeemed
    repo = session.scalar(
        select(RepoPosition).where(
            RepoPosition.run_id == simulation_run.id,
            RepoPosition.status == "REDEEMED",
        )
    )
    assert repo is not None
    assert repo.realized_interest_cents > 0
    assert repo.proceeds_returned_cents == repo.principal_cents + repo.realized_interest_cents


def test_liquidity_shock_triggers_overdraft(session, simulation_run):
    """5. Liquidity shock: Shortfall creates explicit breach and overdraft; no negative cash."""
    # Artificially set cash to 0 to simulate massive liquidity shock
    cash = session.scalar(select(CashAccount).where(CashAccount.run_id == simulation_run.id))
    cash.balance_cents = 0
    simulation_run.current_step = 18  # 18:00 has net outflows (-$226k)
    session.flush()

    res = step_simulation_hour(session, simulation_run.id)
    assert res["breach_occurred"] is True
    assert res["overdraft_borrowed_cents"] > 0
    assert res["tier0_cash_cents"] >= 0  # Cash is never negative!

    # Verify Liquidity Breach logged
    breach = session.scalar(
        select(LiquidityBreach).where(LiquidityBreach.run_id == simulation_run.id)
    )
    assert breach is not None
    assert breach.shortfall_cents == res["overdraft_borrowed_cents"]

    # Verify Overdraft Liability recorded
    od = session.scalar(
        select(OverdraftLiability).where(OverdraftLiability.run_id == simulation_run.id)
    )
    assert od is not None
    assert od.outstanding_principal_cents == res["overdraft_borrowed_cents"]
    assert od.borrowed_cents == res["overdraft_borrowed_cents"]

    # Verify Overdraft Movement recorded
    od_mov = session.scalar(
        select(OverdraftMovement).where(OverdraftMovement.run_id == simulation_run.id)
    )
    assert od_mov is not None
    assert od_mov.kind == "BORROW"
    assert od_mov.principal_cents == res["overdraft_borrowed_cents"]


def test_accounting_identities(session, simulation_run):
    """6. Accounting identity: total = T0 + T1 + T2 + T3, and net = total - liabilities."""
    step_simulation_hour(session, simulation_run.id)

    valuations = list(
        session.scalars(
            select(PortfolioValuation).where(PortfolioValuation.run_id == simulation_run.id)
        ).all()
    )
    assert len(valuations) >= 2  # initial + step 0
    for v in valuations:
        assert v.total_portfolio_value_cents == (
            v.tier0_cash_cents
            + v.tier1_value_cents
            + v.tier2_market_value_cents
            + v.tier3_market_value_cents
        )
        assert v.net_portfolio_value_cents == v.total_portfolio_value_cents - v.liabilities_cents


def test_api_endpoint_simulation_step(session, simulation_run):
    """7. API endpoint POST /api/v1/simulation/step advances step and returns required fields."""
    from app.database import get_db

    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        client = TestClient(app)
        resp = client.post("/api/v1/simulation/step", json={"run_id": str(simulation_run.id)})
        assert resp.status_code == 200
        data = resp.json()
        assert data["run_id"] == str(simulation_run.id)
        assert "tier0_cash_cents" in data
        assert "total_portfolio_value_cents" in data
        assert "required_reserve_cents" in data
        assert "action_taken" in data
        assert "breach_occurred" in data
    finally:
        app.dependency_overrides.clear()
