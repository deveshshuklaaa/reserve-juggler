"""Receipt integration with the verified 1ff1e65 financial runtime checkpoint.

No prices, yields, cash flows, strategy actions, or posting amounts are calculated
here. Incomplete receipts are errors, not opportunities to repair the executor.
"""
from datetime import timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data.organizer import EXPECTED_COLUMNS, HourlyObservation
from app.persistence.models import (
    BondPosition, CashAccount, EquityPosition, InvestmentMovement, LedgerEntry,
    LiquidityBreach, OrganizerObservation, OverdraftLiability, OverdraftMovement,
    PortfolioValuation, PositionValuation, SimulationRun, TreasuryDecision,
)
from app.services.hourly_engine import execute_hourly_step
from .contracts import EngineState, HourReceipt
from .protocol import DecisionFrame, EngineCapabilities, ExecutionFrame, HourlyRun, RunSpec
from .service import EngineContractError, SharedEngineUnavailable, observation_digest

RUNTIME_SHA = "43c275c3efaf7ed986d92d732c55583f096ccadf"
RUNTIME_BLOCKERS = (
    "Historical-comparison release gates remain unaccepted; configured sessions enable diagnostic execution only.",
    "Complete 7/14/30-day scenario acceptance and Member 1 availability/optimizer sign-off remain pending.",
    "Legacy public aware start_time remains a wall-clock compatibility selector, not source timezone provenance.",
)
KNOWN_LEDGER_KINDS = frozenset((
    "CUSTOMER_DEPOSIT_INFLOW", "CUSTOMER_WITHDRAWAL_OUTFLOW", "OVERNIGHT_REPO_SWEEP_DEBIT",
    "REPO_MATURITY_CREDIT", "REPO_EARLY_REDEMPTION", "OVERDRAFT_DRAW_BORROW", "OVERDRAFT_REPAYMENT",
    "OVERDRAFT_FINANCING_PAYMENT",
    "MARKET_LIQUIDATION_CREDIT",
    "MARKET_PURCHASE_DEBIT",
    "MARKET_TRANSACTION_FEE",
))


class RuntimeReceiptUnavailable(EngineContractError):
    """Stored evidence cannot support a complete, reconciled financial receipt."""


class PersistedHourlyRun:
    def __init__(self, session: Session, spec: RunSpec, owns_session: bool = False):
        self.session = session
        self.spec = spec
        self.owns_session = owns_session
        self.closed = False
        self.initial_state = EngineState(
            checking_cents=spec.initial_capital_cents,
            tier1_value_cents=0,
            tier2_value_cents=0,
            tier3_value_cents=0,
            borrowing_outstanding_cents=0,
            unpaid_borrowing_costs_cents=0,
            accrued_interest_cents=0,
            unrealized_market_pnl_cents=0,
            net_asset_value_cents=spec.initial_capital_cents,
        )

    def decide(self, frame: DecisionFrame) -> object:
        return {"step": frame.step, "timestamp": frame.timestamp}

    def execute(self, frame: ExecutionFrame, decision: object) -> HourReceipt:
        if self.closed:
            raise EngineContractError("Cannot execute a closed strategy run")
        if type(frame.step) is not int or not 0 <= frame.step < self.spec.steps:
            raise EngineContractError("Execution step must be an in-window integer")
        timestamp = self.spec.start + timedelta(hours=frame.step)
        if (frame.observation.timestamp != timestamp
                or frame.source_digest != observation_digest(frame.observation)
                or decision != {"step": frame.step, "timestamp": timestamp}):
            raise EngineContractError("Execution frame/token does not identify the agreed source hour")
        # Validation and posting must share one savepoint. Never leave a mutated
        # ledger behind when the strict receipt reader rejects the execution.
        with self.session.begin_nested():
            execute_hourly_step(self.session, self.spec.run_id, expected_step=frame.step, strategy=self.spec.strategy)
            receipt = read_hour_receipt(self.session, self.spec.run_id, frame.step + 1)
            if receipt.timestamp != timestamp or receipt.source_digest != frame.source_digest:
                raise EngineContractError("Persisted execution differs from the supplied source observation")
            return receipt

    def close(self) -> None:
        if not self.closed:
            self.closed = True
            if self.owns_session:
                self.session.close()


