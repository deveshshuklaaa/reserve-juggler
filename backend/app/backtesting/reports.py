"""Owned report projections: preserve shared frontend fields; add explicit detail.

Route owners must opt into these richer response models to expose sampled
history/accounting. Existing shared Pydantic/OpenAPI contracts are not rewritten.
"""
from datetime import datetime, timezone
import json
from typing import Literal

from pydantic import ConfigDict, field_validator

from app.persistence.models import DatasetSource, SimulationRun
from app.v1_contracts import (
    BacktestResult as PublicBacktestResult, FinancialMetrics,
    PerformanceReport as PublicPerformanceReport, StrategyResult as PublicStrategyResult,
)
from .contracts import (
    AccountingMetrics, AccountingTotals, BacktestRequest, ComparisonResult, HistoryPoint, JS_MAX, Cash, Money, canonical_config,
)
from .runtime import RUNTIME_SHA, SharedRuntimeFactory, RuntimeReceiptUnavailable, read_hour_receipt
from .service import BacktestService, ORGANIZER_SHA256, summarize_receipts

PUBLIC_STRATEGIES = {"STATIC":"STATIC_RESERVE", "REACTIVE":"REACTIVE_RESERVE",
                     "RESERVE_JUGGLER":"RESERVE_JUGGLER"}


class FrontendFinancialMetrics(FinancialMetrics):
    model_config = ConfigDict(frozen=True, extra="forbid")
    realized_interest_cents: Cash
    accrued_interest_cents: Cash
    average_checking_cents: Cash
    average_vault_cents: Cash
    redemption_penalties_cents: Cash
    emergency_borrowing_cost_cents: Cash
    unpaid_cents: Cash
    net_benefit_cents: Money

    @field_validator("*", mode="after")
    @classmethod
    def safe_money(cls, value, info):
        if info.field_name.endswith("_cents") and (type(value) is not int or abs(value) > JS_MAX):
            raise ValueError("Report money must be JavaScript-safe integer cents")
        return value


class ReportStrategyResult(PublicStrategyResult):
    model_config = ConfigDict(frozen=True, extra="forbid")
    metrics: FrontendFinancialMetrics
    history: tuple[HistoryPoint, ...]
    accounting: AccountingTotals
    model_evaluation: None = None


class BacktestReport(PublicBacktestResult):
    dataset_id: str | None = None
    dataset_sha256: str | None = None
    child_run_ids: dict[str, str] = {}
    model_config = ConfigDict(frozen=True, extra="forbid")
    results: tuple[ReportStrategyResult, ...]
    execution_kind: Literal["SHARED","TEST_DOUBLE"]
    engine_integration_sha: str | None
    conditions_sha256: str
    scenario_settings_json: str
    model_evaluation: None = None


class RunReport(PublicPerformanceReport):
    dataset_id: str | None = None
    dataset_sha256: str | None = None
    model_config = ConfigDict(frozen=True, extra="forbid")
    metrics: FrontendFinancialMetrics | None
    history: tuple[HistoryPoint, ...]
    accounting: AccountingTotals | None
    scenario_settings_json: str
    # A run may have been executed elsewhere. Never assert an unpersisted code SHA.
    runtime_commit_verified_by_reporter: str = RUNTIME_SHA
    execution_provenance: Literal["NOT_RECORDED_BY_RUNTIME"] = "NOT_RECORDED_BY_RUNTIME"
    model_evaluation: None = None


