from datetime import datetime
from uuid import UUID

import pytest

from app.backtesting import BacktestRequest
from app.data.organizer import OrganizerDatasetSource


@pytest.fixture(scope="session")
def dataset():
    return OrganizerDatasetSource().load()


@pytest.fixture
def source(dataset):
    class LoadedSource:
        def load(self):
            return dataset
    return LoadedSource()


@pytest.fixture
def request_spec():
    return BacktestRequest(
        comparison_id=UUID("388fc688-88ab-40c1-9b41-4ec0990ac186"),
        start=datetime(2026, 1, 1), days=7, initial_capital_cents=100_000, seed=17,
        policy_json='{"reserve_fraction":"0.20"}',
    )


def make_shared_runtime_factory():
    from app.database import SessionLocal
    from app.backtesting.runtime import SharedRuntimeFactory
    return SharedRuntimeFactory(session_factory=SessionLocal)