class SharedRuntimeFactory:
    """Configured shared-engine diagnostic provider, NOT comparison release approval.

    Capabilities describe executable dispatch paths, not H1-H6 acceptance.
    Caller-provided sessions own commit/rollback. Factory-created sessions are
    closed (and uncommitted work rolled back) at run close.
    """
    capabilities = EngineCapabilities(
        engine_version="hourly-runtime-43c275c", integration_sha=RUNTIME_SHA,
        execution_kind="SHARED", strategies=(), scenarios=(),
    )
    blocking_reasons = RUNTIME_BLOCKERS

    def __init__(self, session: Session | None = None, session_factory=None):
        self.session = session
        self.session_factory = session_factory
        if session is not None or session_factory is not None:
            self.capabilities = EngineCapabilities(
                engine_version="hourly-runtime-43c275c", integration_sha=RUNTIME_SHA,
                execution_kind="SHARED", strategies=("STATIC", "REACTIVE", "RESERVE_JUGGLER"),
                scenarios=("NORMAL", "HIGH_WITHDRAWAL", "LOW_DEPOSIT", "SETTLEMENT_DELAY", "LIQUIDITY_SHOCK"),
            )
            self.blocking_reasons = RUNTIME_BLOCKERS
        else:
            self.blocking_reasons = RUNTIME_BLOCKERS

    def start(self, spec: RunSpec) -> HourlyRun:
        if self.session is None and self.session_factory is None:
            raise SharedEngineUnavailable("Shared runtime is blocked: runtime unconfigured")
        import json
        from app.services.run_service import create_simulation_run, apply_simulation_scenario
        from app.v1_contracts import CreateRunRequest, ScenarioRequest, TreasuryPolicy

        policy_dict = json.loads(spec.policy_json)
        # Reuse the shared scenario scheduler; never implement scenario cash
        # arithmetic here or silently drop a schedule from comparison conditions.
        schedule = policy_dict.get("scenarios", [])
        if not isinstance(schedule, list):
            raise EngineContractError("Scenario schedule must be a list")
        scenario_requests = [ScenarioRequest.model_validate(event) for event in schedule]
        if spec.scenario.name != "NORMAL" or spec.scenario.parameters_json != "{}":
            initial_scenario = ScenarioRequest(
                scenario=spec.scenario.name, parameters=json.loads(spec.scenario.parameters_json), effective_step=1)
            # An exact copy in the persisted schedule is the same event, not a
            # second shock. Conflicting step-one settings remain an error.
            if initial_scenario not in scenario_requests:
                scenario_requests.insert(0, initial_scenario)
        steps = [event.effective_step for event in scenario_requests]
        if any(step is None or not 1 <= step <= spec.steps for step in steps) or len(set(steps)) != len(steps):
            raise EngineContractError("Scenario schedule needs unique in-window explicit effective steps")
        policy_for_model = {k: v for k, v in policy_dict.items() if k not in ("scenarios", "scenario_parameters", "strategy")}
        policy_obj = TreasuryPolicy.model_validate(policy_for_model) if policy_for_model else TreasuryPolicy()
        create_req = CreateRunRequest(
            initial_cash_cents=spec.initial_capital_cents,
            duration_steps=spec.steps,
            seed=spec.seed,
            scenario=spec.scenario.name,
            policy=policy_obj,
        )
        owns_session = self.session is None
        session = self.session_factory() if owns_session else self.session
        try:
            if session.get(SimulationRun, spec.run_id) is not None:
                raise EngineContractError("Strategy run ID already exists; use a fresh comparison ID, never reuse a mutated ledger")
            with session.begin_nested():
                create_simulation_run(session, create_req, run_id=spec.run_id, source_start_timestamp=spec.start)
                created = session.get(SimulationRun, spec.run_id)
                if (created.dataset_id != spec.dataset_id or created.source_start_timestamp != spec.start
                        or created.native_interval_seconds != 3600):
                    raise EngineContractError("Shared run creation did not preserve requested source/time conditions")
                for event in sorted(scenario_requests, key=lambda item: item.effective_step):
                    apply_simulation_scenario(session, spec.run_id, event)
                session.flush()
            return PersistedHourlyRun(session, spec, owns_session=owns_session)
        except Exception:
            if owns_session:
                session.close()
            raise


