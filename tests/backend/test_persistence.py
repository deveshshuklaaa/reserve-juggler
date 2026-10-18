"""Real PostgreSQL contracts; stored financial values below are explicit fixtures.

No fixture executes a strategy or calculates a trade, valuation, or interest.
PERSISTENCE_TEST_DATABASE_URL must identify a disposable test server database.
"""

import csv
import os
import re
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Session

from app.data.organizer import NUMERIC_COLUMNS, OrganizerDatasetSource
from app.persistence.migrations import MIGRATION_DIRECTORY, apply_migrations
from app.persistence.models import (
    Base, SCHEMA, BondPosition, CashAccount, DatasetSource, EquityPosition,
    InvestmentMovement, LedgerEntry, LiquidityBreach, OrganizerObservation,
    OverdraftLiability, OverdraftMovement, PortfolioValuation, PositionValuation,
    RepoPosition, SimulationRun, TreasuryDecision,
)
from app.persistence.repositories import (
    DatasetRepository, RunRepository, RunScopedRepository, configuration_identity,
)


@contextmanager
def clean_database(url):
    url = make_url(url)
    if not (url.database or "").startswith("reserve_juggler_m2_test"):
        pytest.fail("Persistence tests require a dedicated reserve_juggler_m2_test* database")
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
    return OrganizerDatasetSource(Path(__file__).resolve().parents[2] / "treasury_4tier_dataset.csv").load()


@pytest.fixture(scope="module")
def pg_engine(pg_url, dataset):
    with clean_database(pg_url) as engine:
        assert SCHEMA not in inspect(engine).get_schema_names()
        assert apply_migrations(engine) == tuple(p.name for p in sorted(MIGRATION_DIRECTORY.glob("*.sql")))
        assert apply_migrations(engine) == ()
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


def historical_run(dataset, **overrides):
    policy = {"label": "persistence fixture"}
    values = dict(id=uuid4(), seed=None, scenario="NORMAL", status="READY", current_step=0,
                  duration_steps=24, initial_cash_cents=2000000000, policy_json=policy,
                  source_type="ORGANIZER_HISTORICAL", dataset_id=dataset.metadata.dataset_id,
                  source_start_timestamp=dataset.metadata.first_timestamp,
                  source_end_timestamp=dataset.metadata.last_timestamp, native_interval_seconds=3600,
                  source_timezone_status="UNSPECIFIED", configuration_hash=configuration_identity(policy))
    return SimulationRun(**dict(values, **overrides))


@pytest.fixture
def runs(session, dataset):
    repository = RunRepository(session)
    return repository.add(historical_run(dataset)), repository.add(historical_run(dataset))


def linked(run, timestamp=datetime(2026, 1, 1)):
    return dict(run_id=run.id, source_type=run.source_type, dataset_id=run.dataset_id,
                source_observation_timestamp=timestamp)


def bond(run):
    return BondPosition(**linked(run), quantity=Decimal("2.333333333333333333333333333"),
                        acquisition_price_index=Decimal("100.000"), acquired_at=datetime(2026, 1, 1),
                        current_market_price_index=Decimal("99.958"), current_market_value_cents=23000,
                        supplied_yield_pct=Decimal("4.822"), modified_duration=Decimal("1.92"),
                        realized_pnl_cents=-100, unrealized_pnl_cents=-50,
                        liquidation_haircut_pct=Decimal("2.0"), liquidation_cost_cents=460,
                        liquidation_proceeds_cents=22540, market_observation_timestamp=datetime(2026, 1, 1, 1),
                        status="OPEN")


def ledger(run, reference="fixture-ledger"):
    return LedgerEntry(**linked(run), event_at=datetime(2026, 1, 1), timestamp=None, step=0,
                       entry_type="FIXTURE", amount_cents=100, balance_before_cents=1000,
                       balance_after_cents=1100, reference_id=reference)


def test_migration_schema_and_model_columns(pg_engine):
    database = inspect(pg_engine)
    for table in Base.metadata.tables.values():
        assert database.has_table(table.name, schema=SCHEMA)
        actual = {column["name"]: column for column in database.get_columns(table.name, schema=SCHEMA)}
        assert set(actual) == set(table.columns.keys())
        for column in table.columns:
            assert actual[column.name]["nullable"] == column.nullable
    numeric = {c["name"]: c for c in database.get_columns("organizer_observations", schema=SCHEMA)}
    for name in NUMERIC_COLUMNS:
        assert numeric[name]["type"].precision is None
        assert numeric[name]["type"].scale is None
    assert not numeric["timestamp"]["type"].timezone
    assert database.get_foreign_keys("investment_movements", schema=SCHEMA)
    assert database.get_indexes("bond_positions", schema=SCHEMA)


