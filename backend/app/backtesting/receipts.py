"""Backtesting Execution Receipt Adapter for canonical runtime execution v1.

Consumes persisted execution receipts from TreasuryDecision.decision_details_json,
LedgerEntry, InvestmentMovement, OverdraftMovement, Position, and Valuation models
without duplicating the runtime's financial logic.
"""
from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.persistence.models import (
    BondPosition, CashAccount, EquityPosition, InvestmentMovement, LedgerEntry,
    OverdraftLiability, OverdraftMovement, PortfolioValuation, PositionValuation,
    SimulationRun, TreasuryDecision,
)
from .contracts import Cash, Contract, HourReceipt, Money
from .runtime import read_hour_receipt, RuntimeReceiptUnavailable

ExecutionOutcome = Literal["EXECUTED", "PARTIALLY_EXECUTED", "REJECTED", "FAILED", "UNPAID"]
SettlementStatus = Literal["PAID", "PARTIALLY_PAID", "UNPAID"]

DOCUMENTED_RUNTIME_GAPS = (
    "Customer payout instructions are generated from external environment observations rather than strategy recommendations; recommendation_reference is null on payout receipts.",
    "Repo sweeps are managed at the portfolio aggregate level; individual lot position entities are not created for Tier 1.",
    "Market trades are settled instantaneously within the hourly step; deferred T+2 market settlement is not yet supported by runtime cash legs.",
)


class PurchaseReceipt(Contract):
    """Preserves executed quantity, cash spent, fees, position change, and tier."""
    run_id: UUID
    step: int
    recommendation_reference: str | None
    instrument: str
    tier: Literal[1, 2, 3]
    action: str
    status: Literal["EXECUTED", "PARTIALLY_EXECUTED"]
    executed_quantity: str
    price_index: str
    cash_spent_cents: Cash
    principal_cents: Cash
    fee_cents: Cash
    position_id: UUID | str | None
    resulting_position_change: str
    resulting_position_quantity: str | None = None
    movement_id: UUID | str | None = None
    ledger_entry_ids: tuple[str, ...]
    reason: str | None = None


class PartialSaleReceipt(Contract):
    """Preserves requested/executed quantities, gross proceeds, fees, realized P&L, and remaining position.
    Proceeds reflect actual fill rather than entire requested sale.
    """
    run_id: UUID
    step: int
    recommendation_reference: str | None
    instrument: str
    tier: Literal[2, 3]
    action: str
    status: Literal["EXECUTED", "PARTIALLY_EXECUTED"]
    requested_quantity: str | None
    executed_quantity: str
    price_index: str
    requested_amount_cents: Cash | None
    executed_amount_cents: Cash
    gross_proceeds_cents: Cash
    fee_cents: Cash
    liquidation_cost_cents: Cash
    cost_basis_released_cents: Cash
    realized_pnl_cents: Money
    net_cash_proceeds_cents: Cash
    position_id: UUID | str
    remaining_position_quantity: str
    remaining_cost_basis_cents: Cash
    is_partial: bool
    movement_id: UUID | str | None = None
    ledger_entry_ids: tuple[str, ...]
    reason: str | None = None


class RejectedTradeReceipt(Contract):
    """Preserves rejected recommendations without fabricating fills or mutating positions."""
    run_id: UUID
    step: int
    recommendation_reference: str | None
    action: str
    status: Literal["REJECTED"] = "REJECTED"
    requested_amount_cents: Cash | None = 0
    executed_amount_cents: Literal[0] = 0
    reason: str
    ledger_entry_ids: tuple[str, ...] = ()


class PayoutReceipt(Contract):
    """Distinguishes amount due, amount paid, unpaid remainder, overdraft use, and financing costs."""
    run_id: UUID
    step: int
    recommendation_reference: str | None = None
    amount_due_cents: Cash
    amount_paid_cents: Cash
    unpaid_remainder_cents: Cash
    overdraft_draw_cents: Cash
    borrowing_outstanding_cents: Cash
    financing_costs_cents: Cash
    execution_status: Literal["EXECUTED", "PARTIALLY_EXECUTED", "FAILED", "UNPAID"]
    settlement_status: Literal["PAID", "PARTIALLY_PAID", "UNPAID"]
    failure_or_shortfall_reason: str | None
    remaining_financial_liability_cents: Cash
    ledger_entry_ids: tuple[str, ...]
    overdraft_ledger_entry_ids: tuple[str, ...]
    automatic_retry: bool = False


