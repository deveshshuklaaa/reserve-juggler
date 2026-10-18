"""Unit-test fixture only: canned journal entries, NOT strategies or a simulator.

Entries intentionally do not execute customer flows, repo schedules or market
prices from the CSV. No test result here is historical strategy performance.
"""
from app.backtesting.contracts import EngineState, HourReceipt, SCENARIOS, STRATEGIES
from app.backtesting.protocol import EngineCapabilities

DELTA_KEYS = (
    "customer_cash_delta_cents", "investment_cash_delta_cents", "financing_cash_delta_cents",
    "realized_interest_cents", "realized_market_pnl_cents", "contractual_penalties_cents",
    "liquidation_losses_cents", "transaction_costs_cents", "borrowing_costs_cents",
    "paid_borrowing_costs_cents", "reserve_breaches", "emergency_events", "failed_payouts",
    "unpaid_payouts_cents", "sweeps",
)


def state(cash, **changes):
    fields = dict(checking_cents=cash, tier1_value_cents=0, tier2_value_cents=0, tier3_value_cents=0,
                  borrowing_outstanding_cents=0, unpaid_borrowing_costs_cents=0,
                  accrued_interest_cents=0, unrealized_market_pnl_cents=0)
    fields.update(changes)
    fields["net_asset_value_cents"] = (
        sum(fields[k] for k in ("checking_cents", "tier1_value_cents", "tier2_value_cents", "tier3_value_cents"))
        - fields["borrowing_outstanding_cents"] - fields["unpaid_borrowing_costs_cents"]
    )
    return EngineState(**fields)


def journal(opening, *, timestamp, digest, event_ids=(), stock_changes=None, **deltas):
    """Post explicitly supplied fixture cash legs/stock changes; no price/rate model."""
    entries = dict.fromkeys(DELTA_KEYS, 0)
    entries.update(deltas)
    changes = stock_changes or {}
    fields = opening.model_dump(exclude={"net_asset_value_cents"})
    for key, delta in changes.items():
        fields[key] += delta
    fields["checking_cents"] += (
        entries["customer_cash_delta_cents"] + entries["investment_cash_delta_cents"]
        + entries["financing_cash_delta_cents"] + entries["realized_interest_cents"]
        - entries["contractual_penalties_cents"] - entries["liquidation_losses_cents"]
        - entries["transaction_costs_cents"] - entries["paid_borrowing_costs_cents"]
    )
    fields["borrowing_outstanding_cents"] += entries["financing_cash_delta_cents"]
    fields["unpaid_borrowing_costs_cents"] += entries["borrowing_costs_cents"] - entries["paid_borrowing_costs_cents"]
    closing = state(fields.pop("checking_cents"), **fields)
    return HourReceipt(timestamp=timestamp, source_digest=digest, opening=opening, closing=closing,
                       event_ids=event_ids, **entries)


SCRIPT = (
    dict(customer_cash_delta_cents=40),
    dict(financing_cash_delta_cents=1000, emergency_events=1, reserve_breaches=1),
    dict(investment_cash_delta_cents=-100, stock_changes={"tier1_value_cents":100}, sweeps=1),
    dict(stock_changes={"tier1_value_cents":10, "accrued_interest_cents":10}),
    dict(investment_cash_delta_cents=100, realized_interest_cents=10,
         stock_changes={"tier1_value_cents":-110, "accrued_interest_cents":-10}),
    dict(investment_cash_delta_cents=-100, stock_changes={"tier2_value_cents":100}),
    dict(stock_changes={"tier2_value_cents":20, "unrealized_market_pnl_cents":20}),
    dict(investment_cash_delta_cents=120, realized_market_pnl_cents=20, liquidation_losses_cents=5,
         stock_changes={"tier2_value_cents":-120, "unrealized_market_pnl_cents":-20}),
    dict(borrowing_costs_cents=3),
    dict(paid_borrowing_costs_cents=3),
    dict(contractual_penalties_cents=2, transaction_costs_cents=1, failed_payouts=1, unpaid_payouts_cents=25),
    dict(financing_cash_delta_cents=-600),
    dict(investment_cash_delta_cents=-100, stock_changes={"tier3_value_cents":100}),
    dict(stock_changes={"tier3_value_cents":-10, "unrealized_market_pnl_cents":-10}),
)


class ScriptedRun:
    def __init__(self, spec, owner):
        self.spec, self.owner = spec, owner
        self.initial_state = self.current = state(spec.initial_capital_cents)
        self.decisions, self.executions = [], []
        self.closed = False
        self.token = None

    def decide(self, frame):
        assert not self.closed
        assert len(self.executions) == frame.step
        assert all(row.timestamp < frame.timestamp for row in frame.history)
        self.decisions.append(frame)
        self.token = object()
        return self.token

    def execute(self, frame, decision):
        assert decision is self.token
        assert len(self.decisions) == frame.step + 1  # decision precedes current-row access
        self.executions.append(frame)
        entries = {}
        if not self.owner.receipt_hook and self.spec.strategy == "RESERVE_JUGGLER" and frame.step < len(SCRIPT):
            entries = SCRIPT[frame.step]
        elif not self.owner.receipt_hook and self.spec.strategy == "REACTIVE" and frame.step == 0:
            entries = dict(contractual_penalties_cents=2)
        event_ids = (f"{self.spec.run_id}:{frame.step}",) if entries else ()
        receipt = journal(self.current, timestamp=frame.observation.timestamp, digest=frame.source_digest,
                          event_ids=event_ids, **entries)
        if self.owner.receipt_hook:
            receipt = self.owner.receipt_hook(self, frame, receipt)
        self.current = receipt.closing
        return receipt

    def close(self):
        self.closed = True


class ScriptedFactory:
    capabilities = EngineCapabilities(engine_version="unit-script-v1", integration_sha=None,
        execution_kind="TEST_DOUBLE", strategies=STRATEGIES, scenarios=SCENARIOS)

    def __init__(self, *, receipt_hook=None, start_hook=None):
        self.runs = []
        self.receipt_hook, self.start_hook = receipt_hook, start_hook

    def start(self, spec):
        run = ScriptedRun(spec, self)
        self.runs.append(run)
        if self.start_hook:
            self.start_hook(run)
        return run