def test_all_organizer_rows_round_trip_exactly(session, dataset):
    repository = DatasetRepository(session)
    assert repository.metadata(dataset.metadata.dataset_id) == dataset.metadata
    restored = repository.observations(dataset.metadata.dataset_id)
    assert len(restored) == 8760
    for before, after in zip(dataset, restored):
        assert before.timestamp == after.timestamp and after.timestamp.tzinfo is None
        for field in NUMERIC_COLUMNS:
            assert getattr(before, field).as_tuple() == getattr(after, field).as_tuple()
        assert before.repo_sweep_window_open == after.repo_sweep_window_open
        assert before.repo_sweep_mature == after.repo_sweep_mature
    assert restored[14].net_flow_usd == Decimal("165091.77")
    assert restored[14].derived_net_flow_usd == Decimal("165091.78")
    assert len(repository.observations(dataset.metadata.dataset_id, through=restored[2].timestamp)) == 3
    repository.store(dataset)
    assert len(repository.observations(dataset.metadata.dataset_id)) == 8760


def test_source_precision_beyond_fixed_numeric_scale(session, tmp_path):
    source = Path(__file__).resolve().parents[2] / "treasury_4tier_dataset.csv"
    with source.open(newline="", encoding="utf-8") as stream:
        row = next(csv.DictReader(stream))
    row["tier1_repo_rate_apy"] = "4.29200000000000000000000000000000000001"
    row["tier2_bond_price_index"] = "100.000000000000000000000000000000000000001"
    path = tmp_path / "precision.csv"
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=row.keys())
        writer.writeheader()
        writer.writerow(row)
    fixture = OrganizerDatasetSource(path, expected_row_count=1).load()
    repository = DatasetRepository(session)
    repository.store(fixture)
    restored = repository.observations(fixture.metadata.dataset_id)[0]
    assert restored.tier1_repo_rate_apy.as_tuple() == Decimal(row["tier1_repo_rate_apy"]).as_tuple()
    assert restored.tier2_bond_price_index.as_tuple() == Decimal(row["tier2_bond_price_index"]).as_tuple()


def test_run_source_and_configuration_contract(session, runs, dataset):
    run, _ = runs
    session.expire_all()
    restored = RunRepository(session).get(run.id)
    assert restored.dataset_id == dataset.metadata.dataset_id
    assert restored.native_interval_seconds == 3600
    assert restored.started_at is restored.current_time is restored.seed is None
    assert restored.source_start_timestamp.tzinfo is None
    assert configuration_identity({"b": 2, "a": 1}) == configuration_identity({"a": 1, "b": 2})
    with pytest.raises(ValueError):
        RunRepository(session).add(historical_run(dataset, configuration_hash="0" * 64))
    synthetic = historical_run(dataset, source_type="SYNTHETIC", dataset_id=None,
                               source_start_timestamp=None, source_end_timestamp=None,
                               source_timezone_status="UTC", native_interval_seconds=900, seed=42,
                               started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                               current_time=datetime(2026, 1, 1, tzinfo=timezone.utc))
    RunRepository(session).add(synthetic)
    assert synthetic.dataset_id is None


def test_run_isolation_and_bond_values(session, runs):
    run_a, run_b = runs
    repository = RunScopedRepository(session, BondPosition)
    record = repository.add(bond(run_a))
    assert repository.get(run_b.id, record.id) is None
    assert repository.list_for_run(run_b.id) == ()
    session.expire_all()
    restored = repository.get(run_a.id, record.id)
    assert restored.acquisition_price_index == Decimal("100.000")
    assert restored.current_market_price_index == Decimal("99.958")
    assert restored.current_market_value_cents == 23000
    assert restored.realized_pnl_cents == -100
    assert restored.unrealized_pnl_cents == -50