def _rows(session, model, run_id, timestamp, *, time_field="occurred_at"):
    return list(session.scalars(select(model).where(
        model.run_id == run_id, getattr(model, time_field) == timestamp)))


def _valuation(session, run_id, timestamp):
    rows = _rows(session, PortfolioValuation, run_id, timestamp, time_field="valued_at")
    if len(rows) != 1:
        raise RuntimeReceiptUnavailable("Exactly one persisted portfolio valuation is required per hour")
    return rows[0]


def _state(session, run_id, valuation):
    pos_vals = session.execute(
        select(PositionValuation.unrealized_pnl_cents).where(
            PositionValuation.run_id == run_id, PositionValuation.valued_at == valuation.valued_at
        )
    ).scalars().all()
    unrealized_mkt_pnl = sum(pos_vals)

    loans_rows = session.execute(
        select(
            OverdraftMovement.kind,
            OverdraftMovement.cash_delta_cents,
            OverdraftMovement.financing_cost_cents,
            OverdraftMovement.principal_cents,
        ).where(
            OverdraftMovement.run_id == run_id,
            OverdraftMovement.occurred_at < valuation.valued_at,
        )
    ).all()
    borrowing_principal = sum(row[3] if row[0] == "BORROW" else -row[3]
                              for row in loans_rows if row[0] in ("BORROW", "REPAYMENT"))
    unpaid_costs = (sum(row[2] for row in loans_rows if row[0] == "FINANCING_COST")
                    - sum(row[2] for row in loans_rows if row[0] == "REPAYMENT"))

    return EngineState(
        checking_cents=valuation.tier0_cash_cents,
        tier1_value_cents=valuation.tier1_value_cents,
        tier2_value_cents=valuation.tier2_market_value_cents,
        tier3_value_cents=valuation.tier3_market_value_cents,
        borrowing_outstanding_cents=borrowing_principal,
        unpaid_borrowing_costs_cents=unpaid_costs,
        accrued_interest_cents=valuation.tier1_value_cents - valuation.tier1_principal_cents,
        unrealized_market_pnl_cents=unrealized_mkt_pnl,
        net_asset_value_cents=valuation.net_portfolio_value_cents,
    )


