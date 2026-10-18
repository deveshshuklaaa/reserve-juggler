from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta
from decimal import localcontext
import hashlib
import json
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.backtesting import BacktestRequest, BacktestService, EngineContractError, ScenarioSpec, SharedEngineUnavailable
from app.backtesting.contracts import ComparisonResult, SCENARIOS, STRATEGIES
from app.backtesting.service import ORGANIZER_SHA256
from app.data.organizer import OrganizerDatasetSource
from .fakes import ScriptedFactory, journal, state


def evaluate(source, spec, factory=None):
    return BacktestService(factory or ScriptedFactory(), source=source, allow_test_double=True).compare(spec)


@pytest.mark.parametrize("days,steps", [(7,168), (14,336), (30,720)])
def test_periods_have_exact_hourly_closing_history(source, request_spec, days, steps):
    spec = BacktestRequest(**(request_spec.model_dump() | {"days":days}))
    result = evaluate(source, spec)
    assert result.steps == steps
    assert result.end_exclusive == spec.start + timedelta(hours=steps)
    assert result.native_interval_seconds == 3600 and result.time_basis == "UNSPECIFIED"
    for metrics in result.results:
        assert len(metrics.history) == steps
        assert metrics.history[0].timestamp == spec.start
        assert metrics.history[-1].timestamp == spec.end_exclusive - timedelta(hours=1)


def test_actual_reported_accounting_not_cash_profit(source, request_spec):
    result = evaluate(source, request_spec)
    static, reactive, rich = result.results
    assert static.net_benefit_cents == 0
    assert reactive.net_benefit_cents == -2
    assert rich.realized_interest_cents == 10
    assert rich.realized_market_pnl_cents == 20
    assert rich.unrealized_market_pnl_cents == -10
    assert rich.accrued_interest_cents == 0
    assert rich.penalties_cents == 7
    assert rich.contractual_penalties_cents == 2
    assert rich.liquidation_losses_cents == 5
    assert rich.transaction_costs_cents == 1
    assert rich.borrowing_costs_cents == 3  # incurred once; paid later does not duplicate it
    assert rich.unpaid_borrowing_costs_cents == 0
    assert rich.borrowing_outstanding_cents == 400  # closing debt, not sum of hourly debt
    assert rich.net_benefit_cents == 9
    assert rich.customer_cash_delta_cents == 40
    assert rich.ending_net_asset_value_cents == 100_049
    assert rich.history[-1].checking_cents == 100_359  # cash includes debt; cash gain is not profit
    assert (rich.reserve_breaches, rich.emergency_events, rich.failed_payouts, rich.sweeps) == (1,1,1,1)
    for m in result.results:
        assert m.net_benefit_cents == (m.realized_interest_cents + m.accrued_interest_cents
            + m.realized_market_pnl_cents + m.unrealized_market_pnl_cents
            - m.penalties_cents - m.transaction_costs_cents - m.borrowing_costs_cents)
        assert m.net_benefit_cents == m.ending_net_asset_value_cents - request_spec.initial_capital_cents - m.customer_cash_delta_cents
        assert m.model_evaluation is None


def test_borrow_draw_is_not_income_and_unpaid_expense_is_not_free_cash(source, request_spec):
    def receipts(run, frame, receipt):
        if frame.step == 0:
            return journal(receipt.opening, timestamp=receipt.timestamp, digest=frame.source_digest,
                           event_ids=("borrow",), financing_cash_delta_cents=100, borrowing_costs_cents=3)
        return journal(receipt.opening, timestamp=receipt.timestamp, digest=frame.source_digest)
    factory = ScriptedFactory(receipt_hook=receipts)
    result = evaluate(source, request_spec, factory)
    for m in result.results:
        assert m.realized_interest_cents == 0 and m.net_benefit_cents == -3
        assert m.borrowing_outstanding_cents == 100 and m.unpaid_borrowing_costs_cents == 3
        assert m.history[-1].checking_cents == 100_100