class FinancingReceipt(Contract):
    """Preserves actual overdraft movements and financing costs."""
    movement_id: str
    liability_id: str
    run_id: UUID
    step: int
    kind: Literal["BORROW", "REPAYMENT", "FINANCING_COST"]
    status: Literal["EXECUTED", "ACCRUED"]
    principal_cents: Cash
    financing_cost_cents: Cash
    cash_delta_cents: Money
    outstanding_principal_cents: Cash
    unpaid_financing_cost_cents: Cash
    ledger_entry_id: str | None = None
    reason: str | None = None


class HourlyExecutionBundle(Contract):
    """Reconciled execution bundle for one completed simulation hour."""
    run_id: UUID
    step: int
    timestamp: datetime
    payout: PayoutReceipt
    purchases: tuple[PurchaseReceipt, ...]
    sales: tuple[PartialSaleReceipt, ...]
    rejected_trades: tuple[RejectedTradeReceipt, ...]
    financing: tuple[FinancingReceipt, ...]
    hour_receipt: HourReceipt
    closing_nav_cents: Money
    closing_cash_cents: Cash
    closing_debt_cents: Cash
    documented_gaps: tuple[str, ...] = DOCUMENTED_RUNTIME_GAPS


class ExecutionReceiptAdapter:
    """Consumes canonical persisted runtime receipts and enforces exact financial reconciliation."""

    @classmethod
    def adapt_hour(cls, session: Session, run_id: UUID, step: int) -> HourlyExecutionBundle:
        run = session.get(SimulationRun, run_id)
        if run is None:
            raise KeyError(run_id)
        if type(step) is not int or not 1 <= step <= run.current_step:
            raise ValueError("Receipt step must identify a completed runtime hour")

        decisions = list(session.scalars(select(TreasuryDecision).where(
            TreasuryDecision.run_id == run.id, TreasuryDecision.step == step)))
        if len(decisions) != 1:
            raise RuntimeReceiptUnavailable("Exactly one persisted decision is required")
        decision = decisions[0]
        details = decision.decision_details_json or {}

        # 1. Payout receipt adaptation
        payout_raw = details.get("payout")
        if not payout_raw:
            raise RuntimeReceiptUnavailable("Decision details lack canonical payout receipt")

        payout = PayoutReceipt(
            run_id=run.id,
            step=step,
            recommendation_reference=payout_raw.get("recommendation_reference"),
            amount_due_cents=payout_raw["requested_amount_cents"],
            amount_paid_cents=payout_raw["executed_amount_cents"],
            unpaid_remainder_cents=payout_raw["unpaid_amount_cents"],
            overdraft_draw_cents=payout_raw.get("overdraft_draw_cents", 0),
            borrowing_outstanding_cents=payout_raw.get("borrowing_outstanding_cents", 0),
            financing_costs_cents=payout_raw.get("unpaid_financing_cost_cents", 0),
            execution_status=payout_raw["status"],
            settlement_status=payout_raw.get("settlement_status", "PAID" if payout_raw["unpaid_amount_cents"] == 0 else "PARTIALLY_PAID"),
            failure_or_shortfall_reason=payout_raw.get("reason"),
            remaining_financial_liability_cents=payout_raw.get("remaining_financial_liability_cents", 0),
            ledger_entry_ids=tuple(payout_raw.get("ledger_entry_ids", [])),
            overdraft_ledger_entry_ids=tuple(payout_raw.get("overdraft_ledger_entry_ids", [])),
            automatic_retry=payout_raw.get("automatic_retry", False),
        )

        # 2. Executed orders (Purchases, Partial Sales, Sweeps, Liquidations)
        purchases: list[PurchaseReceipt] = []
        sales: list[PartialSaleReceipt] = []
        orders_executed = details.get("orders_executed", [])

        for order in orders_executed:
            action = order.get("action", "")
            if action in ("BUY_BONDS", "BUY_EQUITIES"):
                tier = 2 if "BONDS" in action else 3
                instrument = "BONDS" if "BONDS" in action else "EQUITIES"
                qty_str = str(order["quantity"])
                pos_model = BondPosition if tier == 2 else EquityPosition
                position = session.get(pos_model, order["position_id"])
                resulting_qty = str(position.quantity) if position else None

                purchases.append(PurchaseReceipt(
                    run_id=run.id,
                    step=step,
                    recommendation_reference=order.get("order_id"),
                    instrument=instrument,
                    tier=tier,
                    action=action,
                    status=order.get("status", "EXECUTED"),
                    executed_quantity=qty_str,
                    price_index=str(order["price_index"]),
                    cash_spent_cents=abs(order["cash_delta_cents"]),
                    principal_cents=order["principal_cents"],
                    fee_cents=order.get("transaction_cost_cents", 0),
                    position_id=order["position_id"],
                    resulting_position_change=qty_str,
                    resulting_position_quantity=resulting_qty,
                    movement_id=order.get("movement_id"),
                    ledger_entry_ids=tuple(order.get("ledger_entry_ids", [])),
                    reason=order.get("reason"),
                ))
            elif action in ("SELL_BONDS", "SELL_EQUITIES"):
                tier = 2 if "BONDS" in action else 3
                instrument = "BONDS" if "BONDS" in action else "EQUITIES"
                pos_model = BondPosition if tier == 2 else EquityPosition
                position = session.get(pos_model, order["position_id"])
                rem_qty = str(position.quantity) if position and position.status == "OPEN" else "0"
                is_part = position is not None and position.status == "OPEN"

                sales.append(PartialSaleReceipt(
                    run_id=run.id,
                    step=step,
                    recommendation_reference=order.get("order_id"),
                    instrument=instrument,
                    tier=tier,
                    action=action,
                    status=order.get("status", "EXECUTED"),
                    requested_quantity=str(order.get("requested_quantity") or order["quantity"]),
                    executed_quantity=str(order["quantity"]),
                    price_index=str(order["price_index"]),
                    requested_amount_cents=order.get("requested_amount_cents", order.get("gross_cents")),
                    executed_amount_cents=order["executed_amount_cents"],
                    gross_proceeds_cents=order["gross_cents"],
                    fee_cents=order.get("transaction_cost_cents", 0),
                    liquidation_cost_cents=order.get("liquidation_cost_cents", 0),
                    cost_basis_released_cents=order["principal_cents"],
                    realized_pnl_cents=order["realized_market_pnl_cents"],
                    net_cash_proceeds_cents=order["cash_delta_cents"],
                    position_id=order["position_id"],
                    remaining_position_quantity=rem_qty,
                    remaining_cost_basis_cents=order.get("remaining_cost_basis_cents", 0),
                    is_partial=is_part,
                    movement_id=order.get("movement_id"),
                    ledger_entry_ids=tuple(order.get("ledger_entry_ids", [])),
                    reason=order.get("reason"),
                ))
            elif action in ("SWEEP", "INVEST_REPO"):
                purchases.append(PurchaseReceipt(
                    run_id=run.id,
                    step=step,
                    recommendation_reference=order.get("order_id"),
                    instrument="OVERNIGHT_REPO",
                    tier=1,
                    action="INVEST_REPO",
                    status="EXECUTED",
                    executed_quantity=str(order.get("amount_cents", 0)),
                    price_index="1.0000",
                    cash_spent_cents=order.get("amount_cents", 0),
                    principal_cents=order.get("amount_cents", 0),
                    fee_cents=0,
                    position_id=None,
                    resulting_position_change=str(order.get("amount_cents", 0)),
                    resulting_position_quantity=str(order.get("amount_cents", 0)),
                    movement_id=None,
                    ledger_entry_ids=(),
                    reason="Excess cash swept to overnight repo",
                ))
            elif action == "EMERGENCY_LIQUIDATION":
                tier = 2 if order.get("instrument") == "BOND" else 3
                sales.append(PartialSaleReceipt(
                    run_id=run.id,
                    step=step,
                    recommendation_reference=None,
                    instrument=order.get("instrument", "BOND"),
                    tier=tier,
                    action=action,
                    status="EXECUTED",
                    requested_quantity=None,
                    executed_quantity="0",
                    price_index="1.0000",
                    requested_amount_cents=order.get("amount_cents", 0),
                    executed_amount_cents=order.get("amount_cents", 0),
                    gross_proceeds_cents=order.get("amount_cents", 0),
                    fee_cents=0,
                    liquidation_cost_cents=0,
                    cost_basis_released_cents=order.get("amount_cents", 0),
                    realized_pnl_cents=0,
                    net_cash_proceeds_cents=order.get("amount_cents", 0),
                    position_id=order.get("position_id"),
                    remaining_position_quantity="0",
                    remaining_cost_basis_cents=0,
                    is_partial=False,
                    movement_id=None,
                    ledger_entry_ids=(),
                    reason="Emergency liquidation for customer payout shortfall",
                ))

        # 3. Rejected orders
        rejected_trades: list[RejectedTradeReceipt] = []
        for rej in details.get("orders_rejected", []):
            rejected_trades.append(RejectedTradeReceipt(
                run_id=run.id,
                step=step,
                recommendation_reference=rej.get("order_id"),
                action=rej.get("action", "UNKNOWN"),
                status="REJECTED",
                requested_amount_cents=rej.get("requested_amount_cents", 0),
                executed_amount_cents=0,
                reason=rej.get("reason", "Trade rejected by runtime"),
            ))

        # 4. Financing receipts
        financing: list[FinancingReceipt] = []
        for f in details.get("financing", []):
            financing.append(FinancingReceipt(
                movement_id=f["movement_id"],
                liability_id=f["liability_id"],
                run_id=run.id,
                step=step,
                kind=f["kind"],
                status=f["status"],
                principal_cents=f["principal_cents"],
                financing_cost_cents=f["financing_cost_cents"],
                cash_delta_cents=f["cash_delta_cents"],
                outstanding_principal_cents=f["outstanding_principal_cents"],
                unpaid_financing_cost_cents=f["unpaid_financing_cost_cents"],
                ledger_entry_id=f.get("ledger_entry_id"),
                reason=f.get("reason"),
            ))

        # 5. Core financial HourReceipt
        hour_receipt = read_hour_receipt(session, run.id, step)

        # 6. Verify full accounting reconciliation across entities
        # A. Payout reconciliation
        if payout.amount_due_cents != payout.amount_paid_cents + payout.unpaid_remainder_cents:
            raise RuntimeReceiptUnavailable("Payout amounts do not reconcile: amount_due != paid + unpaid")

        payout_ledgers = list(session.scalars(select(LedgerEntry).where(
            LedgerEntry.run_id == run.id, LedgerEntry.step == step,
            LedgerEntry.entry_type == "CUSTOMER_WITHDRAWAL_OUTFLOW")))
        if sum(e.amount_cents for e in payout_ledgers) != payout.amount_paid_cents:
            raise RuntimeReceiptUnavailable("Payout cash ledger does not match executed payout amount")

        # B. Purchases reconciliation
        for p in purchases:
            if p.tier in (2, 3):
                if p.cash_spent_cents != p.principal_cents + p.fee_cents:
                    raise RuntimeReceiptUnavailable("Purchase cash spent does not equal principal + fee")

        # C. Partial sales reconciliation
        for s in sales:
            if s.tier in (2, 3):
                if s.gross_proceeds_cents != s.cost_basis_released_cents + s.realized_pnl_cents:
                    raise RuntimeReceiptUnavailable("Sale gross proceeds do not reconcile to released basis + realized P&L")
                if s.net_cash_proceeds_cents != s.gross_proceeds_cents - s.fee_cents - s.liquidation_cost_cents:
                    raise RuntimeReceiptUnavailable("Net sale proceeds do not reconcile to gross - fee - liquidation cost")

        # D. Cash, Debt, NAV reconciliation
        cash_account = session.scalar(select(CashAccount).where(CashAccount.run_id == run.id))
        closing_cash = cash_account.balance_cents if cash_account else hour_receipt.closing.checking_cents
        if closing_cash != hour_receipt.closing.checking_cents:
            raise RuntimeReceiptUnavailable("Closing cash account disagrees with hour receipt closing state")

        closing_debt = hour_receipt.closing.borrowing_outstanding_cents + hour_receipt.closing.unpaid_borrowing_costs_cents
        closing_nav = hour_receipt.closing.net_asset_value_cents

        return HourlyExecutionBundle(
            run_id=run.id,
            step=step,
            timestamp=hour_receipt.timestamp,
            payout=payout,
            purchases=tuple(purchases),
            sales=tuple(sales),
            rejected_trades=tuple(rejected_trades),
            financing=tuple(financing),
            hour_receipt=hour_receipt,
            closing_nav_cents=closing_nav,
            closing_cash_cents=closing_cash,
            closing_debt_cents=closing_debt,
        )
