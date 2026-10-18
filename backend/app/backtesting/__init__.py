"""Historical comparison orchestration; execution belongs to the shared hourly engine."""

from .contracts import BacktestRequest, ComparisonResult, ScenarioSpec
from .receipts import (
    DOCUMENTED_RUNTIME_GAPS, ExecutionOutcome, ExecutionReceiptAdapter,
    FinancingReceipt, HourlyExecutionBundle, PartialSaleReceipt, PayoutReceipt,
    PurchaseReceipt, RejectedTradeReceipt,
)
from .service import BacktestService, EngineContractError, SharedEngineUnavailable

__all__ = [
    "BacktestRequest", "BacktestService", "ComparisonResult", "ScenarioSpec",
    "EngineContractError", "SharedEngineUnavailable",
    "ExecutionOutcome", "ExecutionReceiptAdapter", "PurchaseReceipt",
    "PartialSaleReceipt", "RejectedTradeReceipt", "PayoutReceipt",
    "FinancingReceipt", "HourlyExecutionBundle", "DOCUMENTED_RUNTIME_GAPS",
]