def test_reproducible_conditions_isolated_starts_and_wire_roundtrip(source, request_spec):
    factory = ScriptedFactory()
    service = BacktestService(factory, source=source, allow_test_double=True)
    first, second = service.compare(request_spec), service.compare(request_spec)
    assert first == second
    assert first.execution_kind == "TEST_DOUBLE" and first.engine_integration_sha is None
    assert ComparisonResult.model_validate_json(first.model_dump_json()) == first
    starts = [r.spec for r in factory.runs[:3]]
    assert tuple(s.strategy for s in starts) == STRATEGIES
    assert len({s.run_id for s in starts}) == 3
    for spec in starts:
        assert spec.start == request_spec.start and spec.end_exclusive == request_spec.end_exclusive
        assert spec.initial_capital_cents == request_spec.initial_capital_cents and spec.seed == request_spec.seed
        assert spec.policy_json == request_spec.policy_json and spec.scenario == request_spec.scenario
        assert spec.conditions_sha256 == first.conditions_sha256
    assert all(r.initial_state == state(request_spec.initial_capital_cents) and r.closed for r in factory.runs)
    other = evaluate(source, BacktestRequest(**(request_spec.model_dump() | {"comparison_id":uuid4()})))
    assert first.conditions_sha256 == other.conditions_sha256
    assert [m.net_benefit_cents for m in first.results] == [m.net_benefit_cents for m in other.results]
    assert first.results[0].run_id != other.results[0].run_id
    wire = json.loads(first.model_dump_json())
    def safe_money(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key.endswith("_cents"):
                    assert type(item) is int and abs(item) <= 9_007_199_254_740_991
                safe_money(item)
        elif isinstance(value, list):
            for item in value:
                safe_money(item)
    safe_money(wire)


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_scenarios_forwarded_identically_without_rewriting_source(source, dataset, request_spec, scenario):
    before = tuple(row.model_dump_json() for row in dataset.observations)
    factory = ScriptedFactory()
    spec = BacktestRequest(**(request_spec.model_dump() | {
        "scenario":ScenarioSpec(name=scenario, parameters_json='{"multiplier":"1.50","delay_hours":2}') }))
    result = evaluate(source, spec, factory)
    assert all(run.spec.scenario == spec.scenario for run in factory.runs)
    assert result.scenario.name == scenario
    assert tuple(row.model_dump_json() for row in dataset.observations) == before
    # This tests routing and immutability, NOT scenario economics (owned by Agent 1).


@pytest.mark.parametrize("start,days", [
    (datetime(2026,1,25),14), (datetime(2026,2,25,17),7), (datetime(2026,12,2),30),
])
def test_calendar_boundaries(source, request_spec, start, days):
    spec = BacktestRequest(**(request_spec.model_dump() | {"start":start,"days":days}))
    assert evaluate(source, spec).results[0].history[-1].timestamp == spec.end_exclusive - timedelta(hours=1)


@pytest.mark.parametrize("start", [datetime(2025,12,31),datetime(2026,12,26),datetime(2027,1,1)])
def test_reject_incomplete_windows_before_starting_engine(source, request_spec, start):
    factory = ScriptedFactory()
    with pytest.raises(ValueError, match="outside"):
        evaluate(source, BacktestRequest(**(request_spec.model_dump() | {"start":start})), factory)
    assert not factory.runs


def test_no_current_or_future_row_in_decision_and_prefix_stable(source, dataset, request_spec):
    factories = [ScriptedFactory(), ScriptedFactory()]
    specs = [BacktestRequest(**(request_spec.model_dump() | {"start":datetime(2026,1,3),"days":d})) for d in (7,14)]
    for factory, spec in zip(factories, specs):
        evaluate(source, spec, factory)
        for run in factory.runs:
            assert not hasattr(run.spec, "dataset") and not hasattr(run.spec, "source_path")
            for frame, execution in zip(run.decisions, run.executions):
                index = 48 + frame.step
                assert frame.history == dataset.observations[:index]
                assert frame.timestamp == execution.observation.timestamp
                assert not hasattr(frame, "observation")
                assert frame.history[-1].timestamp == frame.timestamp - timedelta(hours=1)
            with pytest.raises(FrozenInstanceError):
                run.decisions[0].step = 99
    assert factories[0].runs[0].decisions == factories[1].runs[0].decisions[:168]


def test_default_fails_closed_and_test_double_requires_explicit_opt_in(source, request_spec):
    with pytest.raises(SharedEngineUnavailable, match="required"):
        BacktestService(source=source).compare(request_spec)
    with pytest.raises(SharedEngineUnavailable, match="unit-test-only"):
        BacktestService(ScriptedFactory(), source=source).compare(request_spec)


@pytest.mark.parametrize("cap_change", [{"strategies":("STATIC",)}, {"scenarios":("HIGH_WITHDRAWAL",)}])
def test_missing_capabilities_fail_before_run(source, request_spec, cap_change):
    factory = ScriptedFactory()
    factory.capabilities = factory.capabilities.model_copy(update=cap_change)
    with pytest.raises(SharedEngineUnavailable, match="support"):
        evaluate(source, request_spec, factory)
    assert not factory.runs


@pytest.mark.parametrize("fault", ["timestamp","digest","continuity","duplicate","missing","unsafe"])
def test_bad_receipts_fail_and_close_resources(source, request_spec, fault):
    def hook(run, frame, receipt):
        if fault == "duplicate":
            return receipt.model_copy(update={"event_ids":("same",)})
        if frame.step:
            return receipt
        if fault == "timestamp":
            return receipt.model_copy(update={"timestamp":receipt.timestamp + timedelta(hours=1)})
        if fault == "digest":
            return receipt.model_copy(update={"source_digest":"0"*64})
        if fault == "continuity":
            other = state(123)
            return journal(other, timestamp=receipt.timestamp, digest=receipt.source_digest)
        if fault == "missing":
            return receipt.model_copy(update={"event_ids":(), "reserve_breaches":1})
        return receipt.model_copy(update={"realized_interest_cents":9_007_199_254_740_992})
    factory = ScriptedFactory(receipt_hook=hook)
    with pytest.raises((EngineContractError, ValidationError)):
        evaluate(source, request_spec, factory)
    assert len(factory.runs) == 1 and factory.runs[0].closed


@pytest.mark.parametrize("fault", ["conditions","initial"])
def test_invalid_engine_start_is_rejected_and_closed(source, request_spec, fault):
    def hook(run):
        if fault == "conditions":
            run.spec = run.spec.model_copy(update={"seed":999})
        else:
            run.initial_state = state(request_spec.initial_capital_cents + 1)
    factory = ScriptedFactory(start_hook=hook)
    with pytest.raises(EngineContractError):
        evaluate(source, request_spec, factory)
    assert factory.runs[0].closed


def test_provider_reusing_a_session_is_rejected(source, request_spec):
    class Reusing(ScriptedFactory):
        def start(self, spec):
            return self.runs[0] if self.runs else super().start(spec)
    factory = Reusing()
    with pytest.raises(EngineContractError, match="reused"):
        evaluate(source, request_spec, factory)
    assert factory.runs[0].closed


def test_exception_in_decision_closes_session(source, request_spec):
    def start(run):
        def fail(_frame):
            raise RuntimeError("execution unavailable")
        run.decide = fail
    factory = ScriptedFactory(start_hook=start)
    with pytest.raises(RuntimeError, match="unavailable"):
        evaluate(source, request_spec, factory)
    assert factory.runs[0].closed


def test_average_rounding_is_metric_only_half_up(source, request_spec):
    def hook(run, frame, receipt):
        change = 1 if frame.step == 0 else -1 if frame.step == 84 else 0
        return journal(receipt.opening, timestamp=receipt.timestamp, digest=receipt.source_digest,
                       event_ids=(str(frame.step),) if change else (), customer_cash_delta_cents=change)
    result = evaluate(source, request_spec, ScriptedFactory(receipt_hook=hook))
    assert all(m.average_checking_cents == 100_001 and m.net_benefit_cents == 0 for m in result.results)


def test_source_bytes_precision_residuals_and_low_decimal_context_unchanged(request_spec):
    path = Path(__file__).resolve().parents[2] / "treasury_4tier_dataset.csv"
    original = path.read_bytes()
    with localcontext() as ctx:
        ctx.prec = 3
        factory = ScriptedFactory()
        result = BacktestService(factory, allow_test_double=True).compare(request_spec)
    assert path.read_bytes() == original
    assert hashlib.sha256(original).hexdigest() == result.dataset_sha256 == ORGANIZER_SHA256
    dataset = OrganizerDatasetSource().load()
    # Inspect all source fields, including source net_flow; never derive/overwrite it.
    assert factory.runs[0].executions[0].observation.model_dump_json() == dataset.observations[0].model_dump_json()
    assert len(dataset.observations) == 8760
    assert sum(row.net_flow_usd != row.deposits_usd-row.withdrawals_usd for row in dataset.observations) == 2118


def test_noncanonical_source_rejected(source, dataset, request_spec):
    class WrongSource:
        def load(self):
            return dataset.model_copy(update={"metadata":dataset.metadata.model_copy(update={"content_hash":"0"*64})})
    with pytest.raises(ValueError, match="authoritative"):
        evaluate(WrongSource(), request_spec)


@pytest.mark.parametrize("capital", [0, 9_007_199_254_740_991])
def test_zero_and_safe_limit_cash_remain_exact_even_in_average(source, request_spec, capital):
    def no_op(run, frame, receipt):
        return receipt
    spec = BacktestRequest(**(request_spec.model_dump() | {"initial_capital_cents":capital,"days":30}))
    result = evaluate(source, spec, ScriptedFactory(receipt_hook=no_op))
    assert all(m.average_checking_cents == capital and m.net_benefit_cents == 0 for m in result.results)


def test_cumulative_metrics_cannot_overflow_or_be_clamped(source, request_spec):
    maximum = 9_007_199_254_740_991
    def hook(run, frame, receipt):
        return journal(receipt.opening, timestamp=receipt.timestamp, digest=receipt.source_digest,
                       event_ids=(str(frame.step),), customer_cash_delta_cents=maximum,
                       contractual_penalties_cents=maximum)
    factory = ScriptedFactory(receipt_hook=hook)
    with pytest.raises(ValidationError):
        evaluate(source, request_spec, factory)
    assert factory.runs[0].closed


def test_unrealized_interest_is_not_reported_as_realized_income(source, request_spec):
    def hook(run, frame, receipt):
        changes = {"tier1_value_cents":3,"accrued_interest_cents":3} if frame.step == 0 else {}
        return journal(receipt.opening, timestamp=receipt.timestamp, digest=receipt.source_digest,
                       event_ids=("accrual",) if changes else (), stock_changes=changes)
    result = evaluate(source, request_spec, ScriptedFactory(receipt_hook=hook))
    for m in result.results:
        assert m.realized_interest_cents == 0 and m.accrued_interest_cents == 3
        assert m.net_benefit_cents == 3 and m.average_checking_cents == request_spec.initial_capital_cents


@pytest.mark.parametrize("change", [
    {"seed":18}, {"days":14}, {"initial_capital_cents":200_000},
    {"start":datetime(2026,1,2)}, {"policy_json":'{"reserve_fraction":"0.30"}'},
    {"scenario":ScenarioSpec(name="LIQUIDITY_SHOCK")},
    {"scenario":ScenarioSpec(parameters_json='{"scale":"2.00"}')},
])
def test_conditions_hash_binds_all_comparison_inputs(source, request_spec, change):
    baseline = evaluate(source, request_spec)
    modified = evaluate(source, BacktestRequest(**(request_spec.model_dump() | change)))
    assert baseline.conditions_sha256 != modified.conditions_sha256