def sample_history(history, limit=100):
    """Keep actual points, both endpoints, deterministic spacing; no interpolation."""
    if type(limit) is not int or not 2 <= limit <= 1000:
        raise ValueError("history_limit must be an integer between 2 and 1000")
    if len(history) <= limit:
        return tuple(history)
    return tuple(history[i*(len(history)-1)//(limit-1)] for i in range(limit))


def frontend_metrics(summary: AccountingMetrics) -> FrontendFinancialMetrics:
    """Legacy name mapping; no fabricated zero metrics or substitution of debt for income."""
    summary = AccountingMetrics.model_validate(summary)
    return FrontendFinancialMetrics(
        realized_interest_cents=summary.realized_interest_cents,
        accrued_interest_cents=summary.accrued_interest_cents,
        average_checking_cents=summary.average_checking_cents,
        average_vault_cents=summary.average_invested_cents,
        redemption_penalties_cents=summary.penalties_cents,
        emergency_borrowing_cost_cents=summary.borrowing_costs_cents,
        emergency_events=summary.emergency_events,
        reserve_breaches=summary.reserve_breaches,
        failed_payouts=summary.failed_payouts,
        unpaid_cents=summary.unpaid_payouts_cents,
        net_benefit_cents=summary.net_benefit_cents,
    )


def project_comparison(comparison: ComparisonResult, *, started_at, ended_at, history_limit=100) -> BacktestReport:
    """Project an already validated evaluation, retaining safe money and test-double labels."""
    comparison = ComparisonResult.model_validate(comparison)
    results = []
    for strategy in comparison.results:
        fields = strategy.model_dump(exclude={"strategy","run_id"})
        summary = AccountingMetrics(**fields)
        results.append(ReportStrategyResult(
            strategy=PUBLIC_STRATEGIES[strategy.strategy], metrics=frontend_metrics(summary),
            history=sample_history(summary.history, history_limit),
            accounting=AccountingTotals(**summary.model_dump(exclude={"history"}))))
    return BacktestReport(
        dataset_id=comparison.dataset_id, dataset_sha256=comparison.dataset_sha256,
        run_id=comparison.comparison_id, scenario=comparison.scenario.name, seed=comparison.seed,
        started_at=started_at, ended_at=ended_at, results=results,
        execution_kind=comparison.execution_kind, engine_integration_sha=comparison.engine_integration_sha,
        conditions_sha256=comparison.conditions_sha256,
        scenario_settings_json=comparison.scenario.model_dump_json())


class BacktestReportService:
    def __init__(self, backtester=None):
        self.backtester = backtester if backtester is not None else BacktestService(SharedRuntimeFactory())

    def compare(self, request: BacktestRequest, *, history_limit=100) -> BacktestReport:
        sample_history((), history_limit)
        started = datetime.now(timezone.utc)  # operation metadata, NOT organizer source time
        comparison = self.backtester.compare(request)
        return project_comparison(comparison, started_at=started, ended_at=datetime.now(timezone.utc),
                                  history_limit=history_limit)

    @staticmethod
    def report_run(session, run_id, *, history_limit=100) -> RunReport:
        sample_history((), history_limit)
        run = session.get(SimulationRun, run_id)
        if run is None:
            raise KeyError(run_id)
        source = session.get(DatasetSource, run.dataset_id)
        if run.source_type != "ORGANIZER_HISTORICAL" or source is None or (source.content_hash != ORGANIZER_SHA256 and not (source.source_path.startswith("upload/") and source.validation_status in ("VALIDATED", "VALIDATED_WITH_DIAGNOSTICS"))):
            raise RuntimeReceiptUnavailable("Report requires a validated persisted organizer historical source")
        if run.seed is None:
            raise RuntimeReceiptUnavailable("Run has no reproducible seed")
        def _sanitize(obj):
            if isinstance(obj, float):
                return str(obj)
            if isinstance(obj, dict):
                return {k: _sanitize(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [_sanitize(v) for v in obj]
            return obj

        scenarios = canonical_config(json.dumps(_sanitize({"initial_scenario":run.scenario,
                                     "schedule":(run.policy_json or {}).get("scenarios",[])})))
        summary = None
        if run.current_step:
            receipts = [read_hour_receipt(session, run.id, step) for step in range(1,run.current_step+1)]
            summary = summarize_receipts(receipts[0].opening, receipts)
        return RunReport(
            dataset_id=source.dataset_id, dataset_sha256=source.content_hash,
            run_id=run.id, scenario=run.scenario, seed=run.seed,
            started_at=run.created_at, ended_at=run.updated_at if run.current_step >= run.duration_steps else None,
            metrics=frontend_metrics(summary) if summary is not None else None,
            history=sample_history(summary.history, history_limit) if summary is not None else (),
            accounting=AccountingTotals(**summary.model_dump(exclude={"history"})) if summary is not None else None,
            scenario_settings_json=scenarios)
