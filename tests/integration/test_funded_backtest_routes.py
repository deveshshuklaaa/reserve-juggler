"""Route/lifecycle diagnostics with real funds; not three-strategy release acceptance."""
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from test_four_tier_runtime import dataset, pg_engine, pg_url, session
from app.database import get_db
from app.main import app
from app.persistence.models import CashAccount, SimulationRun
from app.services.hourly_engine import execute_hourly_step
from app.services.run_service import create_simulation_run
from app.v1_contracts import CreateRunRequest


def test_funded_subset_repeat_and_detailed_report_use_real_shared_execution(session):
    created = create_simulation_run(session, CreateRunRequest(
        initial_cash_cents=100_000_000_000, duration_steps=168))
    run = session.get(SimulationRun, created.run_id)
    execute_hourly_step(session, run.id, 0, strategy="STATIC")
    cash_before = session.scalar(select(CashAccount.balance_cents).where(CashAccount.run_id == run.id))
    runs_before = session.scalar(select(func.count()).select_from(SimulationRun))
    app.dependency_overrides[get_db] = lambda: session
    try:
        with TestClient(app) as client:
            url = f"/api/v1/runs/{run.id}"
            reports = [client.post(url+"/backtest", json={"strategies": ["STATIC_RESERVE"]}) for _ in range(2)]
            assert [r.status_code for r in reports] == [200, 200], [r.text for r in reports]
            left, right = [r.json() for r in reports]
            assert left["results"] == right["results"]
            assert left["conditions_sha256"] == right["conditions_sha256"]
            assert [r["strategy"] for r in left["results"]] == ["STATIC_RESERVE"]
            assert left["execution_kind"] == "SHARED"
            selected = left["results"][0]
            assert selected["model_evaluation"] is None
            assert 2 <= len(selected["history"]) <= 100
            assert {"accounting", "history", "metrics"} <= selected.keys()
            for name, value in selected["metrics"].items():
                if name.endswith("_cents"):
                    assert type(value) is int and abs(value) <= 2**53-1
            response = client.get(url+"/report")
            assert response.status_code == 200, response.text
            detail = response.json()
            assert {"accounting", "history", "model_evaluation", "scenario_settings_json", "execution_provenance"} <= detail.keys()
            assert detail["model_evaluation"] is None
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert session.scalar(select(func.count()).select_from(SimulationRun)) == runs_before
    assert session.get(SimulationRun, run.id).current_step == 1
    assert session.scalar(select(CashAccount.balance_cents).where(CashAccount.run_id == run.id)) == cash_before