def test_four_tiers_are_distinct_and_repo_schedule_is_explicit(session, runs):
    run, _ = runs
    cash = RunScopedRepository(session, CashAccount).add(CashAccount(**linked(run), balance_cents=10000))
    repo = RepoPosition(**linked(run, datetime(2026, 1, 1, 17)), principal_cents=100000,
                        entered_at=datetime(2026, 1, 1, 17), scheduled_maturity_at=datetime(2026, 1, 2, 8),
                        applicable_apy_pct=Decimal("4.308"), status="LOCKED",
                        early_redemption_haircut_pct=Decimal("0.5"), accrued_interest_cents=None,
                        realized_interest_cents=None)
    RunScopedRepository(session, RepoPosition).add(repo)
    bond_record = RunScopedRepository(session, BondPosition).add(bond(run))
    equity = EquityPosition(**linked(run), quantity=Decimal("1.123456789"),
                            acquisition_price_index=Decimal("4988.59"), acquired_at=datetime(2026, 1, 1),
                            current_market_price_index=Decimal("4997.45"), current_market_value_cents=561000,
                            supplied_volatility_pct=Decimal("18.0"), realized_pnl_cents=-50,
                            unrealized_pnl_cents=100, liquidation_haircut_pct=Decimal("15.0"),
                            liquidation_cost_cents=100, liquidation_proceeds_cents=560900,
                            market_observation_timestamp=datetime(2026, 1, 1, 1), status="OPEN")
    RunScopedRepository(session, EquityPosition).add(equity)
    session.expire_all()
    assert repo.scheduled_maturity_at - repo.entered_at == timedelta(hours=15)
    assert equity.acquisition_price_index != equity.current_market_price_index
    assert not hasattr(equity, "guaranteed_interest_cents")
    assert len({type(cash), type(repo), type(bond_record), type(equity)}) == 4


def test_investment_audit_and_duplicate_reference(session, runs):
    run, _ = runs
    position = RunScopedRepository(session, BondPosition).add(bond(run))
    entry = RunScopedRepository(session, LedgerEntry).add(ledger(run))
    values = dict(**linked(run), tier=2, bond_position_id=position.id, kind="LIQUIDATION",
                  occurred_at=datetime(2026, 1, 1), cash_delta_cents=100,
                  haircut_cost_cents=2, ledger_entry_id=entry.id, reference_id="liquidation-fixture")
    repository = RunScopedRepository(session, InvestmentMovement)
    record = repository.add(InvestmentMovement(**values))
    assert record.run_id == entry.run_id == position.run_id
    assert record.dataset_id == position.dataset_id
    with pytest.raises(IntegrityError), session.begin_nested():
        repository.add(InvestmentMovement(**values))
    assert len(repository.list_for_run(run.id)) == 1
    valuation = PositionValuation(**linked(run), tier=2, bond_position_id=position.id,
                                 valued_at=datetime(2026, 1, 1), market_price_index=Decimal("99.958"),
                                 market_value_cents=23000, unrealized_pnl_cents=-50, reference_id="mark-fixture")
    RunScopedRepository(session, PositionValuation).add(valuation)


def test_cross_run_position_and_ledger_references_are_rejected(session, runs):
    run_a, run_b = runs
    foreign_position = RunScopedRepository(session, BondPosition).add(bond(run_b))
    foreign_ledger = RunScopedRepository(session, LedgerEntry).add(ledger(run_b))
    own_position = RunScopedRepository(session, BondPosition).add(bond(run_a))
    repository = RunScopedRepository(session, InvestmentMovement)
    for position_id, ledger_id in ((foreign_position.id, None), (own_position.id, foreign_ledger.id)):
        with pytest.raises(IntegrityError), session.begin_nested():
            repository.add(InvestmentMovement(**linked(run_a), tier=2, bond_position_id=position_id,
                                              kind="VALUATION", occurred_at=datetime(2026, 1, 1),
                                              cash_delta_cents=0, ledger_entry_id=ledger_id,
                                              reference_id=str(uuid4())))