def read_hour_receipt(session: Session, run_id: UUID, step: int) -> HourReceipt:
    """Read one existing hour. Reject unsupported/missing evidence, never post fixes."""
    run = session.get(SimulationRun, run_id)
    if run is None:
        raise KeyError(run_id)
    if type(step) is not int or not 1 <= step <= run.current_step:
        raise ValueError("Receipt step must identify a completed runtime hour")
    source_timestamp = run.source_start_timestamp + timedelta(hours=step - 1)
    close_timestamp = run.source_start_timestamp + timedelta(hours=step)
    previous = _valuation(session, run.id, close_timestamp - timedelta(hours=1))
    current = _valuation(session, run.id, close_timestamp)

    source = session.scalar(select(OrganizerObservation).where(
        OrganizerObservation.dataset_id == run.dataset_id, OrganizerObservation.timestamp == source_timestamp))
    if source is None:
        raise RuntimeReceiptUnavailable("Missing source observation")

    pos_vals_curr = list(session.scalars(select(PositionValuation).where(
        PositionValuation.run_id == run.id, PositionValuation.valued_at == current.valued_at)))
    has_open_market = any(session.scalar(select(model.id).where(
        model.run_id == run.id, model.status == "OPEN").limit(1)) is not None
        for model in (BondPosition, EquityPosition))
    if has_open_market and not pos_vals_curr:
        raise RuntimeReceiptUnavailable("Bond/equity P&L needs persisted per-position valuation receipts")

    ledgers = list(session.scalars(select(LedgerEntry).where(
        LedgerEntry.run_id == run.id, LedgerEntry.step == step, LedgerEntry.event_at == source_timestamp)))
    movements = _rows(session, InvestmentMovement, run.id, source_timestamp)
    loans = _rows(session, OverdraftMovement, run.id, source_timestamp)
    breaches = _rows(session, LiquidityBreach, run.id, source_timestamp)
    decisions = list(session.scalars(select(TreasuryDecision).where(
        TreasuryDecision.run_id == run.id, TreasuryDecision.step == step)))
    if len(decisions) != 1:
        raise RuntimeReceiptUnavailable("Exactly one persisted decision is required")
    decision = decisions[0]

    payout_info = decision.decision_details_json.get("payout") if decision.decision_details_json else None
    if payout_info is not None:
        expected_paid_outflow = payout_info.get("executed_amount_cents", decision.expected_outflow_cents)
        unpaid_payout_amount = payout_info.get("unpaid_amount_cents", 0)
        payout_status = payout_info.get("status")
        failed_count = 1 if (payout_status in ("FAILED", "PARTIALLY_EXECUTED") or unpaid_payout_amount > 0) else 0
    else:
        expected_paid_outflow = decision.expected_outflow_cents
        unpaid_payout_amount = 0
        failed_count = 0

    expected_cash_legs = (
        decision.expected_inflow_cents > 0
        or expected_paid_outflow > 0
        or len(movements) > 0
        or len(loans) > 0
    )
    if (expected_cash_legs and not ledgers) or any(row.step != step or row.entry_type not in KNOWN_LEDGER_KINDS for row in ledgers):
        raise RuntimeReceiptUnavailable("Missing or unrecognized hourly cash-ledger evidence")

    inflow = sum(r.amount_cents for r in ledgers if r.entry_type == "CUSTOMER_DEPOSIT_INFLOW")
    outflow = sum(r.amount_cents for r in ledgers if r.entry_type == "CUSTOMER_WITHDRAWAL_OUTFLOW")
    if inflow != decision.expected_inflow_cents or outflow != expected_paid_outflow:
        raise RuntimeReceiptUnavailable("Requested customer flow lacks complete settled-payout ledger legs")

    if any((m.tier == 1 and m.kind not in ("INVESTMENT", "MATURITY", "REDEMPTION"))
           or (m.tier in (2, 3) and m.kind not in ("INVESTMENT", "LIQUIDATION"))
           or m.tier not in (1, 2, 3)
           or m.interest_cents is None or m.haircut_cost_cents is None for m in movements):
        raise RuntimeReceiptUnavailable("Unrecognized or incomplete investment receipt")
    if any(m.kind not in ("BORROW", "REPAYMENT", "FINANCING_COST") for m in loans):
        raise RuntimeReceiptUnavailable("Unrecognized financing receipt")

    ledger_ids = {row.id for row in ledgers}
    for m in movements:
        if m.ledger_entry_id not in ledger_ids:
            raise RuntimeReceiptUnavailable("Financial movement lacks its same-hour cash ledger")
    for m in loans:
        expected_cash = (m.principal_cents if m.kind == "BORROW" else
                         -(m.principal_cents + m.financing_cost_cents) if m.kind == "REPAYMENT" else 0)
        if (m.cash_delta_cents != expected_cash
                or (m.kind == "BORROW" and m.financing_cost_cents != 0)
                or (m.kind == "FINANCING_COST" and m.principal_cents != 0)):
            raise RuntimeReceiptUnavailable("Financing principal, paid expense and cash legs disagree")
        if m.kind in ("BORROW", "REPAYMENT") and m.ledger_entry_id not in ledger_ids:
            raise RuntimeReceiptUnavailable("Financial movement lacks its same-hour cash ledger")
        if m.kind in ("BORROW", "REPAYMENT"):
            ledger = next(row for row in ledgers if row.id == m.ledger_entry_id)
            if ledger.amount_cents != abs(expected_cash) or ledger.balance_after_cents - ledger.balance_before_cents != expected_cash:
                raise RuntimeReceiptUnavailable("Financing movement does not match its cash-ledger amount/direction")
        if m.kind == "FINANCING_COST" and m.cash_delta_cents != 0:
            raise RuntimeReceiptUnavailable("Financing cost movement must have zero cash delta")

    initial, closing = _state(session, run.id, previous), _state(session, run.id, current)
    cash = session.scalar(select(CashAccount).where(CashAccount.run_id == run.id))
    if step == run.current_step and (cash is None or cash.balance_cents != closing.checking_cents):
        raise RuntimeReceiptUnavailable("Latest valuation and cash account disagree")

    borrowing_costs = sum(m.financing_cost_cents for m in loans if m.kind == "FINANCING_COST")
    paid_borrowing_costs = sum(m.financing_cost_cents for m in loans if m.kind == "REPAYMENT")
    financing_cash_delta = sum(m.principal_cents if m.kind == "BORROW" else -m.principal_cents
                               for m in loans if m.kind in ("BORROW", "REPAYMENT"))
    realized_mkt_pnl = sum(pv.realized_pnl_cents for pv in pos_vals_curr)
    tx_costs = sum(r.amount_cents for r in ledgers if r.entry_type == "MARKET_TRANSACTION_FEE")

    observation = HourlyObservation(**{name: getattr(source, name) for name in EXPECTED_COLUMNS})
    return HourReceipt(
        timestamp=source_timestamp, source_digest=observation_digest(observation), opening=initial, closing=closing,
        customer_cash_delta_cents=inflow - outflow,
        investment_cash_delta_cents=sum(m.cash_delta_cents - m.interest_cents + m.haircut_cost_cents for m in movements),
        financing_cash_delta_cents=financing_cash_delta,
        realized_interest_cents=sum(m.interest_cents for m in movements),
        realized_market_pnl_cents=realized_mkt_pnl,
        contractual_penalties_cents=sum(m.haircut_cost_cents for m in movements if m.tier == 1),
        liquidation_losses_cents=sum(m.haircut_cost_cents for m in movements if m.tier in (2, 3)),
        transaction_costs_cents=tx_costs,
        borrowing_costs_cents=borrowing_costs, paid_borrowing_costs_cents=paid_borrowing_costs,
        reserve_breaches=len(breaches), emergency_events=len(breaches),
        failed_payouts=failed_count, unpaid_payouts_cents=unpaid_payout_amount,
        sweeps=sum(m.kind == "INVESTMENT" for m in movements),
        event_ids=tuple(f"{type(row).__name__}:{row.id}" for row in
                        (*ledgers, *movements, *loans, *breaches, decision, current, *pos_vals_curr)),
    )


def execute_persisted_hour(session: Session, run_id: UUID, expected_step: int) -> HourReceipt:
    """Execute the shared engine atomically with strict receipt validation.

    A validation failure rolls back this step's savepoint. The caller still owns
    the outer transaction. StepConflictError propagates unchanged.
    """
    if type(expected_step) is not int or expected_step < 0:
        raise ValueError("expected_step must be a nonnegative integer")
    with session.begin_nested():
        execute_hourly_step(session, run_id, expected_step=expected_step)
        return read_hour_receipt(session, run_id, expected_step + 1)


def make_shared_runtime_factory() -> SharedRuntimeFactory:
    from app.database import SessionLocal
    return SharedRuntimeFactory(session_factory=SessionLocal)


