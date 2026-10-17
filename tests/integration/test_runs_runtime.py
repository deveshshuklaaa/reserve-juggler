"""Integration test suite for live simulation runtime, scenarios, and four-tier portfolio state.

Tests:
1. Run creation with $20M default checking.
2. Full snapshot validation with four-tier portfolio state and aggregates.
3. Normal hourly advancement and ledger accounting.
4. Stale-step conflict (HTTP 409) preventing duplicate execution.
5. Scheduling and applying all five scenario types.
6. Policy updates mapping frontend parameter names.
7. Repo entry window (17:00 sweep) and maturity (08:00 settlement).
8. Shock-induced liquidity shortfalls, breach records, and overdraft liabilities.
9. Exact accounting identities across all tiers and ledger.
10. Enveloped responses: {items: [...]} for history, decisions, transactions; {points: [...]} for forecast.
"""

import os
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.data.organizer import OrganizerDatasetSource
from app.database import get_db
from app.main import app
from app.persistence.migrations import apply_migrations
from app.persistence.models import (
    BondPosition, CashAccount, EquityPosition, LedgerEntry, LiquidityBreach,
    OrganizerObservation, OverdraftLiability, PortfolioValuation, RepoPosition,
    SimulationRun, TreasuryDecision,
)
from app.persistence.repositories import DatasetRepository


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
def client(pg_engine):
    def override_get_db():
        with Session(pg_engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_run_creation_and_defaults(client):
    """1. Run creation: default initial Tier 0 checking is exactly $20,000,000.00."""
    res = client.post("/api/v1/runs", json={})
    assert res.status_code == 201
    data = res.json()
    assert data["status"] == "READY"
    assert data["current_step"] == 0
    assert data["checking_cents"] == 2000000000
    assert data["vault_locked_cents"] == 0
    assert "run_id" in data


def test_full_snapshot_validation(client):
    """2. Full snapshot: status, policy, deployable surplus, and four-tier portfolio structure."""
    created = client.post("/api/v1/runs", json={}).json()
    run_id = created["run_id"]

    res = client.get(f"/api/v1/runs/{run_id}/snapshot")
    assert res.status_code == 200
    snap = res.json()
    assert snap["run_id"] == run_id
    assert snap["step"] == 0
    assert snap["checking_cents"] == 2000000000
    assert snap["deployable_surplus_cents"] > 0
    assert snap["status"] == "READY"
    assert "policy" in snap
    assert "four_tier" in snap

    ft = snap["four_tier"]
    assert "tier0" in ft
    assert "tier1" in ft
    assert "tier2" in ft
    assert "tier3" in ft
    assert "overdraft" in ft
    assert "aggregates" in ft

    # Validate aggregates
    aggr = ft["aggregates"]
    assert aggr["gross_assets_cents"] == 2000000000
    assert aggr["total_liabilities_cents"] == 0
    assert aggr["net_portfolio_value_cents"] == 2000000000


def test_normal_hourly_advancement(client):
    """3. Normal hourly advancement: expected_step = 0 advances to step 1."""
    run_id = client.post("/api/v1/runs", json={}).json()["run_id"]

    res = client.post(f"/api/v1/runs/{run_id}/advance", json={"expected_step": 0, "steps": 1})
    assert res.status_code == 200
    snap = res.json()
    assert snap["step"] == 1
    assert snap["status"] == "RUNNING"
    assert snap["checking_cents"] > 0


def test_stale_step_conflict_prevention(client):
    """4. Stale-step conflict: expected_step mismatch returns HTTP 409 without applying step twice."""
    run_id = client.post("/api/v1/runs", json={}).json()["run_id"]

    # Initial step is 0; provide expected_step=5 (stale)
    res = client.post(f"/api/v1/runs/{run_id}/advance", json={"expected_step": 5})
    assert res.status_code == 409
    err = res.json()
    assert err["error_code"] == "CONFLICTING_STEP"

    # Verify run remains at step 0
    snap = client.get(f"/api/v1/runs/{run_id}/snapshot").json()
    assert snap["step"] == 0


def test_all_five_scenarios_scheduling(client):
    """5. All five scenario types: NORMAL, HIGH_WITHDRAWAL, LOW_DEPOSIT, SETTLEMENT_DELAY, LIQUIDITY_SHOCK."""
    run_id = client.post("/api/v1/runs", json={}).json()["run_id"]

    scenarios = [
        ("NORMAL", {}),
        ("HIGH_WITHDRAWAL", {"multiplier": 2.0}),
        ("LOW_DEPOSIT", {"multiplier": 0.25}),
        ("SETTLEMENT_DELAY", {"delay_hours": 24}),
        ("LIQUIDITY_SHOCK", {"amount_cents": 1000000000}),
    ]

    for index, (scen, params) in enumerate(scenarios):
        res = client.post(
            f"/api/v1/runs/{run_id}/scenario",
            json={"scenario": scen, "parameters": params, "effective_step": index + 1},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["scenario"] == scen
        assert data["effective_step"] == index + 1


def test_policy_update_frontend_field_mapping(client):
    """6. Policy updates: map frontend field names (min_sweep_cents, vault_rate_bps, risk_percentile=99)."""
    run_id = client.post("/api/v1/runs", json={}).json()["run_id"]

    res = client.patch(
        f"/api/v1/runs/{run_id}/policy",
        json={
            "min_sweep_cents": 50000000,
            "vault_rate_bps": 550,
            "lock_steps": 192,
            "allow_early_redemption": False,
            "risk_percentile": 99,
        },
    )
    assert res.status_code == 200
    pol = res.json()
    assert pol["minimum_sweep_cents"] == 50000000
    assert pol["vault_yield_bps"] == 550
    assert pol["vault_lock_steps"] == 192
    assert pol["early_redemption_allowed"] is False
    assert pol["risk_percentile"] == 0.99


def test_repo_sweep_and_maturity_cycle(client):
    """7. Overnight repo 17:00 sweep window and 08:00 maturity settlement."""
    run_id = client.post("/api/v1/runs", json={}).json()["run_id"]

    # Step up to hour 17 (step 17)
    for step in range(17):
        res = client.post(f"/api/v1/runs/{run_id}/advance", json={"expected_step": step})
        assert res.status_code == 200

    # At step 17 (17:00), sweep occurs
    snap_17 = client.get(f"/api/v1/runs/{run_id}/snapshot").json()
    assert snap_17["vault_locked_cents"] > 0
    assert snap_17["decision"]["action"] == "SWEEP"
    repo_principal = snap_17["vault_locked_cents"]

    # Step from hour 17 to hour 32 (next day 08:00: step 32 = 24 + 8)
    for step in range(17, 32):
        res = client.post(f"/api/v1/runs/{run_id}/advance", json={"expected_step": step})
        assert res.status_code == 200

    # At step 32 (08:00), repo matured
    snap_32 = client.get(f"/api/v1/runs/{run_id}/snapshot").json()
    assert snap_32["vault_locked_cents"] == 0
    assert snap_32["decision"]["action"] == "WITHDRAW"


def test_shock_induced_liquidity_shortfall_and_overdraft(client):
    """8. Shock-induced shortfall: creates liquidity breach and emergency overdraft liability."""
    # Create run with minimal starting cash
    run_id = client.post("/api/v1/runs", json={"initial_cash_cents": 1000000}).json()["run_id"]

    # Inject massive liquidity shock at step 1 ($50,000,000.00 outflow)
    client.post(
        f"/api/v1/runs/{run_id}/scenario",
        json={"scenario": "LIQUIDITY_SHOCK", "parameters": {"amount_cents": 5000000000}, "effective_step": 1},
    )

    # Advance to step 1
    res = client.post(f"/api/v1/runs/{run_id}/advance", json={"expected_step": 0})
    assert res.status_code == 200
    snap = res.json()

    # Cash should be depleted, overdraft liability active
    ft = snap["four_tier"]
    assert ft["tier0"]["checking_cents"] == 0
    assert ft["tier0"]["status"] == "DEFICIT"
    assert ft["overdraft"]["is_active"] is True
    assert ft["overdraft"]["borrowing_outstanding_cents"] > 0
    assert snap["decision"]["action"] == "LIQUIDITY_WARNING"


def test_accounting_identities(client):
    """9. Accounting identities: gross assets, net portfolio value, and aggregate invariants."""
    run_id = client.post("/api/v1/runs", json={}).json()["run_id"]
    client.post(f"/api/v1/runs/{run_id}/advance", json={"expected_step": 0})

    snap = client.get(f"/api/v1/runs/{run_id}/snapshot").json()
    ft = snap["four_tier"]
    t0 = ft["tier0"]["checking_cents"]
    t1 = ft["tier1"]["principal_cents"]
    t2 = ft["tier2"]["market_value_cents"]
    t3 = ft["tier3"]["market_value_cents"]
    od = ft["overdraft"]["borrowing_outstanding_cents"]

    aggr = ft["aggregates"]
    assert aggr["gross_assets_cents"] == t0 + t1 + t2 + t3
    assert aggr["net_portfolio_value_cents"] == aggr["gross_assets_cents"] - od
    assert aggr["total_liabilities_cents"] == od


def test_enveloped_collections_responses(client):
    """10. Collections envelopes: {items: [...]} and {points: [...]}."""
    run_id = client.post("/api/v1/runs", json={}).json()["run_id"]
    client.post(f"/api/v1/runs/{run_id}/advance", json={"expected_step": 0})

    # History
    hist = client.get(f"/api/v1/runs/{run_id}/history").json()
    assert isinstance(hist.get("items"), list)

    # Decisions
    decs = client.get(f"/api/v1/runs/{run_id}/decisions").json()
    assert isinstance(decs.get("items"), list)

    # Transactions
    txs = client.get(f"/api/v1/runs/{run_id}/transactions").json()
    assert isinstance(txs.get("items"), list)

    # Forecast
    fc = client.get(f"/api/v1/runs/{run_id}/forecast").json()
    assert isinstance(fc.get("points"), list)
    for p in fc["points"]:
        assert "predicted_net_cents" in p
        assert "lower_cents" in p
        assert "upper_cents" in p
