"""Fast execution preserves causal forecasts and every hourly posting."""
from datetime import datetime,timedelta
from decimal import Decimal
import pytest
from sqlalchemy import select
from app.persistence.models import OrganizerObservation,SimulationRun,LedgerEntry
from app.services.treasury_adapter import forecast_history_scope,get_hourly_forecasts_from_db,get_information_cutoff
from app.services.run_service import create_simulation_run,advance_simulation_run
from app.services.hourly_engine import execute_hourly_step
from app.v1_contracts import CreateRunRequest,AdvanceRequest
from treasury_intelligence.hourly_forecasting import forecast_hourly_cashflows
from .test_runtime_persistence import runtime_database,runtime_session
from .test_checkpoint_verification import runtime_client

@pytest.mark.parametrize('delay',[0,3600])
def test_incremental_forecasts_equal_full_original_history(runtime_session,delay):
    s=runtime_session
    row=s.scalar(select(OrganizerObservation).order_by(OrganizerObservation.timestamp))
    dataset_id=row.dataset_id
    with forecast_history_scope(s):
        for hours in (0,1,23,24,25,49,2000,2001,48):
            at=datetime(2026,1,1)+timedelta(hours=hours)
            cutoff=get_information_cutoff(at,delay)
            history=list(s.scalars(select(OrganizerObservation).where(OrganizerObservation.dataset_id==dataset_id,OrganizerObservation.timestamp<=cutoff).order_by(OrganizerObservation.timestamp)))
            expected=forecast_hourly_cashflows(history,as_of=at,horizon_hours=15,start_at=at,model_version='hourly-seasonal-naive-v1')
            actual=get_hourly_forecasts_from_db(s,dataset_id,at,horizon_hours=15,publication_delay_seconds=delay)
            assert [p.model_dump(exclude={'time_basis'}) for p in actual]==[p.model_dump(exclude={'time_basis'}) for p in expected.points]
    assert '_rj_forecast_history' not in s.info


def test_failed_scope_cannot_leave_stale_source_cache(runtime_session):
    s=runtime_session;row=s.scalar(select(OrganizerObservation).order_by(OrganizerObservation.timestamp))
    with pytest.raises(RuntimeError):
        with forecast_history_scope(s):
            get_hourly_forecasts_from_db(s,row.dataset_id,datetime(2026,1,1,2))
            raise RuntimeError('simulate failed batch')
    assert '_rj_forecast_history' not in s.info
    row.deposits_usd+=Decimal('100.00');s.flush()
    result=get_hourly_forecasts_from_db(s,row.dataset_id,datetime(2026,1,1,1))
    assert result[0].predicted_deposits_cents==int(row.deposits_usd*100)


def test_batch_equals_single_hour_execution_including_repo_maturity(runtime_session):
    s=runtime_session
    ids=[create_simulation_run(s,CreateRunRequest(duration_steps=40)).run_id for _ in range(2)]
    request=AdvanceRequest(expected_step=0,steps=40)
    batched=advance_simulation_run(s,ids[0],request)
    assert request.expected_step==0
    for step in range(40):execute_hourly_step(s,ids[1],expected_step=step)
    from app.backtesting.reports import BacktestReportService
    a,b=[BacktestReportService.report_run(s,rid) for rid in ids]
    assert a.metrics==b.metrics and a.accounting==b.accounting and a.history==b.history
    assert batched.status=='COMPLETED'
    for rid in ids:
        records=list(s.scalars(select(LedgerEntry).where(LedgerEntry.run_id==rid)))
        assert len([r for r in records if r.entry_type=='REPO_MATURITY_CREDIT'])==1
    assert '_rj_forecast_history' not in s.info


def test_batches_validate_before_writing_and_rollback_on_failure(runtime_session,runtime_client,monkeypatch):
    from app.services import run_service
    client,s=runtime_client,runtime_session
    created=client.post('/api/v1/runs',json={'duration_steps':25}).json();rid=created['run_id']
    url=f'/api/v1/runs/{rid}/advance'
    assert client.post(url,json={'expected_step':0,'steps':26}).status_code==422
    assert client.post(url,json={'expected_step':0,'steps':169}).status_code==422
    assert client.post(url,json={'expected_step':1,'steps':24}).status_code==409
    original=run_service.execute_hourly_step
    def fail_on_second(*args,**kwargs):
        if kwargs['expected_step']==1:raise ValueError('injected batch failure')
        return original(*args,**kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(run_service,'execute_hourly_step',fail_on_second)
        assert client.post(url,json={'expected_step':0,'steps':24}).status_code==422
    assert client.get(f'/api/v1/runs/{rid}/snapshot').json()['step']==0
    assert client.post(url,json={'expected_step':0,'steps':24}).json()['step']==24
    assert client.post(url,json={'expected_step':24,'steps':1}).json()['status']=='COMPLETED'
    assert client.post(url,json={'expected_step':24,'steps':1}).status_code==409
    assert client.post(url,json={'expected_step':25,'steps':1}).status_code==422


@pytest.mark.parametrize('days',[0,8,True,7.5])
def test_invalid_comparison_days_are_rejected_before_execution(runtime_client,days):
    client=runtime_client
    rid=client.post('/api/v1/runs',json={'duration_steps':168}).json()['run_id']
    assert client.post(f'/api/v1/runs/{rid}/backtest',json={'days':days}).status_code==422
    assert client.get(f'/api/v1/runs/{rid}/snapshot').json()['step']==0
