"""Shared hourly execution engine for live simulations and strategy backtests.

Accounts separately for:
- Tier 0 checking cash
- Tier 1 overnight repo (17:00 sweep window, 08:00 maturity, 50 bps early break penalty)
- Tier 2 sovereign bond mark-to-market valuation (200 bps liquidation haircut)
- Tier 3 growth equity mark-to-market valuation (1500 bps emergency slippage)
- Emergency overdraft liability (1000 bps APR financing cost)

Integrates Member 1's canonical four-tier liquidity risk engine and optimizer recommendations.
Zero floats: all financial balances and valuations are strict integer cents.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.persistence.models import (
    BondPosition as DbBondPosition,
    CashAccount as DbCashAccount,
    EquityPosition as DbEquityPosition,
    InvestmentMovement as DbInvestmentMovement,
    LedgerEntry as DbLedgerEntry,
    LiquidityBreach as DbLiquidityBreach,
    OrganizerObservation as DbOrganizerObservation,
    OverdraftLiability as DbOverdraftLiability,
    OverdraftMovement as DbOverdraftMovement,
    PortfolioValuation as DbPortfolioValuation,
    PositionValuation as DbPositionValuation,
    RepoPosition as DbRepoPosition,
    SimulationRun as DbSimulationRun,
    TreasuryDecision as DbTreasuryDecision,
)
from app.services.treasury_adapter import (
    build_four_tier_policy,
    evaluate_liquidity_risk,
    get_hourly_forecasts_from_db,
    get_information_cutoff,
    hydrate_portfolio_state,
    recommend_four_tier_allocation_decision,
)

STRATEGY_STATIC = "STATIC"
STRATEGY_REACTIVE = "REACTIVE"
STRATEGY_RESERVE_JUGGLER = "RESERVE_JUGGLER"

CANONICAL_STRATEGIES = {
    "STATIC": STRATEGY_STATIC,
    "STATIC_RESERVE": STRATEGY_STATIC,
    "REACTIVE": STRATEGY_REACTIVE,
    "REACTIVE_RESERVE": STRATEGY_REACTIVE,
    "RESERVE_JUGGLER": STRATEGY_RESERVE_JUGGLER,
}


def normalize_strategy_id(strategy_name: str | None) -> str:
    """Normalizes strategy identifier to canonical ID: STATIC, REACTIVE, or RESERVE_JUGGLER.
    
    Accepts both canonical frontend IDs and legacy aliases.
    """
    if not strategy_name:
        return STRATEGY_RESERVE_JUGGLER
    key = str(strategy_name).strip().upper()
    if key in CANONICAL_STRATEGIES:
        return CANONICAL_STRATEGIES[key]
    raise ValueError(
        f"Unknown strategy '{strategy_name}'. Expected one of: STATIC, REACTIVE, RESERVE_JUGGLER "
        f"(or legacy aliases STATIC_RESERVE, REACTIVE_RESERVE)"
    )


class StepConflictError(Exception):
    """Raised when expected_step conflicts with current simulation step."""
    def __init__(self, expected_step: int, current_step: int):
        self.expected_step = expected_step
        self.current_step = current_step
        super().__init__(
            f"Expected step {expected_step} conflicts with current step {current_step}"
        )


def get_active_scenario(run: DbSimulationRun, target_step: int) -> dict[str, Any]:
    """Resolves active scenario and parameters for the target step."""
    policy_json = run.policy_json or {}
    scenarios_list = policy_json.get("scenarios", [])
    
    active = {
        "scenario": run.scenario or "NORMAL",
        "parameters": {},
        "effective_step": 0,
    }
    
    for event in scenarios_list:
        eff_step = event.get("effective_step", 0)
        if eff_step <= target_step:
            active = event
            
    return active


def execute_hourly_step(
    session: Session,
    run_id: UUID,
    expected_step: int | None = None,
    strategy: str | None = None,
) -> dict[str, Any]:
    """Executes exactly one hour of the simulation.
    
    Shared by live simulation advance and backtesting engines.
    """
    run = session.scalar(select(DbSimulationRun).where(DbSimulationRun.id == run_id))
    if run is None:
        raise KeyError(f"Simulation run {run_id} not found")

    if expected_step is not None and run.current_step != expected_step:
        raise StepConflictError(expected_step=expected_step, current_step=run.current_step)

    target_step = run.current_step + 1
    source_observation_timestamp = run.source_start_timestamp + timedelta(hours=run.current_step)
    target_timestamp = run.source_start_timestamp + timedelta(hours=target_step)

    observation = session.scalar(
        select(DbOrganizerObservation).where(
            DbOrganizerObservation.dataset_id == run.dataset_id,
            DbOrganizerObservation.timestamp == source_observation_timestamp,
        )
    )
    if observation is None:
        raise RuntimeError(
            f"Observation for dataset {run.dataset_id} at step {target_step} ({source_observation_timestamp}) not found"
        )

    # 1. Hydrate current portfolio
    (
        portfolio,
        cash_acc,
        db_repos,
        db_bonds,
        db_equities,
        db_overdrafts,
    ) = hydrate_portfolio_state(session, run, observation)

    policy_dict = run.policy_json or {}
    policy_obj = build_four_tier_policy(
        policy_dict,
        repo_sweep_window_open=(observation.timestamp.hour == 17),
    )

    action_decision = "HOLD"
    decision_amount = 0
    decision_explanations: list[str] = []
    executed_decision = True
    orders_executed: list[dict[str, Any]] = []

    # 2. Check 08:00 Repo Maturity
    if observation.timestamp.hour == 8:
        active_repos = [r for r in db_repos if r.status in ("ACTIVE", "LOCKED")]
        for r in active_repos:
            repo_rate = observation.tier1_repo_rate_apy if observation else Decimal("5.25")
            interest_cents = int(
                r.principal_cents * (repo_rate / Decimal("100")) * Decimal(15) / Decimal(8760)
            )
            total_credit = r.principal_cents + interest_cents
            pre_bal = cash_acc.balance_cents
            cash_acc.balance_cents += total_credit
            r.status = "MATURED"

            mat_ledger = DbLedgerEntry(
                id=uuid4(),
                run_id=run.id,
                step=target_step,
                timestamp=None,
                entry_type="REPO_MATURITY_CREDIT",
                amount_cents=total_credit,
                balance_before_cents=pre_bal,
                balance_after_cents=cash_acc.balance_cents,
                reference_id=f"REPO-MATURITY-{r.id}",
                source_type=run.source_type,
                dataset_id=run.dataset_id,
                source_observation_timestamp=observation.timestamp,
                event_at=observation.timestamp,
            )
            session.add(mat_ledger)
            session.flush()

            session.add(
                DbInvestmentMovement(
                    id=uuid4(),
                    run_id=run.id,
                    tier=1,
                    repo_position_id=r.id,
                    kind="MATURITY",
                    occurred_at=observation.timestamp,
                    cash_delta_cents=total_credit,
                    principal_cents=r.principal_cents,
                    interest_cents=interest_cents,
                    haircut_cost_cents=0,
                    ledger_entry_id=mat_ledger.id,
                    reference_id=f"mov-mat-{r.id}",
                    source_type=run.source_type,
                    dataset_id=run.dataset_id,
                    source_observation_timestamp=observation.timestamp,
                )
            )
            action_decision = "WITHDRAW"
            decision_amount += total_credit
            decision_explanations.append(
                f"Matured repo {r.id} principal {r.principal_cents} + {interest_cents} interest credited."
            )
            orders_executed.append({
                "instrument": "OVERNIGHT_REPO",
                "action": "REDEEM_REPO",
                "amount_cents": total_credit,
            })

    # 3. Apply customer cash flows with scenario adjustments
    scenario_info = get_active_scenario(run, target_step)
    scen_name = scenario_info.get("scenario", "NORMAL")
    scen_params = scenario_info.get("parameters", {})

    inflow_multiplier = Decimal("1.0")
    outflow_multiplier = Decimal("1.0")
    extra_outflow_cents = 0

    if scen_name == "HIGH_WITHDRAWAL":
        outflow_multiplier = Decimal(str(scen_params.get("multiplier", 1.5)))
    elif scen_name == "LOW_DEPOSIT":
        inflow_multiplier = Decimal(str(scen_params.get("multiplier", 0.5)))
    elif scen_name == "SETTLEMENT_DELAY":
        inflow_multiplier = Decimal("0.0")
    elif scen_name == "LIQUIDITY_SHOCK":
        extra_outflow_cents = int(scen_params.get("amount_cents", scen_params.get("shock_cents", 500000000)))

    deposits_cents = int(round(observation.deposits_usd * 100))
    withdrawals_cents = int(round(observation.withdrawals_usd * 100))
    inflow_cents = int(Decimal(deposits_cents) * inflow_multiplier)
    outflow_cents = int(Decimal(withdrawals_cents) * outflow_multiplier) + extra_outflow_cents

    # Customer Inflow
    if inflow_cents > 0:
        pre_in = cash_acc.balance_cents
        cash_acc.balance_cents += inflow_cents
        session.add(
            DbLedgerEntry(
                id=uuid4(),
                run_id=run.id,
                step=target_step,
                timestamp=None,
                entry_type="CUSTOMER_DEPOSIT_INFLOW",
                amount_cents=inflow_cents,
                balance_before_cents=pre_in,
                balance_after_cents=cash_acc.balance_cents,
                reference_id=f"FLOW-IN-{target_step}",
                source_type=run.source_type,
                dataset_id=run.dataset_id,
                source_observation_timestamp=observation.timestamp,
                event_at=observation.timestamp,
            )
        )

    # Customer Outflow
    pre_out = cash_acc.balance_cents
    if cash_acc.balance_cents >= outflow_cents:
        cash_acc.balance_cents -= outflow_cents
        session.add(
            DbLedgerEntry(
                id=uuid4(),
                run_id=run.id,
                step=target_step,
                timestamp=None,
                entry_type="CUSTOMER_WITHDRAWAL_OUTFLOW",
                amount_cents=outflow_cents,
                balance_before_cents=pre_out,
                balance_after_cents=cash_acc.balance_cents,
                reference_id=f"FLOW-OUT-{target_step}",
                source_type=run.source_type,
                dataset_id=run.dataset_id,
                source_observation_timestamp=observation.timestamp,
                event_at=observation.timestamp,
            )
        )
    else:
        # Cash deficit!
        cash_shortfall = outflow_cents - cash_acc.balance_cents
        paid_from_cash = cash_acc.balance_cents
        cash_acc.balance_cents = 0

        if paid_from_cash > 0:
            session.add(
                DbLedgerEntry(
                    id=uuid4(),
                    run_id=run.id,
                    step=target_step,
                    timestamp=None,
                    entry_type="CUSTOMER_WITHDRAWAL_OUTFLOW",
                    amount_cents=paid_from_cash,
                    balance_before_cents=pre_out,
                    balance_after_cents=0,
                    reference_id=f"FLOW-OUT-PARTIAL-{target_step}",
                    source_type=run.source_type,
                    dataset_id=run.dataset_id,
                    source_observation_timestamp=observation.timestamp,
                    event_at=observation.timestamp,
                )
            )

        # Early repo break check
        if policy_obj.allow_early_repo_redemption and cash_shortfall > 0:
            active_repos = [r for r in db_repos if r.status in ("ACTIVE", "LOCKED")]
            for r in active_repos:
                if cash_shortfall <= 0:
                    break
                haircut = r.early_redemption_haircut_pct if r.early_redemption_haircut_pct is not None else Decimal("0.50")
                penalty = int(r.principal_cents * (haircut / Decimal("100")))
                recoverable = max(0, r.principal_cents - penalty)
                use_amount = min(cash_shortfall, recoverable)
                r.status = "REDEEMED"
                r.early_redemption_at = observation.timestamp
                r.early_redemption_cost_cents = penalty
                r.proceeds_returned_cents = recoverable
                cash_shortfall -= use_amount

                cash_before_redemption = cash_acc.balance_cents
                cash_acc.balance_cents += recoverable

                early_ledger = DbLedgerEntry(
                    id=uuid4(),
                    run_id=run.id,
                    step=target_step,
                    timestamp=None,
                    entry_type="REPO_EARLY_REDEMPTION",
                    amount_cents=recoverable,
                    balance_before_cents=cash_before_redemption,
                    balance_after_cents=cash_acc.balance_cents,
                    reference_id=f"REPO-EARLY-{r.id}",
                    source_type=run.source_type,
                    dataset_id=run.dataset_id,
                    source_observation_timestamp=observation.timestamp,
                    event_at=observation.timestamp,
                )
                session.add(early_ledger)
                session.flush()

                session.add(
                    DbInvestmentMovement(
                        id=uuid4(),
                        run_id=run.id,
                        tier=1,
                        repo_position_id=r.id,
                        kind="REDEMPTION",
                        occurred_at=observation.timestamp,
                        cash_delta_cents=recoverable,
                        principal_cents=r.principal_cents,
                        interest_cents=0,
                        haircut_cost_cents=penalty,
                        ledger_entry_id=early_ledger.id,
                        reference_id=f"mov-early-{r.id}",
                        source_type=run.source_type,
                        dataset_id=run.dataset_id,
                        source_observation_timestamp=observation.timestamp,
                    )
                )

                cash_before_payout = cash_acc.balance_cents
                cash_acc.balance_cents -= use_amount
                session.add(
                    DbLedgerEntry(
                        id=uuid4(),
                        run_id=run.id,
                        step=target_step,
                        timestamp=None,
                        entry_type="CUSTOMER_WITHDRAWAL_OUTFLOW",
                        amount_cents=use_amount,
                        balance_before_cents=cash_before_payout,
                        balance_after_cents=cash_acc.balance_cents,
                        reference_id=f"FLOW-OUT-REPO-{target_step}-{r.id}",
                        source_type=run.source_type,
                        dataset_id=run.dataset_id,
                        source_observation_timestamp=observation.timestamp,
                        event_at=observation.timestamp,
                    )
                )

        if cash_shortfall > 0:
            # Overdraft draw
            breach_ref = f"breach-{run.id}-{target_step}"
            breach = DbLiquidityBreach(
                id=uuid4(),
                run_id=run.id,
                source_type=run.source_type,
                dataset_id=run.dataset_id,
                source_observation_timestamp=observation.timestamp,
                occurred_at=observation.timestamp,
                shortfall_cents=cash_shortfall,
                description=f"Negative cash drain of {cash_shortfall} cents; triggered overdraft.",
                reference_id=breach_ref,
            )
            session.add(breach)
            session.flush()

            od_ref = f"overdraft-{run.id}-{target_step}"
            od_liability = DbOverdraftLiability(
                id=uuid4(),
                run_id=run.id,
                source_type=run.source_type,
                dataset_id=run.dataset_id,
                source_observation_timestamp=observation.timestamp,
                borrowed_at=observation.timestamp,
                borrowed_cents=cash_shortfall,
                outstanding_principal_cents=cash_shortfall,
                repaid_principal_cents=0,
                apr_pct=observation.emergency_overdraft_penalty_apr_pct if observation else Decimal("10.0"),
                financing_cost_cents=0,
                breach_id=breach.id,
                reference_id=od_ref,
            )
            session.add(od_liability)
            session.flush()

            cash_before_borrow = cash_acc.balance_cents
            cash_acc.balance_cents += cash_shortfall

            od_ledger = DbLedgerEntry(
                id=uuid4(),
                run_id=run.id,
                step=target_step,
                timestamp=None,
                entry_type="OVERDRAFT_DRAW_BORROW",
                amount_cents=cash_shortfall,
                balance_before_cents=cash_before_borrow,
                balance_after_cents=cash_acc.balance_cents,
                reference_id=f"OD-DRAW-{target_step}",
                source_type=run.source_type,
                dataset_id=run.dataset_id,
                source_observation_timestamp=observation.timestamp,
                event_at=observation.timestamp,
            )
            session.add(od_ledger)
            session.flush()

            session.add(
                DbOverdraftMovement(
                    id=uuid4(),
                    run_id=run.id,
                    liability_id=od_liability.id,
                    occurred_at=observation.timestamp,
                    kind="BORROW",
                    principal_cents=cash_shortfall,
                    financing_cost_cents=0,
                    cash_delta_cents=cash_shortfall,
                    ledger_entry_id=od_ledger.id,
                    reference_id=f"od-mov-{target_step}",
                    source_type=run.source_type,
                    dataset_id=run.dataset_id,
                    source_observation_timestamp=observation.timestamp,
                )
            )

            cash_before_financed = cash_acc.balance_cents
            cash_acc.balance_cents -= cash_shortfall
            session.add(
                DbLedgerEntry(
                    id=uuid4(),
                    run_id=run.id,
                    step=target_step,
                    timestamp=None,
                    entry_type="CUSTOMER_WITHDRAWAL_OUTFLOW",
                    amount_cents=cash_shortfall,
                    balance_before_cents=cash_before_financed,
                    balance_after_cents=cash_acc.balance_cents,
                    reference_id=f"FLOW-OUT-FINANCED-{target_step}",
                    source_type=run.source_type,
                    dataset_id=run.dataset_id,
                    source_observation_timestamp=observation.timestamp,
                    event_at=observation.timestamp,
                )
            )

            action_decision = "LIQUIDITY_WARNING"
            decision_explanations.append(
                f"Cash deficit of {cash_shortfall} cents covered via emergency overdraft."
            )

    # 4. Overdraft repayment & hourly interest accrual
    active_ods = list(
        session.scalars(
            select(DbOverdraftLiability).where(
                DbOverdraftLiability.run_id == run.id,
                DbOverdraftLiability.outstanding_principal_cents > 0,
            )
        )
    )
    for od in active_ods:
        hourly_fee = int(
            Decimal(od.outstanding_principal_cents)
            * (od.apr_pct / Decimal("100"))
            / Decimal(8760)
        )
        if hourly_fee > 0:
            od.financing_cost_cents = (od.financing_cost_cents or 0) + hourly_fee
            session.add(
                DbOverdraftMovement(
                    id=uuid4(),
                    run_id=run.id,
                    liability_id=od.id,
                    occurred_at=observation.timestamp,
                    kind="FINANCING_COST",
                    principal_cents=0,
                    financing_cost_cents=hourly_fee,
                    cash_delta_cents=0,
                    ledger_entry_id=None,
                    reference_id=f"od-fee-{run.id}-{target_step}-{od.id}",
                    source_type=run.source_type,
                    dataset_id=run.dataset_id,
                    source_observation_timestamp=observation.timestamp,
                )
            )

        if cash_acc.balance_cents > 0:
            repay_cents = min(cash_acc.balance_cents, od.outstanding_principal_cents)
            cash_acc.balance_cents -= repay_cents
            od.outstanding_principal_cents -= repay_cents
            od.repaid_principal_cents += repay_cents

            repay_ledger = DbLedgerEntry(
                id=uuid4(),
                run_id=run.id,
                step=target_step,
                timestamp=None,
                entry_type="OVERDRAFT_REPAYMENT",
                amount_cents=repay_cents,
                balance_before_cents=cash_acc.balance_cents + repay_cents,
                balance_after_cents=cash_acc.balance_cents,
                reference_id=f"OD-REPAY-{target_step}-{od.id}",
                source_type=run.source_type,
                dataset_id=run.dataset_id,
                source_observation_timestamp=observation.timestamp,
                event_at=observation.timestamp,
            )
            session.add(repay_ledger)
            session.flush()

            session.add(
                DbOverdraftMovement(
                    id=uuid4(),
                    run_id=run.id,
                    liability_id=od.id,
                    occurred_at=observation.timestamp,
                    kind="REPAYMENT",
                    principal_cents=repay_cents,
                    financing_cost_cents=0,
                    cash_delta_cents=-repay_cents,
                    ledger_entry_id=repay_ledger.id,
                    reference_id=f"od-repay-mov-{target_step}-{od.id}",
                    source_type=run.source_type,
                    dataset_id=run.dataset_id,
                    source_observation_timestamp=observation.timestamp,
                )
            )

    # 5. Required Reserve & Sweep Decision by Strategy
    active_strategy = normalize_strategy_id(strategy or policy_dict.get("strategy"))
    cutoff = get_information_cutoff(observation.timestamp)

    forecasts = None
    if active_strategy == STRATEGY_STATIC:
        req_reserve = policy_obj.base_buffer_cents
        strategy_rationale = f"STATIC strategy: fixed buffer of {req_reserve} cents."
    elif active_strategy == STRATEGY_REACTIVE:
        trailing_start = cutoff - timedelta(hours=24)
        recent_obs = list(
            session.scalars(
                select(DbOrganizerObservation).where(
                    DbOrganizerObservation.dataset_id == run.dataset_id,
                    DbOrganizerObservation.timestamp <= cutoff,
                    DbOrganizerObservation.timestamp >= trailing_start,
                )
            ).all()
        )
        if not recent_obs:
            recent_obs = [observation]
        max_withdrawal = max(
            [int(round(o.withdrawals_usd * 100)) for o in recent_obs],
            default=0,
        )
        req_reserve = max(
            policy_obj.base_buffer_cents,
            max_withdrawal + (policy_obj.base_buffer_cents // 2),
        )
        strategy_rationale = (
            f"REACTIVE strategy: buffer set to {req_reserve} cents based on trailing 24h peak withdrawal of {max_withdrawal} cents."
        )
    else:
        forecasts = get_hourly_forecasts_from_db(
            session, run.dataset_id, observation.timestamp, horizon_hours=15
        )
        opt_result = recommend_four_tier_allocation_decision(
            portfolio,
            policy_obj,
            observation,
            forecasts=forecasts,
            horizon_hours=15,
            risk_aversion=policy_dict.get("risk_aversion", "1"),
        )
        req_reserve = opt_result.decision.targets.tier0_target_cents
        strategy_rationale = (
            f"RESERVE_JUGGLER: dynamic required reserve {req_reserve} cents. "
            f"RESERVE_JUGGLER: canonical optimizer recommended reserve {req_reserve} cents. "
            f"Summary action: {opt_result.summary_action}."
        )
        for order in opt_result.decision.orders:
            if order.action == "INVEST_REPO" and order.amount_cents > 0:
                sweep_cents = min(order.amount_cents, max(0, cash_acc.balance_cents - req_reserve))
                if sweep_cents > 0:
                    pre_sweep = cash_acc.balance_cents
                    cash_acc.balance_cents -= sweep_cents

                    sweep_ledger = DbLedgerEntry(
                        id=uuid4(),
                        run_id=run.id,
                        step=target_step,
                        timestamp=None,
                        entry_type="OVERNIGHT_REPO_SWEEP_DEBIT",
                        amount_cents=sweep_cents,
                        balance_before_cents=pre_sweep,
                        balance_after_cents=cash_acc.balance_cents,
                        reference_id=f"REPO-SWEEP-{target_step}",
                        source_type=run.source_type,
                        dataset_id=run.dataset_id,
                        source_observation_timestamp=observation.timestamp,
                        event_at=observation.timestamp,
                    )
                    session.add(sweep_ledger)
                    session.flush()

                    maturity_time = observation.timestamp.replace(hour=8) + timedelta(days=1)
                    new_repo = DbRepoPosition(
                        id=uuid4(),
                        run_id=run.id,
                        source_type=run.source_type,
                        dataset_id=run.dataset_id,
                        source_observation_timestamp=observation.timestamp,
                        principal_cents=sweep_cents,
                        entered_at=observation.timestamp,
                        scheduled_maturity_at=maturity_time,
                        applicable_apy_pct=observation.tier1_repo_rate_apy,
                        status="LOCKED",
                        early_redemption_haircut_pct=observation.tier1_early_redemption_haircut_pct,
                    )
                    session.add(new_repo)
                    session.flush()

                    session.add(
                        DbInvestmentMovement(
                            id=uuid4(),
                            run_id=run.id,
                            tier=1,
                            repo_position_id=new_repo.id,
                            kind="INVESTMENT",
                            occurred_at=observation.timestamp,
                            cash_delta_cents=-sweep_cents,
                            principal_cents=sweep_cents,
                            interest_cents=0,
                            haircut_cost_cents=0,
                            ledger_entry_id=sweep_ledger.id,
                            reference_id=f"mov-sweep-{target_step}",
                            source_type=run.source_type,
                            dataset_id=run.dataset_id,
                            source_observation_timestamp=observation.timestamp,
                        )
                    )
                    action_decision = "SWEEP"
                    decision_amount = sweep_cents
                    decision_explanations.append(
                        f"Canonical optimizer executed repo sweep of {sweep_cents} cents. {strategy_rationale}"
                    )
                    orders_executed.append({
                        "instrument": "OVERNIGHT_REPO",
                        "action": "SWEEP",
                        "amount_cents": sweep_cents,
                        "order_id": str(order.id),
                    })

    if active_strategy in (STRATEGY_STATIC, STRATEGY_REACTIVE) and observation.timestamp.hour == 17:
        deployable_surplus = max(0, cash_acc.balance_cents - req_reserve)
        min_sweep = policy_dict.get("min_sweep_cents", policy_dict.get("minimum_sweep_cents", 1000000))
        if deployable_surplus >= min_sweep:
            sweep_cents = deployable_surplus
            pre_sweep = cash_acc.balance_cents
            cash_acc.balance_cents -= sweep_cents

            sweep_ledger = DbLedgerEntry(
                id=uuid4(),
                run_id=run.id,
                step=target_step,
                timestamp=None,
                entry_type="OVERNIGHT_REPO_SWEEP_DEBIT",
                amount_cents=sweep_cents,
                balance_before_cents=pre_sweep,
                balance_after_cents=cash_acc.balance_cents,
                reference_id=f"REPO-SWEEP-{target_step}",
                source_type=run.source_type,
                dataset_id=run.dataset_id,
                source_observation_timestamp=observation.timestamp,
                event_at=observation.timestamp,
            )
            session.add(sweep_ledger)
            session.flush()

            maturity_time = observation.timestamp.replace(hour=8) + timedelta(days=1)
            new_repo = DbRepoPosition(
                id=uuid4(),
                run_id=run.id,
                source_type=run.source_type,
                dataset_id=run.dataset_id,
                source_observation_timestamp=observation.timestamp,
                principal_cents=sweep_cents,
                entered_at=observation.timestamp,
                scheduled_maturity_at=maturity_time,
                applicable_apy_pct=observation.tier1_repo_rate_apy,
                status="LOCKED",
                early_redemption_haircut_pct=observation.tier1_early_redemption_haircut_pct,
            )
            session.add(new_repo)
            session.flush()

            session.add(
                DbInvestmentMovement(
                    id=uuid4(),
                    run_id=run.id,
                    tier=1,
                    repo_position_id=new_repo.id,
                    kind="INVESTMENT",
                    occurred_at=observation.timestamp,
                    cash_delta_cents=-sweep_cents,
                    principal_cents=sweep_cents,
                    interest_cents=0,
                    haircut_cost_cents=0,
                    ledger_entry_id=sweep_ledger.id,
                    reference_id=f"mov-sweep-{target_step}",
                    source_type=run.source_type,
                    dataset_id=run.dataset_id,
                    source_observation_timestamp=observation.timestamp,
                )
            )
            action_decision = "SWEEP"
            decision_amount = sweep_cents
            decision_explanations.append(
                f"17:00 sweep window open. Swept {sweep_cents} cents excess cash into overnight repo. {strategy_rationale}"
            )
            orders_executed.append({
                "instrument": "OVERNIGHT_REPO",
                "action": "SWEEP",
                "amount_cents": sweep_cents,
            })

    # 6. Mark to Market & Valuations
    tier2_mkt_val = 0
    tier2_notional = 0
    tier2_unrealized = 0
    tier2_realized = 0
    for b in db_bonds:
        cur_p = observation.tier2_bond_price_index if observation else Decimal("100.0")
        cost_b = int(round(b.quantity * b.acquisition_price_index * Decimal(100)))
        tier2_notional += cost_b
        mkt_val = int(round(b.quantity * cur_p * Decimal(100))) if b.quantity > 0 else (b.current_market_value_cents or 0)
        tier2_mkt_val += mkt_val
        tier2_unrealized += (mkt_val - cost_b)
        session.add(
            DbPositionValuation(
                id=uuid4(),
                run_id=run.id,
                tier=2,
                bond_position_id=b.id,
                repo_position_id=None,
                equity_position_id=None,
                valued_at=target_timestamp,
                market_price_index=cur_p,
                market_value_cents=mkt_val,
                realized_pnl_cents=0,
                unrealized_pnl_cents=mkt_val - cost_b,
                reference_id=f"pos-val-b-{b.id}-{target_step}",
                source_type=run.source_type,
                dataset_id=run.dataset_id,
                source_observation_timestamp=observation.timestamp,
            )
        )

    tier3_mkt_val = 0
    tier3_cost_basis = 0
    tier3_unrealized = 0
    tier3_realized = 0
    for eq in db_equities:
        cur_p = observation.tier3_stock_index_price if observation else Decimal("450.0")
        cost_b = int(round(eq.quantity * eq.acquisition_price_index * Decimal(100)))
        tier3_cost_basis += cost_b
        mkt_val = int(round(eq.quantity * cur_p * Decimal(100))) if eq.quantity > 0 else (eq.current_market_value_cents or 0)
        tier3_mkt_val += mkt_val
        tier3_unrealized += (mkt_val - cost_b)
        session.add(
            DbPositionValuation(
                id=uuid4(),
                run_id=run.id,
                tier=3,
                bond_position_id=None,
                repo_position_id=None,
                equity_position_id=eq.id,
                valued_at=target_timestamp,
                market_price_index=cur_p,
                market_value_cents=mkt_val,
                realized_pnl_cents=0,
                unrealized_pnl_cents=mkt_val - cost_b,
                reference_id=f"pos-val-eq-{eq.id}-{target_step}",
                source_type=run.source_type,
                dataset_id=run.dataset_id,
                source_observation_timestamp=observation.timestamp,
            )
        )

    active_repos_after = list(
        session.scalars(
            select(DbRepoPosition).where(
                DbRepoPosition.run_id == run.id,
                DbRepoPosition.status.in_(["ACTIVE", "LOCKED"]),
            )
        )
    )
    tier1_principal = sum(r.principal_cents for r in active_repos_after)
    repo_apy_bps = int(observation.tier1_repo_rate_apy * 100) if observation else 525
    tier1_accrued = sum(
        int(r.principal_cents * (observation.tier1_repo_rate_apy / Decimal("100")) * Decimal(1) / Decimal(8760))
        for r in active_repos_after
    ) if observation else 0

    all_ods = list(
        session.scalars(
            select(DbOverdraftLiability).where(
                DbOverdraftLiability.run_id == run.id,
            )
        )
    )
    od_borrowing = sum(o.outstanding_principal_cents for o in all_ods)
    od_fees = sum(o.financing_cost_cents or 0 for o in all_ods)
    total_liabilities = od_borrowing + od_fees

    gross_assets = cash_acc.balance_cents + tier1_principal + tier1_accrued + tier2_mkt_val + tier3_mkt_val
    net_value = gross_assets - total_liabilities

    # Haircut and slippage
    tier2_haircut_bps = int(observation.tier2_bond_liquidation_haircut_pct * 100) if observation else 200
    tier2_haircut_cents = int(tier2_mkt_val * tier2_haircut_bps / 10000)
    tier2_avail_liquidity = max(0, tier2_mkt_val - tier2_haircut_cents)

    tier3_slippage_bps = int(observation.tier3_stock_liquidation_haircut_pct * 100) if observation else 1500
    tier3_slippage_cents = int(tier3_mkt_val * tier3_slippage_bps / 10000)
    tier3_avail_liquidity = max(0, tier3_mkt_val - tier3_slippage_cents)

    tier1_break_fee_bps = 50
    tier1_break_fee_cents = int(tier1_principal * tier1_break_fee_bps / 10000) if policy_obj.allow_early_repo_redemption else 0
    tier1_net_redeemable = max(0, tier1_principal - tier1_break_fee_cents) if policy_obj.allow_early_repo_redemption else 0

    total_immediate_liquidity = (
        cash_acc.balance_cents
        + tier1_net_redeemable
        + tier2_avail_liquidity
        + tier3_avail_liquidity
    )

    pv = DbPortfolioValuation(
        id=uuid4(),
        run_id=run.id,
        source_type=run.source_type,
        dataset_id=run.dataset_id,
        source_observation_timestamp=observation.timestamp,
        valued_at=target_timestamp,
        tier0_cash_cents=cash_acc.balance_cents,
        tier1_principal_cents=tier1_principal,
        tier1_value_cents=tier1_principal + tier1_accrued,
        tier2_market_value_cents=tier2_mkt_val,
        tier3_market_value_cents=tier3_mkt_val,
        total_portfolio_value_cents=gross_assets,
        immediately_available_cents=cash_acc.balance_cents,
        liquidatable_value_cents=total_immediate_liquidity,
        restricted_value_cents=tier1_principal,
        liabilities_cents=total_liabilities,
        net_portfolio_value_cents=net_value,
        reference_id=f"val-{run.id}-{target_step}",
    )
    session.add(pv)

    # 7. Record Treasury Decision
    if not decision_explanations:
        decision_explanations = [
            f"Holding cash balance of {cash_acc.balance_cents} cents. Required reserve: {req_reserve} cents. {strategy_rationale}"
        ]

    details = {
        "strategy": active_strategy,
        "pre_checking_cents": pre_out,
        "post_checking_cents": cash_acc.balance_cents,
        "executed": executed_decision,
        "orders_executed": orders_executed,
    }
    db_decision = DbTreasuryDecision(
        id=uuid4(),
        run_id=run.id,
        step=target_step,
        timestamp=None if run.source_type == "ORGANIZER_HISTORICAL" else observation.timestamp,
        action=action_decision,
        amount_cents=decision_amount,
        execution_status="EXECUTED" if executed_decision else "RECOMMENDED",
        explanation_json=decision_explanations,
        decision_details_json=details,
        source_type=run.source_type,
        dataset_id=run.dataset_id,
        source_observation_timestamp=observation.timestamp,
        tier0_target_cents=req_reserve,
        required_reserve_cents=req_reserve,
        available_liquidity_cents=cash_acc.balance_cents,
        expected_inflow_cents=inflow_cents,
        expected_outflow_cents=outflow_cents,
        uncertainty_cents=forecasts[0].supplied_uncertainty_buffer_cents if forecasts else 0,
    )
    session.add(db_decision)

    # 8. Advance run step and timestamp
    run.current_step = target_step
    run.updated_at = datetime.now(timezone.utc)
    session.flush()

    deployable_surplus_cents = max(0, cash_acc.balance_cents - req_reserve)

    four_tier_dict = {
        "timestamp": observation.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
        "tier0": {
            "tier": 0,
            "name": "Operating Cash Buffer",
            "checking_cents": cash_acc.balance_cents,
            "required_reserve_cents": req_reserve,
            "operational_buffer_cents": policy_obj.base_buffer_cents,
            "deployable_surplus_cents": deployable_surplus_cents,
            "reserve_deficit_cents": max(0, req_reserve - cash_acc.balance_cents),
            "immediate_liquidity_cents": cash_acc.balance_cents,
            "status": "DEFICIT" if cash_acc.balance_cents < req_reserve else ("SURPLUS" if deployable_surplus_cents > 0 else "BALANCED"),
        },
        "tier1": {
            "tier": 1,
            "id": "REPO-PORTFOLIO-1",
            "name": "Overnight Repo",
            "principal_cents": tier1_principal,
            "repo_apy_bps": repo_apy_bps,
            "repo_apy_decimal": f"{repo_apy_bps / 100:.2f}",
            "accrued_interest_cents": tier1_accrued,
            "realized_interest_cents": 0,
            "status": "LOCKED" if tier1_principal > 0 else "MATURED",
            "entry_window_open": (observation.timestamp.hour == 17),
            "early_redemption_allowed": policy_obj.allow_early_repo_redemption,
            "early_break_fee_bps": tier1_break_fee_bps,
            "break_fee_cents": tier1_break_fee_cents,
            "net_redeemable_cents": tier1_net_redeemable,
            "immediate_liquidity_cents": tier1_net_redeemable,
            "entry_time": "17:00",
            "maturity_time": "08:00",
            "maturity_timestamp": (observation.timestamp.replace(hour=8) + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S") if tier1_principal > 0 else None,
        },
        "tier2": {
            "tier": 2,
            "id": "BOND-SOV-1",
            "name": "Sovereign Bonds",
            "notional_cents": tier2_notional,
            "quantity": float(sum(b.quantity for b in db_bonds)) if db_bonds else 0.0,
            "acquisition_price": "100.0000",
            "current_price": str(observation.tier2_bond_price_index) if observation else "100.0000",
            "market_value_cents": tier2_mkt_val,
            "ytm_bps": int(observation.tier2_bond_yield_pct * 100) if observation else 445,
            "ytm_decimal": f"{observation.tier2_bond_yield_pct:.2f}" if observation else "4.45",
            "modified_duration": float(observation.tier2_bond_mod_duration) if observation and observation.tier2_bond_mod_duration else 4.25,
            "liquidation_haircut_bps": tier2_haircut_bps,
            "haircut_cents": tier2_haircut_cents,
            "realized_pnl_cents": tier2_realized,
            "unrealized_pnl_cents": tier2_unrealized,
            "available_liquidity_cents": tier2_avail_liquidity,
            "liquidity_status": "2-DAY_SETTLEMENT_OR_HAIRCUT",
        },
        "tier3": {
            "tier": 3,
            "id": "EQ-IDX-1",
            "name": "Growth Equities",
            "quantity": float(sum(eq.quantity for eq in db_equities)) if db_equities else 0.0,
            "acquisition_price": "450.0000",
            "current_price": str(observation.tier3_stock_index_price) if observation else "450.0000",
            "market_value_cents": tier3_mkt_val,
            "cost_basis_cents": tier3_cost_basis,
            "volatility_bps": int(observation.tier3_stock_volatility_pct * 100) if observation else 1680,
            "volatility_decimal": f"{observation.tier3_stock_volatility_pct:.2f}" if observation else "16.80",
            "emergency_slippage_bps": tier3_slippage_bps,
            "slippage_cents": tier3_slippage_cents,
            "realized_pnl_cents": tier3_realized,
            "unrealized_pnl_cents": tier3_unrealized,
            "available_liquidity_cents": tier3_avail_liquidity,
            "liquidity_status": "MARKET_VOLATILITY_AND_SLIPPAGE",
        },
        "overdraft": {
            "borrowing_outstanding_cents": od_borrowing,
            "financing_rate_bps": 1000,
            "financing_cost_cents": od_fees,
            "liability_status": "ACTIVE" if od_borrowing > 0 else "CLEARED",
            "is_active": (od_borrowing > 0),
        },
        "aggregates": {
            "gross_assets_cents": gross_assets,
            "total_liabilities_cents": od_borrowing,
            "net_portfolio_value_cents": net_value,
            "total_immediate_liquidity_cents": total_immediate_liquidity,
            "total_realized_returns_cents": 0,
            "total_unrealized_returns_cents": tier1_accrued + tier2_unrealized + tier3_unrealized,
            "net_financial_benefit_cents": -od_fees,
            "checking_cents": cash_acc.balance_cents,
            "required_reserve_cents": req_reserve,
            "deployable_surplus_cents": deployable_surplus_cents,
        },
    }

    iso_utc_ts = datetime.now(timezone.utc)

    return {
        "run_id": run.id,
        "step": target_step,
        "timestamp": iso_utc_ts,
        "strategy": active_strategy,
        "status": "RUNNING" if target_step < run.duration_steps else "COMPLETED",
        "checking_cents": cash_acc.balance_cents,
        "vault_locked_cents": tier1_principal,
        "vault_redeemable_cents": tier1_net_redeemable,
        "required_reserve_cents": req_reserve,
        "deployable_surplus_cents": deployable_surplus_cents,
        "policy": {
            "strategy": active_strategy,
            "risk_percentile": policy_dict.get("risk_percentile", 0.95),
            "operational_buffer_cents": policy_dict.get("operational_buffer_cents", 50000000),
            "minimum_sweep_cents": policy_dict.get("minimum_sweep_cents", 1000000),
            "vault_yield_bps": policy_dict.get("vault_yield_bps", 500),
            "vault_lock_steps": policy_dict.get("vault_lock_steps", 96),
            "early_redemption_allowed": policy_dict.get("early_redemption_allowed", True),
            "early_redemption_penalty_bps": policy_dict.get("early_redemption_penalty_bps", 200),
        },
        "decision": {
            "action": action_decision,
            "amount_cents": decision_amount,
            "pre_checking_cents": pre_out,
            "post_checking_cents": cash_acc.balance_cents,
            "executed": executed_decision,
            "explanation": decision_explanations,
        },
        "forecast": {
            "horizon_minutes": 240,
            "peak_shortfall_cents": 0,
            "uncertainty_buffer_cents": forecasts[0].supplied_uncertainty_buffer_cents if (forecasts and len(forecasts) > 0) else 0,
            "operational_buffer_cents": policy_obj.base_buffer_cents,
            "model_version": "evaluated-gb-v1" if active_strategy == STRATEGY_RESERVE_JUGGLER else "none",
        },
        "four_tier": four_tier_dict,
    }