def test_liability_repayment_cost_and_portfolio_values(session, runs):
    run, _ = runs
    breach = RunScopedRepository(session, LiquidityBreach).add(LiquidityBreach(
        **linked(run), occurred_at=datetime(2026, 1, 1), shortfall_cents=10000,
        description="Explicit persistence fixture", reference_id="breach-fixture"))
    loan = RunScopedRepository(session, OverdraftLiability).add(OverdraftLiability(
        **linked(run), borrowed_at=datetime(2026, 1, 1), borrowed_cents=10000,
        outstanding_principal_cents=8000, repaid_principal_cents=2000,
        apr_pct=Decimal("12.0"), financing_cost_cents=20, breach_id=breach.id, reference_id="loan-fixture"))
    repayment_entry = ledger(run, "repayment-ledger")
    repayment_entry.amount_cents = 2000
    repayment_entry.balance_before_cents = 3000
    repayment_entry.balance_after_cents = 1000
    entry = RunScopedRepository(session, LedgerEntry).add(repayment_entry)
    RunScopedRepository(session, OverdraftMovement).add(OverdraftMovement(
        **linked(run), liability_id=loan.id, occurred_at=datetime(2026, 1, 1), kind="REPAYMENT",
        principal_cents=2000, financing_cost_cents=0, cash_delta_cents=-2000,
        ledger_entry_id=entry.id, reference_id="repayment-fixture"))
    valuation = RunScopedRepository(session, PortfolioValuation).add(PortfolioValuation(
        **linked(run), valued_at=datetime(2026, 1, 1), tier0_cash_cents=1000,
        tier1_principal_cents=2000, tier1_value_cents=2000, tier2_market_value_cents=3000,
        tier3_market_value_cents=4000, total_portfolio_value_cents=10000,
        immediately_available_cents=1000, liquidatable_value_cents=5000, restricted_value_cents=2000,
        liabilities_cents=8000, net_portfolio_value_cents=2000, reference_id="portfolio-fixture"))
    assert valuation.total_portfolio_value_cents != valuation.immediately_available_cents
    assert valuation.net_portfolio_value_cents == 2000
    assert loan.outstanding_principal_cents == 8000 and loan.financing_cost_cents == 20
    assert not isinstance(loan, CashAccount)


def test_multi_tier_decision_persistence(session, runs):
    run, _ = runs
    decision = TreasuryDecision(**linked(run), timestamp=None, step=0, action="ALLOCATE", amount_cents=0,
                                execution_status="PENDING", explanation_json=["fixture only"], decision_details_json={},
                                tier0_target_cents=100, tier1_allocation_cents=200,
                                tier2_allocation_cents=300, tier3_allocation_cents=400,
                                required_reserve_cents=100, available_liquidity_cents=100,
                                expected_inflow_cents=500, expected_outflow_cents=400, uncertainty_cents=20)
    RunScopedRepository(session, TreasuryDecision).add(decision)
    session.expire_all()
    assert decision.tier2_allocation_cents == 300
    assert decision.execution_status == "PENDING"


@pytest.mark.parametrize("change", ["missing_observation", "negative_money", "wrong_tier", "missing_audit", "nonfinite_sql"])
def test_database_constraints(session, runs, change):
    run, _ = runs
    with pytest.raises(IntegrityError), session.begin_nested():
        if change == "missing_observation":
            session.add(CashAccount(**linked(run, datetime(2030, 1, 1)), balance_cents=1))
        elif change == "negative_money":
            session.add(CashAccount(**linked(run), balance_cents=-1))
        elif change in ("wrong_tier", "missing_audit"):
            position = RunScopedRepository(session, BondPosition).add(bond(run))
            session.add(InvestmentMovement(**linked(run), tier=1 if change == "wrong_tier" else 2,
                                          bond_position_id=position.id, kind="INVESTMENT", occurred_at=datetime(2026, 1, 1),
                                          cash_delta_cents=-100, reference_id="invalid-fixture"))
        else:
            session.execute(text(f"UPDATE {SCHEMA}.organizer_observations SET tier1_repo_rate_apy='NaN'::numeric WHERE timestamp='2026-01-01 00:00:00'"))
        session.flush()


@pytest.mark.parametrize("field,value", [("quantity", 1.5), ("acquisition_price_index", Decimal("NaN")),
                                         ("current_market_value_cents", 23000.5), ("acquired_at", datetime(2026, 1, 1, tzinfo=timezone.utc))])
def test_bind_types_reject_precision_or_timezone_loss(session, runs, field, value):
    position = bond(runs[0])
    setattr(position, field, value)
    with pytest.raises(StatementError), session.begin_nested():
        RunScopedRepository(session, BondPosition).add(position)


def test_repository_does_not_commit_partial_state(session, runs):
    run = runs[0]
    with pytest.raises(RuntimeError), session.begin_nested():
        RunScopedRepository(session, CashAccount).add(CashAccount(**linked(run), balance_cents=123))
        raise RuntimeError("caller aborts the financial transaction")
    assert RunScopedRepository(session, CashAccount).list_for_run(run.id) == ()


