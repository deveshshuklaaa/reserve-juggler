"""Compare shared-engine runs over one immutable organizer source snapshot."""
import hashlib
import json
from uuid import uuid5

from app.data.organizer import NATIVE_INTERVAL, OrganizerDatasetSource
from .contracts import (
    AccountingMetrics, BacktestRequest, ComparisonResult, EngineState, HistoryPoint, HourReceipt,
    STRATEGIES, StrategyMetrics,
)
from .protocol import DecisionFrame, EngineCapabilities, ExecutionFrame, HourlyEngineFactory, RunSpec

ORGANIZER_SHA256 = "2e7c1d2e5b678e9975250211e7e0017022049c510e1dd90cd7f29e931837b0c5"


class SharedEngineUnavailable(RuntimeError):
    pass


class EngineContractError(ValueError):
    pass


def observation_digest(observation):
    wire = json.dumps(observation.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(wire.encode()).hexdigest()


def conditions_digest(request, metadata, capabilities):
    wire = dict(dataset_sha256=metadata.content_hash, start=request.start.isoformat(),
                end_exclusive=request.end_exclusive.isoformat(), steps=request.steps,
                initial_capital_cents=request.initial_capital_cents, seed=request.seed,
                scenario=request.scenario.model_dump(mode="json"), policy_json=request.policy_json,
                engine_version=capabilities.engine_version, integration_sha=capabilities.integration_sha,
                protocol_version=capabilities.protocol_version)
    return hashlib.sha256(json.dumps(wire, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class BacktestService:
    def __init__(self, engine_factory: HourlyEngineFactory | None = None, *,
                 source: OrganizerDatasetSource | None = None, allow_test_double: bool = False):
        self.engine_factory = engine_factory
        self.source = source if source is not None else OrganizerDatasetSource()
        self.allow_test_double = allow_test_double

    def compare(self, request: BacktestRequest) -> ComparisonResult:
        request = BacktestRequest.model_validate(request)
        if self.engine_factory is None:
            raise SharedEngineUnavailable("Agent 1 shared hourly provider is required; no substitute engine is installed")
        factory = self.engine_factory
        caps = EngineCapabilities.model_validate(factory.capabilities)
        if caps.execution_kind == "TEST_DOUBLE" and not self.allow_test_double:
            raise SharedEngineUnavailable("Test-double performance is unit-test-only; explicitly opt in in tests")
        if not set(STRATEGIES) <= set(caps.strategies) or request.scenario.name not in caps.scenarios:
            raise SharedEngineUnavailable("Provider does not support all requested strategies/scenario")
        dataset = self.source.load()
        if dataset.metadata.content_hash != ORGANIZER_SHA256 or len(dataset) != 8760:
            raise ValueError("Backtesting requires the byte-identical authoritative 8760-row organizer dataset")
        offset = request.start - dataset.metadata.first_timestamp
        start_index = offset // NATIVE_INTERVAL
        if (start_index < 0 or start_index + request.steps > len(dataset)
                or dataset.observations[start_index].timestamp != request.start):
            raise ValueError("Requested complete hourly interval lies outside the organizer source")
        conditions = conditions_digest(request, dataset.metadata, caps)
        metrics = []
        sessions = []  # retain identity until completion to detect a factory reusing run objects
        for strategy in STRATEGIES:
            spec = RunSpec(comparison_id=request.comparison_id, run_id=uuid5(request.comparison_id, strategy),
                strategy=strategy, start=request.start, end_exclusive=request.end_exclusive, steps=request.steps,
                initial_capital_cents=request.initial_capital_cents, seed=request.seed, scenario=request.scenario,
                policy_json=request.policy_json, dataset_id=dataset.metadata.dataset_id,
                dataset_sha256=dataset.metadata.content_hash, conditions_sha256=conditions)
            run = factory.start(spec)
            if any(run is other for other in sessions):
                raise EngineContractError("Factory reused a strategy session instead of an isolated run")
            sessions.append(run)
            try:
                if run.spec != spec:
                    raise EngineContractError("Engine did not accept the identical comparison conditions")
                initial = EngineState.model_validate(run.initial_state)
                if (initial.checking_cents != request.initial_capital_cents
                        or initial.net_asset_value_cents != request.initial_capital_cents
                        or any((initial.tier1_value_cents, initial.tier2_value_cents, initial.tier3_value_cents,
                                initial.borrowing_outstanding_cents, initial.unpaid_borrowing_costs_cents,
                                initial.accrued_interest_cents,
                                initial.unrealized_market_pnl_cents))):
                    raise EngineContractError("Every strategy must start with identical all-cash capital and zero debt")
                metrics.append(self._evaluate(run, spec, dataset, start_index, initial))
            finally:
                run.close()
        return ComparisonResult(comparison_id=request.comparison_id, dataset_id=dataset.metadata.dataset_id,
            dataset_sha256=dataset.metadata.content_hash, start=request.start, end_exclusive=request.end_exclusive,
            steps=request.steps, initial_capital_cents=request.initial_capital_cents, seed=request.seed,
            scenario=request.scenario, policy_json=request.policy_json, conditions_sha256=conditions,
            engine_version=caps.engine_version, engine_integration_sha=caps.integration_sha,
            execution_kind=caps.execution_kind, results=tuple(metrics))

    @staticmethod
    def _evaluate(run, spec, dataset, start_index, initial):
        def receipts():
            for step in range(spec.steps):
                index = start_index + step
                source = dataset.observations[index]
                decision = run.decide(DecisionFrame(step, source.timestamp, dataset.observations[:index]))
                digest = observation_digest(source)
                receipt = HourReceipt.model_validate(run.execute(ExecutionFrame(step, source, digest), decision))
                if receipt.timestamp != source.timestamp or receipt.source_digest != digest:
                    raise EngineContractError("Receipt refers to a different source hour/observation")
                yield receipt
        summary = summarize_receipts(initial, receipts())
        return StrategyMetrics(strategy=spec.strategy, run_id=spec.run_id, **summary.model_dump())


def rounded_mean(total: int, count: int) -> int:
    quotient, remainder = divmod(total, count)
    return quotient + int(2 * remainder >= count)


def summarize_receipts(initial: EngineState, receipts) -> AccountingMetrics:
    """One accounting aggregator for injected executions AND persisted reports."""
    initial = EngineState.model_validate(initial)
    sums = {key:0 for key in (
        "realized_interest_cents", "realized_market_pnl_cents", "contractual_penalties_cents",
        "liquidation_losses_cents", "transaction_costs_cents", "borrowing_costs_cents",
        "customer_cash_delta_cents", "reserve_breaches", "emergency_events", "failed_payouts",
        "unpaid_payouts_cents", "sweeps")}
    history, seen = [], set()
    invested_total = 0
    previous = initial
    for raw in receipts:
        receipt = HourReceipt.model_validate(raw)
        if receipt.opening != previous:
            raise EngineContractError("Hourly accounting state is discontinuous")
        if history and receipt.timestamp-history[-1].timestamp != NATIVE_INTERVAL:
            raise EngineContractError("Accounting history must be contiguous and hourly")
        if seen.intersection(receipt.event_ids):
            raise EngineContractError("Duplicate audit events cannot be counted twice")
        seen.update(receipt.event_ids)
        for key in sums:
            sums[key] += getattr(receipt, key)
        history.append(HistoryPoint(timestamp=receipt.timestamp, checking_cents=receipt.closing.checking_cents))
        previous = receipt.closing
        invested_total += previous.tier1_value_cents + previous.tier2_value_cents + previous.tier3_value_cents
    if not history:
        raise EngineContractError("No executed receipts; metrics are unavailable")
    return AccountingMetrics(**sums,
        average_checking_cents=rounded_mean(sum(p.checking_cents for p in history), len(history)),
        average_invested_cents=rounded_mean(invested_total, len(history)),
        penalties_cents=sums["contractual_penalties_cents"]+sums["liquidation_losses_cents"],
        borrowing_outstanding_cents=previous.borrowing_outstanding_cents,
        unpaid_borrowing_costs_cents=previous.unpaid_borrowing_costs_cents,
        accrued_interest_cents=previous.accrued_interest_cents-initial.accrued_interest_cents,
        unrealized_market_pnl_cents=previous.unrealized_market_pnl_cents-initial.unrealized_market_pnl_cents,
        ending_net_asset_value_cents=previous.net_asset_value_cents,
        net_benefit_cents=previous.net_asset_value_cents-initial.net_asset_value_cents-sums["customer_cash_delta_cents"],
        history=tuple(history))
