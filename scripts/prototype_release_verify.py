"""Focused release evidence; invokes the shared executor, never simulates finances.

Run from the repository root with the existing backend environment. Creates and
retains one explicitly named disposable PostgreSQL database and writes JSON/log
artifacts to --output. Never changes source observations, runtime, or models.
The HTTP comparison is ephemeral by contract; a second service comparison is
committed solely to provide durable audit evidence for Member 1.
"""
import argparse
from datetime import datetime
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import Request, urlopen
from uuid import UUID, uuid4

from sqlalchemy import create_engine, select, func
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT)]


def encode(value):
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, (datetime, Decimal, UUID)):
        return str(value)
    raise TypeError(type(value).__name__)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8017)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    def save(name, data):
        (args.output / (name + ".json")).write_text(
            json.dumps(data, default=encode, indent=2), encoding="utf-8")

    base = make_url(os.environ["BACKTEST_TEST_DATABASE_URL"])
    assert (base.database or "").startswith("reserve_juggler_m2_test")
    name = "reserve_juggler_m2_test_release_" + uuid4().hex[:12]
    assert re.fullmatch(r"reserve_juggler_m2_test_release_[0-9a-f]{12}", name)
    admin = create_engine(base, isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.exec_driver_sql(f'CREATE DATABASE "{name}"')
    admin.dispose()
    url = base.set(database=name, drivername="postgresql+psycopg2")
    os.environ["DATABASE_URL"] = url.render_as_string(hide_password=False)
    os.environ["PYTHONPATH"] = os.pathsep.join((str(ROOT / "backend"), str(ROOT)))
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    engine = create_engine(url)

    from app.data.organizer import OrganizerDatasetSource
    from app.persistence.migrations import apply_migrations
    from app.persistence.repositories import DatasetRepository
    from app.persistence.models import (SimulationRun, OrganizerObservation, LedgerEntry,
        TreasuryDecision, InvestmentMovement, OverdraftMovement, PortfolioValuation,
        CashAccount, RepoPosition, BondPosition, EquityPosition)
    from app.backtesting.contracts import BacktestRequest
    from app.backtesting import runtime
    from app.backtesting.service import BacktestService
    from app.backtesting.reports import BacktestReportService
    from app.services import treasury_adapter
    from app.services.run_service import get_simulation_snapshot
    from treasury_intelligence.optimizer import recommend_four_tier_allocation

    migrations = apply_migrations(engine)
    source = OrganizerDatasetSource().load()
    with Session(engine) as session, session.begin():
        DatasetRepository(session).store(source)
    source_hash = hashlib.sha256((ROOT / "treasury_4tier_dataset.csv").read_bytes()).hexdigest()
    tested_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    meta = dict(tested_sha=tested_sha, core_runtime_sha=runtime.RUNTIME_SHA,
        database=name, database_url=url.render_as_string(hide_password=False),
        migrations=migrations, organizer_rows=len(source), organizer_sha256=source_hash,
        app_command=f'{sys.executable} -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port {args.port}',
        source_time_basis="UNSPECIFIED", publication_delay_seconds=0)
    save("environment", meta)
    print("BOOTSTRAP", json.dumps(meta), flush=True)

    root = f"http://127.0.0.1:{args.port}"
    def call(method, path, data=None):
        request = Request(root + path, method=method,
            data=None if data is None else json.dumps(data).encode(),
            headers={"Content-Type": "application/json"})
        with urlopen(request, timeout=240) as response:
            result = json.loads(response.read())
            print("HTTP", method, path, response.status, flush=True)
            return result

    server_log = (args.output / "uvicorn.log").open("w", encoding="utf-8")
    server = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app",
        "--app-dir", "backend", "--host", "127.0.0.1", "--port", str(args.port)],
        cwd=ROOT, env=dict(os.environ), stdout=server_log, stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    try:
        deadline = time.monotonic() + 30
        while True:
            if server.poll() is not None:
                raise RuntimeError("Backend exited; inspect uvicorn.log")
            try:
                health = call("GET", "/health")
                break
            except (URLError, TimeoutError):
                if time.monotonic() > deadline:
                    raise
                time.sleep(.2)
        assert health["database"] == "connected"
        live = call("POST", "/api/v1/runs", dict(initial_cash_cents=2_000_000_000,
            duration_steps=168, seed=42, scenario="NORMAL"))
        parent = live["run_id"]
        save("live-created", live)
        save("live-initial", call("GET", f"/api/v1/runs/{parent}/snapshot"))
        save("live-policy", call("PATCH", f"/api/v1/runs/{parent}/policy",
            {"operational_buffer_cents": 50_000_000}))
        # Explicit NORMAL scheduling tests the route without contaminating the comparison.
        save("live-scenario", call("POST", f"/api/v1/runs/{parent}/scenario",
            {"scenario": "NORMAL", "parameters": {}, "effective_step": 2}))
        save("live-advanced", call("POST", f"/api/v1/runs/{parent}/advance",
            {"expected_step": 0, "steps": 1}))
        save("live-report", call("GET", f"/api/v1/runs/{parent}/report"))
        api_comparison = call("POST", f"/api/v1/runs/{parent}/backtest",
            {"days": 7, "scenario": "NORMAL", "seed": 42,
             "strategies": ["STATIC", "REACTIVE", "RESERVE_JUGGLER"]})
        assert len(api_comparison["results"]) == 3
        save("http-comparison", api_comparison)

        original = treasury_adapter.recommend_four_tier_allocation
        assert original.__code__ is recommend_four_tier_allocation.__code__
        canonical_calls, latest = [], []
        def capture(request):
            result = original(request)  # Actual canonical implementation, not a test double.
            latest[:] = [dict(request=request.model_dump(mode="json"),
                             response=result.model_dump(mode="json"))]
            canonical_calls.append(result.request_id if hasattr(result, "request_id") else str(request.request_id))
            return result
        treasury_adapter.recommend_four_tier_allocation = capture
        original_step = runtime.execute_hourly_step
        evidence = {}
        def row_data(row):
            return {column.key: getattr(row, column.key) for column in row.__table__.columns}
        def capture_step(session, run_id, expected_step, **kwargs):
            latest.clear()
            result = original_step(session, run_id, expected_step, **kwargs)
            if latest:
                decision = session.scalar(select(TreasuryDecision).where(
                    TreasuryDecision.run_id == run_id, TreasuryDecision.step == expected_step + 1))
                details = decision.decision_details_json
                ids = {order["id"] for order in latest[0]["response"]["decision"]["orders"]}
                matching = [fill for fill in details.get("orders_executed", [])
                            if fill.get("order_id") in ids]
                key = "first_executed_recommendation" if matching else "first_optimizer_call"
                if key not in evidence:
                    evidence[key] = latest[0] | dict(run_id=str(run_id), step=expected_step+1,
                        decision=row_data(decision), matched_fills=matching,
                        snapshot=get_simulation_snapshot(session, run_id).model_dump(mode="json"),
                        ledger=[row_data(r) for r in session.scalars(select(LedgerEntry).where(
                            LedgerEntry.run_id == run_id, LedgerEntry.step == expected_step+1))],
                        movements=[row_data(r) for r in session.scalars(select(InvestmentMovement).where(
                            InvestmentMovement.run_id == run_id))])
            return result
        runtime.execute_hourly_step = capture_step
        request = BacktestRequest(comparison_id=uuid4(), start=source.observations[0].timestamp,
            days=7, initial_capital_cents=2_000_000_000, seed=42)
        try:
            with Session(engine) as session:
                comparison = BacktestService(runtime.SharedRuntimeFactory(session=session)).compare(request)
                session.commit()
        finally:
            runtime.execute_hourly_step = original_step
            treasury_adapter.recommend_four_tier_allocation = original
        save("persisted-comparison", comparison)
        save("canonical-evidence", dict(call_count=len(canonical_calls), **evidence))

        observations = source.observations[:168]
        deposits = sum(int(o.deposits_usd * 100) for o in observations)
        withdrawals = sum(int(o.withdrawals_usd * 100) for o in observations)
        source_net = sum(o.net_flow_usd for o in observations)
        audits = []
        for result in comparison.results:
            persisted_report = call("GET", f"/api/v1/runs/{result.run_id}/report")
            save("report-" + result.strategy, persisted_report)
            save("snapshot-" + result.strategy, call("GET", f"/api/v1/runs/{result.run_id}/snapshot"))
            with Session(engine) as session:
                run = session.get(SimulationRun, result.run_id)
                ds = list(session.scalars(select(TreasuryDecision).where(
                    TreasuryDecision.run_id == run.id).order_by(TreasuryDecision.step)))
                ledgers = list(session.scalars(select(LedgerEntry).where(
                    LedgerEntry.run_id == run.id).order_by(LedgerEntry.step, LedgerEntry.id)))
                paid = sum(r.amount_cents for r in ledgers if r.entry_type == "CUSTOMER_WITHDRAWAL_OUTFLOW")
                inflows = sum(r.amount_cents for r in ledgers if r.entry_type == "CUSTOMER_DEPOSIT_INFLOW")
                unpaid = sum(d.decision_details_json["payout"]["unpaid_amount_cents"] for d in ds)
                failed = sum(d.decision_details_json["payout"]["unpaid_amount_cents"] > 0 for d in ds)
                requested = sum(d.decision_details_json["payout"]["requested_amount_cents"] for d in ds)
                assert len(ds) == run.current_step == 168
                assert requested == withdrawals == paid + unpaid
                assert inflows == deposits
                assert failed == result.failed_payouts and unpaid == result.unpaid_payouts_cents
                assert persisted_report["accounting"] == result.model_dump(mode="json", exclude={"strategy", "run_id", "history"})
                value = session.scalar(select(PortfolioValuation).where(
                    PortfolioValuation.run_id == run.id).order_by(PortfolioValuation.valued_at.desc()).limit(1))
                cash = session.scalar(select(CashAccount).where(CashAccount.run_id == run.id))
                assert value.net_portfolio_value_cents == value.total_portfolio_value_cents-value.liabilities_cents
                assert cash.balance_cents == value.tier0_cash_cents
                assert value.net_portfolio_value_cents-run.initial_cash_cents-inflows+paid == result.net_benefit_cents
                count_models = (LedgerEntry, TreasuryDecision, InvestmentMovement, OverdraftMovement,
                                RepoPosition, BondPosition, EquityPosition, PortfolioValuation)
                counts = {model.__name__: session.scalar(select(func.count()).select_from(model).where(
                    model.run_id == run.id)) for model in count_models}
                hourly = [dict(timestamp=o.timestamp, source_deposits_usd=o.deposits_usd,
                    source_withdrawals_usd=o.withdrawals_usd, source_net_flow_usd=o.net_flow_usd,
                    decision_requested_cents=d.expected_outflow_cents,
                    payout=d.decision_details_json["payout"])
                    for o, d in zip(observations, ds)]
                save("payout-trace-" + result.strategy, hourly)
                audits.append(dict(strategy=result.strategy, run_id=str(run.id), counts=counts,
                    initial_cash_cents=run.initial_cash_cents, requested_cents=requested, paid_cents=paid,
                    unpaid_cents=unpaid, failed_payouts=failed, inflow_cents=inflows,
                    last_valuation=row_data(value), metrics= result.model_dump(mode="json", exclude={"history"})))
        save("persisted-audit", audits)
        save("workload", dict(start=request.start, end_exclusive=request.end_exclusive, steps=168,
            source_deposits_cents=deposits, source_withdrawals_cents=withdrawals,
            preserved_source_net_flow_usd=source_net,
            deposits_less_withdrawals_cents=deposits-withdrawals,
            source_rows_unchanged=source_hash == hashlib.sha256((ROOT/"treasury_4tier_dataset.csv").read_bytes()).hexdigest(),
            usd_to_cents="Exact source Decimal multiplied by 100 once; original source net_flow is not substituted"))
        print("PERSISTED_COMPARISON", json.dumps(audits, default=encode), flush=True)
        print("CANONICAL_CALLS", len(canonical_calls), "executed_recommendation",
              "first_executed_recommendation" in evidence, flush=True)
        print("RELEASE_SMOKE_PASS; database retained for independent inspection:", name, flush=True)
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=10)
        server_log.close()
        engine.dispose()


if __name__ == "__main__":
    main()

