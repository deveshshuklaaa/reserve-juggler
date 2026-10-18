"""Actual CSV -> PostgreSQL -> shared hourly engine workflow; no financial mocks."""
import csv
import hashlib
import io
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.data.organizer import DatasetValidationError
from app.persistence.models import DatasetSource, OrganizerObservation, SimulationRun
from app.services.dataset_import import validate_upload
from .test_runtime_persistence import runtime_database, runtime_session
from .test_checkpoint_verification import runtime_client


def upload_csv(count=48, *, changes=None):
    source = Path(__file__).resolve().parents[2] / 'treasury_4tier_dataset.csv'
    with source.open(encoding='utf-8-sig') as stream:
        rows = list(csv.DictReader(stream))[:count]
    for index, row in enumerate(rows):
        time = datetime(2026, 2, 1) + timedelta(hours=index)
        row.update(timestamp=str(time), deposits_usd='123.45', withdrawals_usd='23.45', net_flow_usd='99.99',
                   repo_sweep_window_open=str(time.hour == 17), repo_sweep_mature=str(time.hour == 8))
    if changes:
        rows[0].update(changes)
    text = io.StringIO(newline='')
    writer = csv.DictWriter(text, fieldnames=rows[0]); writer.writeheader(); writer.writerows(rows)
    return text.getvalue().encode()


def post_csv(client, raw):
    return client.post('/api/v1/datasets', content=raw, headers={'content-type': 'text/csv; charset=utf-8'})


def test_3500_rows_and_empty_suffix_preserve_source_bytes_and_values():
    raw = upload_csv(3500) + b',,,,,,,,,,,,,,,\r\n' * 5075
    dataset = validate_upload(raw)
    assert len(dataset) == 3500
    assert dataset.metadata.content_hash == hashlib.sha256(raw).hexdigest()
    assert str(dataset.observations[0].net_flow_usd) == '99.99'
    assert dataset.validation.reconciliation.one_cent_differences == 3500


@pytest.mark.parametrize('changes', [
    {'timestamp': '01-02-2026 00:00'}, {'repo_sweep_window_open': 'FALSE'},
    {'repo_sweep_mature': 'True'}, {'deposits_usd': '-1'}, {'deposits_usd': '0.001'},
    {'deposits_usd': '1e999999'}, {'tier2_bond_price_index': 'NaN'},
    {'tier2_bond_mod_duration': '0'}, {'tier3_stock_liquidation_haircut_pct': '101'},
])
def test_reject_invalid_upload(changes):
    with pytest.raises(DatasetValidationError):
        validate_upload(upload_csv(changes=changes))


@pytest.mark.parametrize('raw', [b'', b'\xff', b'x' * (2 * 1024 * 1024 + 1), b'"unclosed',
                                upload_csv(1), upload_csv(5001),
                                upload_csv(2).replace(b'2026-02-01 01:00:00', b'2026-02-01 02:00:00')], ids=['empty','encoding','oversize','quote','one-row','too-many','gap'])
def test_reject_invalid_csv_shape(raw):
    with pytest.raises(DatasetValidationError):
        validate_upload(raw)


def test_import_idempotent_and_run_uses_exact_uploaded_source(runtime_session, runtime_client):
    session, client = runtime_session, runtime_client
    raw = upload_csv(2)
    before = session.scalar(select(func.count()).select_from(DatasetSource))
    response = post_csv(client, raw)
    assert response.status_code == 201, response.text
    imported = response.json()
    assert imported['row_count'] == 2
    assert imported['validation']['reconciliation']['one_cent_differences'] == 2
    assert post_csv(client, raw).json()['dataset_id'] == imported['dataset_id']
    assert session.scalar(select(func.count()).select_from(DatasetSource)) == before + 1
    assert len(list(session.scalars(select(OrganizerObservation).where(
        OrganizerObservation.dataset_id == imported['dataset_id'])))) == 2
    created = client.post('/api/v1/runs', json={'dataset_id': imported['dataset_id'], 'duration_steps': 2})
    assert created.status_code == 201, created.text
    run_id = created.json()['run_id']
    snap = client.get(f'/api/v1/runs/{run_id}/snapshot').json()
    assert snap['source_dataset']['dataset_id'] == imported['dataset_id']
    assert snap['source_dataset']['uploaded'] is True
    assert snap['four_tier']['timestamp'] == '2026-02-01 00:00:00'
    assert snap['duration_steps'] == 2
    for step in range(2):
        response = client.post(f'/api/v1/runs/{run_id}/advance', json={'expected_step': step})
        assert response.status_code == 200, response.text
    assert response.json()['status'] == 'COMPLETED'
    assert response.json()['checking_cents'] == 2_000_020_000
    report = client.get(f'/api/v1/runs/{run_id}/report')
    assert report.status_code == 200, report.text
    assert imported['dataset_id'] in report.text
    default = client.post('/api/v1/runs', json={'duration_steps': 2})
    assert default.status_code == 201
    default_snap = client.get(f"/api/v1/runs/{default.json()['run_id']}/snapshot").json()
    assert default_snap['source_dataset']['dataset_id'] != imported['dataset_id']
    assert default_snap['source_dataset']['uploaded'] is False


def test_invalid_upload_and_run_window_do_not_write(runtime_session, runtime_client):
    client, session = runtime_client, runtime_session
    before = session.scalar(select(func.count()).select_from(DatasetSource))
    assert post_csv(client, upload_csv(changes={'deposits_usd': '-1'})).status_code == 422
    assert client.post('/api/v1/datasets', json={}).status_code == 415
    assert post_csv(client, b'x' * (2 * 1024 * 1024 + 1)).status_code == 413
    assert session.scalar(select(func.count()).select_from(DatasetSource)) == before
    ds = post_csv(client, upload_csv(2)).json()['dataset_id']
    before_runs = session.scalar(select(func.count()).select_from(SimulationRun))
    assert client.post('/api/v1/runs', json={'dataset_id': ds, 'duration_steps': 3}).status_code == 422
    assert client.post('/api/v1/runs', json={'dataset_id': 'missing'}).status_code == 422
    assert session.scalar(select(func.count()).select_from(SimulationRun)) == before_runs


def test_uploaded_source_strategy_comparison(runtime_session, runtime_client):
    client = runtime_client
    ds = post_csv(client, upload_csv(168)).json()['dataset_id']
    created = client.post('/api/v1/runs', json={'dataset_id': ds, 'duration_steps': 168})
    run_id = created.json()['run_id']
    response = client.post(f'/api/v1/runs/{run_id}/backtest', json={'days': 7, 'strategies': ['STATIC_RESERVE'], 'retain_runs': True})
    assert response.status_code == 200, response.text
    data = response.json()
    assert ds in response.text
    assert data['child_run_ids']['STATIC_RESERVE']
    assert client.get(f'/api/v1/runs/{run_id}/snapshot').json()['step'] == 0
    child = data['child_run_ids']['STATIC_RESERVE']
    snapshot = client.get(f'/api/v1/runs/{child}/snapshot').json()
    assert snapshot['source_dataset']['dataset_id'] == ds
    assert snapshot['status'] == 'COMPLETED'
