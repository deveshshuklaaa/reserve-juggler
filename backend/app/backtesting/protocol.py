"""Proposed injectable boundary for Agent 1; no substitute execution engine."""
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID

from pydantic import Field, model_validator

from app.data.organizer import HourlyObservation
from .contracts import Cash, Contract, Count, EngineState, HourReceipt, Scenario, ScenarioSpec, Strategy


class EngineCapabilities(Contract):
    protocol_version: Literal["hourly-backtest-v1"] = "hourly-backtest-v1"
    engine_version: str = Field(min_length=1)
    integration_sha: str | None
    execution_kind: Literal["SHARED", "TEST_DOUBLE"]
    strategies: tuple[Strategy, ...]
    scenarios: tuple[Scenario, ...]

    @model_validator(mode="after")
    def provenance(self):
        if self.execution_kind == "SHARED" and (
            self.integration_sha is None or len(self.integration_sha) != 40
            or any(c not in "0123456789abcdef" for c in self.integration_sha)
        ):
            raise ValueError("A shared provider must identify its actual integration commit")
        if self.execution_kind == "TEST_DOUBLE" and self.integration_sha is not None:
            raise ValueError("A unit-test double cannot claim a real engine integration SHA")
        if len(set(self.strategies)) != len(self.strategies) or len(set(self.scenarios)) != len(self.scenarios):
            raise ValueError("Capabilities cannot contain duplicates")
        return self


class RunSpec(Contract):
    comparison_id: UUID
    run_id: UUID
    strategy: Strategy
    start: datetime
    end_exclusive: datetime
    steps: Count
    initial_capital_cents: Cash
    seed: Count
    scenario: ScenarioSpec
    policy_json: str
    dataset_id: str
    dataset_sha256: str
    conditions_sha256: str


@dataclass(frozen=True)
class DecisionFrame:
    """Only rows strictly earlier than timestamp. No current/future flow values."""
    step: int
    timestamp: datetime
    history: tuple[HourlyObservation, ...]


@dataclass(frozen=True)
class ExecutionFrame:
    """Current source row becomes visible only after decide() returns."""
    step: int
    observation: HourlyObservation
    source_digest: str


class HourlyRun(Protocol):
    spec: RunSpec
    initial_state: EngineState

    def decide(self, frame: DecisionFrame) -> object:
        """Apply the selected strategy with causal information; return an opaque token."""
        ...

    def execute(self, frame: ExecutionFrame, decision: object) -> HourReceipt:
        """Use the shared ledger/scenario/execution path, not a backtest financial model."""
        ...

    def close(self) -> None:
        """Release resources, including on failure; executor owns transactions/receipts."""
        ...


class HourlyEngineFactory(Protocol):
    capabilities: EngineCapabilities

    def start(self, spec: RunSpec) -> HourlyRun:
        """Create a fresh isolated all-cash, zero-debt run for the supplied strategy."""
        ...