def test_upgrade_preserves_existing_002_rows(pg_url, tmp_path):
    with clean_database(pg_url) as engine:
        for path in sorted(MIGRATION_DIRECTORY.glob("00[12]_*.sql")):
            (tmp_path / path.name).write_bytes(path.read_bytes())
        apply_migrations(engine, tmp_path)
        legacy_id = uuid4()
        with engine.begin() as connection:
            connection.execute(text(f"""INSERT INTO {SCHEMA}.simulation_runs
                (id,seed,scenario,status,started_at,"current_time",duration_steps,initial_cash_cents,policy_json)
                VALUES (:id,42,'NORMAL','READY',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,24,1000,'{{}}')"""), {"id": legacy_id})
        assert apply_migrations(engine) == ("003_four_tier_persistence.sql",)
        with engine.connect() as connection:
            preserved = connection.execute(text(f"SELECT seed,initial_cash_cents,source_type FROM {SCHEMA}.simulation_runs WHERE id=:id"), {"id": legacy_id}).one()
            assert tuple(preserved) == (42, 1000, None)
            assert connection.scalar(text(f"SELECT count(*) FROM {SCHEMA}.vault_positions")) == 0


def test_migrations_refuse_sqlite():
    with pytest.raises(ValueError, match="require PostgreSQL"):
        apply_migrations(create_engine("sqlite:///:memory:"))


def test_dataset_store_detects_conflicting_existing_observation(session, dataset):
    session.execute(text(f"""UPDATE {SCHEMA}.organizer_observations
        SET net_flow_usd = net_flow_usd + 1
        WHERE dataset_id=:dataset AND timestamp=:timestamp"""),
        {"dataset": dataset.metadata.dataset_id, "timestamp": dataset.metadata.first_timestamp})
    with pytest.raises(ValueError, match="immutable source snapshot"):
        DatasetRepository(session).store(dataset)


@pytest.mark.parametrize("change", ["interval", "missing_timezone", "invented_timezone", "missing_source",
                                  "other_run_type", "overdraft_identity", "portfolio_total", "portfolio_net"])
def test_additional_financial_and_source_constraints(session, runs, change):
    run, _ = runs
    with pytest.raises(IntegrityError), session.begin_nested():
        if change in ("interval", "missing_timezone", "invented_timezone"):
            values = {"interval": ("native_interval_seconds", 900),
                      "missing_timezone": ("source_timezone_status", None),
                      "invented_timezone": ("source_timezone_status", "UTC")}
            column, value = values[change]
            session.execute(text(f"UPDATE {SCHEMA}.simulation_runs SET {column}=:value WHERE id=:id"),
                            {"id": run.id, "value": value})
        elif change in ("missing_source", "other_run_type"):
            values = linked(run)
            values.update(source_type=None if change == "missing_source" else "SYNTHETIC",
                          dataset_id=None, source_observation_timestamp=None)
            session.add(CashAccount(**values, balance_cents=1))
        elif change == "overdraft_identity":
            breach = RunScopedRepository(session, LiquidityBreach).add(LiquidityBreach(
                **linked(run), occurred_at=datetime(2026, 1, 1), shortfall_cents=100,
                description="fixture", reference_id="constraint-breach"))
            session.add(OverdraftLiability(**linked(run), borrowed_at=datetime(2026, 1, 1),
                borrowed_cents=100, outstanding_principal_cents=100, repaid_principal_cents=1,
                apr_pct=Decimal("12"), breach_id=breach.id, reference_id="invalid-loan"))
        else:
            session.add(PortfolioValuation(**linked(run), valued_at=datetime(2026, 1, 1),
                tier0_cash_cents=100, tier1_principal_cents=0, tier1_value_cents=0,
                tier2_market_value_cents=0, tier3_market_value_cents=0,
                total_portfolio_value_cents=101 if change == "portfolio_total" else 100,
                immediately_available_cents=100, liquidatable_value_cents=100, restricted_value_cents=0,
                liabilities_cents=50, net_portfolio_value_cents=51 if change == "portfolio_net" else 50,
                reference_id="invalid-portfolio"))
        session.flush()


def test_migration_checksum_changes_are_rejected(pg_engine, tmp_path):
    for path in sorted(MIGRATION_DIRECTORY.glob("*.sql")):
        (tmp_path / path.name).write_bytes(path.read_bytes())
    first = sorted(tmp_path.glob("*.sql"))[0]
    first.write_text(first.read_text() + "\n-- unexpected change\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Applied migration was modified"):
        apply_migrations(pg_engine, tmp_path)
