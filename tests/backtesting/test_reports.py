from datetime import datetime, timezone

import pytest

from app.backtesting import BacktestService, SharedEngineUnavailable
from app.backtesting.contracts import HistoryPoint
from app.backtesting.reports import (
    BacktestReport, BacktestReportService, PUBLIC_STRATEGIES, project_comparison, sample_history,
)
from app.backtesting.runtime import RUNTIME_SHA, SharedRuntimeFactory
from .fakes import ScriptedFactory


@pytest.mark.parametrize("limit", [2,3,17,100,1000])
def test_sampled_history_is_actual_deterministic_and_includes_endpoints(limit):
    history = tuple(HistoryPoint(timestamp=datetime(2026,1,1), checking_cents=i) for i in range(720))
    sampled = sample_history(history, limit)
    assert sampled == sample_history(history, limit)
    assert len(sampled) == min(limit,len(history))
    assert sampled[0] == history[0] and sampled[-1] == history[-1]
    assert all(point in history for point in sampled)
    assert [p.checking_cents for p in sampled] == sorted({p.checking_cents for p in sampled})


@pytest.mark.parametrize("limit", [0,1,1001,True,3.0,"10"])
def test_invalid_history_sampling_is_rejected(limit):
    with pytest.raises(ValueError):
        sample_history((), limit)


def test_comparison_projection_maps_frontend_names_without_hiding_accounting(source, request_spec):
    comparison = BacktestService(ScriptedFactory(), source=source, allow_test_double=True).compare(request_spec)
    started = datetime(2026,10,18,tzinfo=timezone.utc)
    report = project_comparison(comparison, started_at=started, ended_at=started, history_limit=5)
    assert report.execution_kind == "TEST_DOUBLE" and report.engine_integration_sha is None
    assert report.run_id == comparison.comparison_id
    assert report.seed == request_spec.seed and report.model_evaluation is None
    for raw, projected in zip(comparison.results, report.results):
        assert projected.strategy == PUBLIC_STRATEGIES[raw.strategy]
        assert len(projected.history) == 5
        assert projected.metrics.realized_interest_cents == raw.realized_interest_cents
        assert projected.metrics.net_benefit_cents == raw.net_benefit_cents
        assert projected.metrics.unpaid_cents == raw.unpaid_payouts_cents
        assert projected.metrics.average_vault_cents == raw.average_invested_cents
        assert projected.accounting.liquidation_losses_cents == raw.liquidation_losses_cents
        assert projected.accounting.borrowing_outstanding_cents == raw.borrowing_outstanding_cents
        assert projected.model_evaluation is None
    assert report.results[1].metrics.net_benefit_cents < 0
    assert report.results[2].metrics.unpaid_cents == 25  # unpaid customer payouts, NOT 400 cents of debt
    assert report.results[2].accounting.borrowing_outstanding_cents == 400
    assert BacktestReport.model_validate_json(report.model_dump_json()) == report
    assert all("history" not in r["accounting"] for r in report.model_dump(mode="json")["results"])


def test_current_runtime_stays_blocked_and_never_starts_three_identical_strategies(request_spec):
    factory = SharedRuntimeFactory()
    assert factory.capabilities.integration_sha == RUNTIME_SHA
    assert not factory.capabilities.strategies
    assert factory.blocking_reasons
    with pytest.raises(SharedEngineUnavailable, match="blocked"):
        factory.start(None)
    with pytest.raises(SharedEngineUnavailable, match="support"):
        BacktestReportService().compare(request_spec)


def test_report_service_retains_explicit_test_double_label(source, request_spec):
    reports = BacktestReportService(BacktestService(ScriptedFactory(), source=source, allow_test_double=True))
    report = reports.compare(request_spec, history_limit=3)
    assert report.execution_kind == "TEST_DOUBLE" and all(len(r.history)==3 for r in report.results)
    assert report.scenario_settings_json == request_spec.scenario.model_dump_json()


def test_frontend_money_stays_safe_when_deserializing(source, request_spec):
    from pydantic import ValidationError
    from app.backtesting.reports import FrontendFinancialMetrics
    comparison = BacktestService(ScriptedFactory(), source=source, allow_test_double=True).compare(request_spec)
    timestamp = datetime.now(timezone.utc)
    report = project_comparison(comparison, started_at=timestamp, ended_at=timestamp)
    metrics = report.results[0].metrics.model_dump()
    for value in (9_007_199_254_740_992, True, 0.5, "3"):
        with pytest.raises(ValidationError):
            FrontendFinancialMetrics(**(metrics | {"average_checking_cents":value}))
    # Legacy shared interest fields cannot express negative interest; never clamp.
    with pytest.raises(ValidationError):
        FrontendFinancialMetrics(**(metrics | {"realized_interest_cents":-1}))
