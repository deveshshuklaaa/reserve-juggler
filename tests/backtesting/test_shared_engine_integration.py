"""Opt-in real-engine tests. Missing Agent 1 dependency is a skip, never a fake pass."""
import hashlib
import importlib
import os
from pathlib import Path
from uuid import uuid4

import pytest

from app.backtesting import BacktestRequest, BacktestService, ScenarioSpec
from app.backtesting.service import ORGANIZER_SHA256


@pytest.fixture
def shared_factory():
    target = os.getenv("BACKTEST_SHARED_ENGINE_FACTORY")
    if not target:
        pytest.skip("PENDING: Agent 1 must publish shared hourly engine branch/SHA/path/receipt schema")
    branch = os.getenv("BACKTEST_SHARED_ENGINE_BRANCH")
    sha = os.getenv("BACKTEST_SHARED_ENGINE_SHA")
    assert branch and sha, "Explicit published branch and full integration SHA are required"
    module_name, separator, callable_name = target.partition(":")
    assert separator and module_name and callable_name, "Use published.module:zero_argument_factory"
    factory = getattr(importlib.import_module(module_name), callable_name)()
    assert factory.capabilities.execution_kind == "SHARED", "No fake in integration tests"
    assert factory.capabilities.integration_sha == sha
    return factory


@pytest.mark.parametrize("days,scenario", [
    (7,"NORMAL"), (14,"NORMAL"), (30,"NORMAL"), (7,"HIGH_WITHDRAWAL"),
    (7,"LOW_DEPOSIT"), (7,"SETTLEMENT_DELAY"), (7,"LIQUIDITY_SHOCK"),
])
def test_actual_shared_engine_comparison(shared_factory, request_spec, days, scenario):
    path = Path(__file__).resolve().parents[2] / "treasury_4tier_dataset.csv"
    before = path.read_bytes()
    spec = BacktestRequest(**(request_spec.model_dump() | {
        "comparison_id": uuid4(), "days": days, "scenario": ScenarioSpec(name=scenario), "policy_json": "{}"}))
    result = BacktestService(shared_factory).compare(spec)
    assert result.execution_kind == "SHARED"
    assert result.engine_integration_sha == os.environ["BACKTEST_SHARED_ENGINE_SHA"]
    assert result.dataset_sha256 == ORGANIZER_SHA256
    assert all(len(m.history) == days*24 for m in result.results)
    assert all(m.model_evaluation is None for m in result.results)
    # Actual-engine determinism, including provider's isolated run lifecycle.
    repeated = BacktestService(shared_factory).compare(spec)
    assert repeated == result
    assert path.read_bytes() == before and hashlib.sha256(before).hexdigest() == ORGANIZER_SHA256
