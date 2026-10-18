"""Focused API retention contract; finances remain covered by real executor tests."""
from datetime import datetime, timezone
from uuid import UUID, uuid5
import pytest
from sqlalchemy import select, func
from app.persistence.models import SimulationRun
from app.services.run_service import create_simulation_run
from app.v1_contracts import CreateRunRequest, BacktestRequest
from app.backtesting.reports import BacktestReportService, project_comparison
from app.backtesting.service import BacktestService
from .fakes import ScriptedFactory
from .test_runtime_persistence import runtime_database, runtime_session, create_run
from .test_checkpoint_verification import runtime_client

@pytest.mark.parametrize('retain', [False, True])
def test_optional_retention_preserves_default_and_returns_real_child_ids(runtime_session, runtime_client, source, monkeypatch, retain):
    session=runtime_session
    run=create_run(session, duration_steps=168)
    parent_id=run.id
    initial_count=session.scalar(select(func.count()).select_from(SimulationRun))
    def compare(self, request):
        # Stub computation only; exercise the actual route/savepoint/database persistence.
        for strategy in request.strategies:
            create_simulation_run(session, CreateRunRequest(duration_steps=168),
                run_id=uuid5(request.comparison_id,strategy), source_start_timestamp=request.start)
        result=BacktestService(ScriptedFactory(),source=source,allow_test_double=True).compare(request)
        now=datetime.now(timezone.utc)
        return project_comparison(result,started_at=now,ended_at=now)
    monkeypatch.setattr(BacktestReportService,'compare',compare)
    response=runtime_client.post(f'/api/v1/runs/{parent_id}/backtest',json={
        'strategies':['STATIC_RESERVE'],'days':7,'retain_runs':retain})
    assert response.status_code==200,response.text
    data=response.json()
    assert session.get(SimulationRun,parent_id).current_step==0
    count=session.scalar(select(func.count()).select_from(SimulationRun))
    assert count==initial_count+int(retain)
    if retain:
        child=UUID(data['child_run_ids']['STATIC_RESERVE'])
        assert child==uuid5(parent_id,'STATIC')
        assert session.get(SimulationRun,child) is not None
    else:
        assert data['child_run_ids']=={}
    assert BacktestRequest().retain_runs is False

def test_real_api_create_advance_snapshot_history(runtime_session,runtime_client):
    response=runtime_client.post('/api/v1/runs',json={
        'initial_cash_cents':2000000000,'duration_steps':168,'seed':42,'scenario':'NORMAL',
        'start_time':'2026-01-01T00:00:00Z'})
    assert response.status_code==201,response.text
    run_id=response.json()['run_id']
    opening=runtime_client.get(f'/api/v1/runs/{run_id}/snapshot').json()
    closing=runtime_client.post(f'/api/v1/runs/{run_id}/advance',json={'expected_step':0})
    assert closing.status_code==200,closing.text
    data=closing.json()
    assert opening['four_tier']['timestamp']=='2026-01-01 00:00:00'
    assert data['four_tier']['timestamp']=='2026-01-01 01:00:00'
    assert data['checking_cents']==1980720409
    assert data['four_tier']['aggregates']['net_portfolio_value_cents']==1980720409
    for resource in ['transactions','decisions','history','forecast']:
        assert runtime_client.get(f'/api/v1/runs/{run_id}/{resource}').status_code==200
    assert runtime_client.post(f'/api/v1/runs/{run_id}/advance',json={'expected_step':0}).status_code==409
