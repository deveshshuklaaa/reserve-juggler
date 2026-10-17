"""Integration with the *unmodified* 082f019 runtime and its persisted evidence.

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
    PortfolioValuation, SimulationRun, TreasuryDecision,
)
from app.services.hourly_engine import execute_hourly_step
from .contracts import EngineState, HourReceipt
from .protocol import EngineCapabilities
from .service import EngineContractError, SharedEngineUnavailable, observation_digest

RUNTIME_SHA = "082f0190a015298d63583d65a0b216a465b93ce1"
RUNTIME_BLOCKERS = (
    "No shared strategy dispatch for STATIC, REACTIVE, RESERVE_JUGGLER.",
    "get_hourly_forecasts_from_db reads current/future realized source flows.",
    "The first execution is source_start_timestamp + one hour; the first dataset row cannot be executed.",
)
KNOWN_LEDGER_KINDS = frozenset((
    "CUSTOMER_DEPOSIT_INFLOW", "CUSTOMER_WITHDRAWAL_OUTFLOW", "OVERNIGHT_REPO_SWEEP_DEBIT",
    "REPO_MATURITY_CREDIT", "REPO_EARLY_REDEMPTION", "OVERDRAFT_DRAW_BORROW", "OVERDRAFT_REPAYMENT",
))


class RuntimeReceiptUnavailable(EngineContractError):
    """Stored evidence cannot support a complete, reconciled financial receipt."""


class SharedRuntimeFactory:
    """Explicit dependency guard, not three differently named copies of one policy."""
    capabilities = EngineCapabilities(
        engine_version="hourly-runtime-082f019", integration_sha=RUNTIME_SHA,
        execution_kind="SHARED", strategies=(),
        scenarios=("NORMAL","HIGH_WITHDRAWAL","LOW_DEPOSIT","SETTLEMENT_DELAY","LIQUIDITY_SHOCK"),
    )
    blocking_reasons = RUNTIME_BLOCKERS

    def start(self, spec):
        raise SharedEngineUnavailable("Runtime comparison is blocked: " + " ".join(self.blocking_reasons))


def _rows(session, model, run_id, timestamp, *, time_field="occurred_at"):
    return list(session.scalars(select(model).where(
        model.run_id == run_id, getattr(model, time_field) == timestamp)))


def _valuation(session, run_id, timestamp):
    rows = _rows(session, PortfolioValuation, run_id, timestamp, time_field="valued_at")
    if len(rows) != 1:
        raise RuntimeReceiptUnavailable("Exactly one persisted portfolio valuation is required per hour")
    return rows[0]


def _state(valuation):
    # Actual persisted decomposition, not an interest or market-pricing calculation.
    return EngineState(
        checking_cents=valuation.tier0_cash_cents,
        tier1_value_cents=valuation.tier1_value_cents,
        tier2_value_cents=valuation.tier2_market_value_cents,
        tier3_value_cents=valuation.tier3_market_value_cents,
        borrowing_outstanding_cents=valuation.liabilities_cents,
        unpaid_borrowing_costs_cents=0,
        accrued_interest_cents=valuation.tier1_value_cents-valuation.tier1_principal_cents,
        unrealized_market_pnl_cents=0,
        net_asset_value_cents=valuation.net_portfolio_value_cents,
    )


def read_hour_receipt(session: Session, run_id: UUID, step: int) -> HourReceipt:
    """Read one existing hour. Reject unsupported/missing evidence, never post fixes."""
    run = session.get(SimulationRun, run_id)
    if run is None:
        raise KeyError(run_id)
    if type(step) is not int or not 1 <= step <= run.current_step:
        raise ValueError("Receipt step must identify a completed runtime hour")
    timestamp = run.source_start_timestamp + timedelta(hours=step)
    previous = _valuation(session, run.id, timestamp-timedelta(hours=1))
    current = _valuation(session, run.id, timestamp)
    if any(v.tier2_market_value_cents or v.tier3_market_value_cents for v in (previous,current)):
        raise RuntimeReceiptUnavailable("Market asset amounts lack persisted P&L attribution")
    source = session.scalar(select(OrganizerObservation).where(
        OrganizerObservation.dataset_id == run.dataset_id, OrganizerObservation.timestamp == timestamp))
    if source is None:
        raise RuntimeReceiptUnavailable("Missing source observation")
    # Snapshot-only marks do not supply persisted realized/unrealized P&L attribution.
    if any(session.scalar(select(model.id).where(model.run_id == run.id).limit(1)) is not None
           for model in (BondPosition, EquityPosition)):
        raise RuntimeReceiptUnavailable("Bond/equity P&L needs persisted per-position valuation receipts")
    liabilities = list(session.scalars(select(OverdraftLiability).where(OverdraftLiability.run_id == run.id)))
    if any(row.financing_cost_cents is None or row.financing_cost_cents != 0 for row in liabilities):
        raise RuntimeReceiptUnavailable(
            "Financing expense is mutable liability state without hourly cost/payment receipts; NAV omits it")
    ledgers = _rows(session, LedgerEntry, run.id, timestamp, time_field="event_at")
    if not ledgers or any(row.step != step or row.entry_type not in KNOWN_LEDGER_KINDS for row in ledgers):
        raise RuntimeReceiptUnavailable("Missing or unrecognized hourly cash-ledger evidence")
    movements = _rows(session, InvestmentMovement, run.id, timestamp)
    loans = _rows(session, OverdraftMovement, run.id, timestamp)
    breaches = _rows(session, LiquidityBreach, run.id, timestamp)
    decisions = list(session.scalars(select(TreasuryDecision).where(
        TreasuryDecision.run_id == run.id, TreasuryDecision.step == step)))
    if len(decisions) != 1:
        raise RuntimeReceiptUnavailable("Exactly one persisted decision is required")
    decision = decisions[0]
    inflow = sum(r.amount_cents for r in ledgers if r.entry_type == "CUSTOMER_DEPOSIT_INFLOW")
    outflow = sum(r.amount_cents for r in ledgers if r.entry_type == "CUSTOMER_WITHDRAWAL_OUTFLOW")
    if inflow != decision.expected_inflow_cents or outflow != decision.expected_outflow_cents:
        raise RuntimeReceiptUnavailable("Requested customer flow lacks complete settled-payout ledger legs")
    if any(m.kind not in ("INVESTMENT","MATURITY","REDEMPTION") or m.tier != 1
           or m.interest_cents is None or m.haircut_cost_cents is None for m in movements):
        raise RuntimeReceiptUnavailable("Unrecognized or incomplete investment receipt")
    if any(m.kind not in ("BORROW","REPAYMENT") for m in loans):
        raise RuntimeReceiptUnavailable("Unrecognized financing receipt")
    ledger_ids = {row.id for row in ledgers}
    if any(m.ledger_entry_id not in ledger_ids for m in (*movements,*loans)):
        raise RuntimeReceiptUnavailable("Financial movement lacks its same-hour cash ledger")
    initial, closing = _state(previous), _state(current)
    cash = session.scalar(select(CashAccount).where(CashAccount.run_id == run.id))
    if step == run.current_step and (cash is None or cash.balance_cents != closing.checking_cents):
        raise RuntimeReceiptUnavailable("Latest valuation and cash account disagree")
    observation = HourlyObservation(**{name:getattr(source,name) for name in EXPECTED_COLUMNS})
    return HourReceipt(
        timestamp=timestamp, source_digest=observation_digest(observation), opening=initial, closing=closing,
        customer_cash_delta_cents=inflow-outflow,
        investment_cash_delta_cents=sum(m.cash_delta_cents-m.interest_cents+m.haircut_cost_cents for m in movements),
        financing_cash_delta_cents=sum(m.cash_delta_cents for m in loans),
        realized_interest_cents=sum(m.interest_cents for m in movements),
        realized_market_pnl_cents=0,
        contractual_penalties_cents=sum(m.haircut_cost_cents for m in movements),
        liquidation_losses_cents=0, transaction_costs_cents=0,
        borrowing_costs_cents=0, paid_borrowing_costs_cents=0,
        reserve_breaches=len(breaches), emergency_events=len(breaches), failed_payouts=0, unpaid_payouts_cents=0,
        sweeps=sum(m.kind == "INVESTMENT" for m in movements),
        event_ids=tuple(f"{type(row).__name__}:{row.id}" for row in
                        (*ledgers,*movements,*loans,*breaches,decision,current)),
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
        return read_hour_receipt(session, run_id, expected_step+1)
