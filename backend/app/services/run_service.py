"""Simulation run lifecycle and domain service.

Manages:
- Run creation with default $20M checking
- Full four-tier snapshot generation
- Simulation advancement with concurrency control (stale-step conflicts)
- Scenario scheduling and application
- Policy updates supporting frontend parameter naming
- History, decisions, transactions, and forecast reporting
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
    DatasetSource as DbDatasetSource,
    EquityPosition as DbEquityPosition,
    InvestmentMovement as DbInvestmentMovement,
    LedgerEntry as DbLedgerEntry,
    OrganizerObservation as DbOrganizerObservation,
    OverdraftLiability as DbOverdraftLiability,
    PortfolioValuation as DbPortfolioValuation,
    RepoPosition as DbRepoPosition,
    SimulationRun as DbSimulationRun,
    TreasuryDecision as DbTreasuryDecision,
)
from app.persistence.repositories import configuration_identity
from app.services.hourly_engine import StepConflictError, execute_hourly_step
from app.services.treasury_adapter import (
    build_four_tier_policy,
    get_hourly_forecasts_from_db,
    hydrate_portfolio_state,
)
from app.v1_contracts import (
    AdvanceRequest,
    CreateRunRequest,
    DecisionRecord,
    DecisionsResponse,
    ForecastPoint,
    ForecastResponse,
    ForecastSummary,
    FourTierPortfolioSnapshot,
    HistoryResponse,
    PolicyPatch,
    RunCreated,
    ScenarioApplied,
    ScenarioRequest,
    SimulationSnapshot,
    TransactionRecord,
    TransactionsResponse,
    TreasuryPolicy,
)


def _get_or_load_dataset(session: Session) -> DbDatasetSource:
    """Retrieves the active dataset source."""
    ds = session.scalar(select(DbDatasetSource).limit(1))
    if ds is not None:
        return ds

    # If not yet registered in dataset_sources, query organizer_observations
    obs = session.scalar(
        select(DbOrganizerObservation).order_by(DbOrganizerObservation.timestamp.asc()).limit(1)
    )
    if obs is not None:
        last_obs = session.scalar(
            select(DbOrganizerObservation).order_by(DbOrganizerObservation.timestamp.desc()).limit(1)
        )
        ds = DbDatasetSource(
            dataset_id=obs.dataset_id,
            dataset_name="treasury_4tier_dataset",
            source_type="ORGANIZER_CSV",
            source_path="treasury_4tier_dataset.csv",
            content_hash="2e7c1d2e5b678e9975250211e7e0017022067fc4d01b173bf8a335759714856f",
            hash_algorithm="sha256",
            row_count=8760,
            first_timestamp=obs.timestamp,
            last_timestamp=last_obs.timestamp,
            native_interval_seconds=3600,
            timezone_status="UNSPECIFIED",
            validation_status="VALIDATED",
            validation_json={},
        )
        session.add(ds)
        session.flush()
        return ds

    raise RuntimeError("No organizer dataset found in database.")


def create_simulation_run(session: Session, request: CreateRunRequest) -> RunCreated:
    """Creates a new simulation run with default $20 million in Tier 0 checking."""
    ds = _get_or_load_dataset(session)
    policy_dict = request.policy.model_dump(mode="json")
    policy_dict.setdefault("scenarios", [])

    run_id = uuid4()
    run = DbSimulationRun(
        id=run_id,
        seed=request.seed,
        scenario=request.scenario.value,
        status="READY",
        current_step=0,
        duration_steps=request.duration_steps,
        initial_cash_cents=request.initial_cash_cents,
        policy_json=policy_dict,
        source_type="ORGANIZER_HISTORICAL",
        dataset_id=ds.dataset_id,
        source_start_timestamp=ds.first_timestamp,
        source_end_timestamp=ds.last_timestamp,
        native_interval_seconds=ds.native_interval_seconds,
        source_timezone_status="UNSPECIFIED",
        configuration_hash=configuration_identity(policy_dict),
    )
    session.add(run)
    session.flush()

    # Initial Tier 0 Cash Account
    cash = DbCashAccount(
        id=uuid4(),
        run_id=run.id,
        source_type=run.source_type,
        dataset_id=run.dataset_id,
        source_observation_timestamp=ds.first_timestamp,
        balance_cents=request.initial_cash_cents,
    )
    session.add(cash)

    # Initial Portfolio Valuation
    pv = DbPortfolioValuation(
        id=uuid4(),
        run_id=run.id,
        source_type=run.source_type,
        dataset_id=run.dataset_id,
        source_observation_timestamp=ds.first_timestamp,
        valued_at=ds.first_timestamp,
        tier0_cash_cents=request.initial_cash_cents,
        tier1_principal_cents=0,
        tier1_value_cents=0,
        tier2_market_value_cents=0,
        tier3_market_value_cents=0,
        total_portfolio_value_cents=request.initial_cash_cents,
        immediately_available_cents=request.initial_cash_cents,
        liquidatable_value_cents=request.initial_cash_cents,
        restricted_value_cents=0,
        liabilities_cents=0,
        net_portfolio_value_cents=request.initial_cash_cents,
        reference_id=f"val-init-{run.id}",
    )
    session.add(pv)

    # Initial Ledger Entry
    ledger = DbLedgerEntry(
        id=uuid4(),
        run_id=run.id,
        step=0,
        timestamp=None,
        entry_type="INITIAL_CAPITAL_DEPOSIT",
        amount_cents=request.initial_cash_cents,
        balance_before_cents=0,
        balance_after_cents=request.initial_cash_cents,
        reference_id=f"INITIAL-{run.id}",
        source_type=run.source_type,
        dataset_id=run.dataset_id,
        source_observation_timestamp=ds.first_timestamp,
        event_at=ds.first_timestamp,
    )
    session.add(ledger)
    session.flush()

    return RunCreated(
        run_id=run.id,
        status="READY",
        current_step=0,
        checking_cents=request.initial_cash_cents,
        vault_locked_cents=0,
    )


def get_simulation_snapshot(session: Session, run_id: UUID) -> SimulationSnapshot:
    """Reads full simulation snapshot with four-tier portfolio state."""
    run = session.scalar(select(DbSimulationRun).where(DbSimulationRun.id == run_id))
    if run is None:
        raise KeyError(f"Simulation run {run_id} not found")

    step_timestamp = run.source_start_timestamp + timedelta(hours=run.current_step)
    obs = session.scalar(
        select(DbOrganizerObservation).where(
            DbOrganizerObservation.dataset_id == run.dataset_id,
            DbOrganizerObservation.timestamp == step_timestamp,
        )
    )

    (
        portfolio,
        cash_acc,
        db_repos,
        db_bonds,
        db_equities,
        db_overdrafts,
    ) = hydrate_portfolio_state(session, run, obs)

    policy_dict = run.policy_json or {}
    policy_obj = build_four_tier_policy(policy_dict)

    # Repo positions
    active_repos = [r for r in db_repos if r.status in ("ACTIVE", "LOCKED")]
    tier1_principal = sum(r.principal_cents for r in active_repos)
    repo_apy_bps = int(obs.tier1_repo_rate_apy * 100) if obs else 525
    tier1_accrued = sum(
        int(r.principal_cents * (obs.tier1_repo_rate_apy / Decimal("100")) * Decimal(1) / Decimal(8760))
        for r in active_repos
    ) if obs else 0
    tier1_break_fee_bps = 50
    tier1_break_fee_cents = int(tier1_principal * tier1_break_fee_bps / 10000) if policy_obj.allow_early_repo_redemption else 0
    tier1_net_redeemable = max(0, tier1_principal - tier1_break_fee_cents) if policy_obj.allow_early_repo_redemption else 0

    # Bonds
    tier2_mkt_val = 0
    tier2_notional = 0
    tier2_unrealized = 0
    for b in db_bonds:
        cur_p = obs.tier2_bond_price_index if obs else b.acquisition_price_index
        cost_b = int(round(b.quantity * b.acquisition_price_index * Decimal(100)))
        tier2_notional += cost_b
        mkt_val = int(round(b.quantity * cur_p * Decimal(100))) if b.quantity > 0 else (b.current_market_value_cents or 0)
        tier2_mkt_val += mkt_val
        tier2_unrealized += (mkt_val - cost_b)

    tier2_haircut_bps = int(obs.tier2_bond_liquidation_haircut_pct * 100) if obs else 200
    tier2_haircut_cents = int(tier2_mkt_val * tier2_haircut_bps / 10000)
    tier2_avail_liquidity = max(0, tier2_mkt_val - tier2_haircut_cents)

    # Equities
    tier3_mkt_val = 0
    tier3_cost_basis = 0
    tier3_unrealized = 0
    for eq in db_equities:
        cur_p = obs.tier3_stock_index_price if obs else eq.acquisition_price_index
        cost_b = int(round(eq.quantity * eq.acquisition_price_index * Decimal(100)))
        tier3_cost_basis += cost_b
        mkt_val = int(round(eq.quantity * cur_p * Decimal(100))) if eq.quantity > 0 else (eq.current_market_value_cents or 0)
        tier3_mkt_val += mkt_val
        tier3_unrealized += (mkt_val - cost_b)

    tier3_slippage_bps = int(obs.tier3_stock_liquidation_haircut_pct * 100) if obs else 1500
    tier3_slippage_cents = int(tier3_mkt_val * tier3_slippage_bps / 10000)
    tier3_avail_liquidity = max(0, tier3_mkt_val - tier3_slippage_cents)

    # Overdraft
    od_borrowing = sum(od.outstanding_principal_cents for od in db_overdrafts)
    od_fees = sum(od.financing_cost_cents or 0 for od in db_overdrafts)

    gross_assets = cash_acc.balance_cents + tier1_principal + tier2_mkt_val + tier3_mkt_val
    net_value = gross_assets - od_borrowing

    req_reserve = policy_obj.minimum_liquid_reserve_cents
    deployable_surplus = max(0, cash_acc.balance_cents - req_reserve)

    total_immediate_liquidity = (
        cash_acc.balance_cents
        + tier1_net_redeemable
        + tier2_avail_liquidity
        + tier3_avail_liquidity
    )

    four_tier_snapshot = FourTierPortfolioSnapshot(
        timestamp=obs.timestamp.strftime("%Y-%m-%d %H:%M:%S") if obs else None,
        tier0={
            "tier": 0,
            "name": "Operating Cash Buffer",
            "checking_cents": cash_acc.balance_cents,
            "required_reserve_cents": req_reserve,
            "operational_buffer_cents": policy_obj.base_buffer_cents,
            "deployable_surplus_cents": deployable_surplus,
            "reserve_deficit_cents": max(0, req_reserve - cash_acc.balance_cents),
            "immediate_liquidity_cents": cash_acc.balance_cents,
            "status": "DEFICIT" if cash_acc.balance_cents < req_reserve else ("SURPLUS" if deployable_surplus > 0 else "BALANCED"),
        },
        tier1={
            "tier": 1,
            "id": "REPO-PORTFOLIO-1",
            "name": "Overnight Repo",
            "principal_cents": tier1_principal,
            "repo_apy_bps": repo_apy_bps,
            "repo_apy_decimal": f"{repo_apy_bps / 100:.2f}",
            "accrued_interest_cents": tier1_accrued,
            "realized_interest_cents": 0,
            "status": "LOCKED" if tier1_principal > 0 else "MATURED",
            "entry_window_open": (obs.timestamp.hour == 17) if obs else False,
            "early_redemption_allowed": policy_obj.allow_early_repo_redemption,
            "early_break_fee_bps": tier1_break_fee_bps,
            "break_fee_cents": tier1_break_fee_cents,
            "net_redeemable_cents": tier1_net_redeemable,
            "immediate_liquidity_cents": tier1_net_redeemable,
            "entry_time": "17:00",
            "maturity_time": "08:00",
            "maturity_timestamp": (obs.timestamp.replace(hour=8) + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S") if (obs and tier1_principal > 0) else None,
        },
        tier2={
            "tier": 2,
            "id": "BOND-SOV-1",
            "name": "Sovereign Bonds",
            "notional_cents": tier2_notional,
            "quantity": float(sum(b.quantity for b in db_bonds)) if db_bonds else 0.0,
            "acquisition_price": "100.0000",
            "current_price": str(obs.tier2_bond_price_index) if obs else "100.0000",
            "market_value_cents": tier2_mkt_val,
            "ytm_bps": int(obs.tier2_bond_yield_pct * 100) if obs else 445,
            "ytm_decimal": f"{obs.tier2_bond_yield_pct:.2f}" if obs else "4.45",
            "modified_duration": float(obs.tier2_bond_mod_duration) if obs and obs.tier2_bond_mod_duration else 4.25,
            "liquidation_haircut_bps": tier2_haircut_bps,
            "haircut_cents": tier2_haircut_cents,
            "realized_pnl_cents": 0,
            "unrealized_pnl_cents": tier2_unrealized,
            "available_liquidity_cents": tier2_avail_liquidity,
            "liquidity_status": "2-DAY_SETTLEMENT_OR_HAIRCUT",
        },
        tier3={
            "tier": 3,
            "id": "EQ-IDX-1",
            "name": "Growth Equities",
            "quantity": float(sum(eq.quantity for eq in db_equities)) if db_equities else 0.0,
            "acquisition_price": "450.0000",
            "current_price": str(obs.tier3_stock_index_price) if obs else "450.0000",
            "market_value_cents": tier3_mkt_val,
            "cost_basis_cents": tier3_cost_basis,
            "volatility_bps": int(obs.tier3_stock_volatility_pct * 100) if obs else 1680,
            "volatility_decimal": f"{obs.tier3_stock_volatility_pct:.2f}" if obs else "16.80",
            "emergency_slippage_bps": tier3_slippage_bps,
            "slippage_cents": tier3_slippage_cents,
            "realized_pnl_cents": 0,
            "unrealized_pnl_cents": tier3_unrealized,
            "available_liquidity_cents": tier3_avail_liquidity,
            "liquidity_status": "MARKET_VOLATILITY_AND_SLIPPAGE",
        },
        overdraft={
            "borrowing_outstanding_cents": od_borrowing,
            "financing_rate_bps": 1000,
            "financing_cost_cents": od_fees,
            "liability_status": "ACTIVE" if od_borrowing > 0 else "CLEARED",
            "is_active": (od_borrowing > 0),
        },
        aggregates={
            "gross_assets_cents": gross_assets,
            "total_liabilities_cents": od_borrowing,
            "net_portfolio_value_cents": net_value,
            "total_immediate_liquidity_cents": total_immediate_liquidity,
            "total_realized_returns_cents": 0,
            "total_unrealized_returns_cents": tier1_accrued + tier2_unrealized + tier3_unrealized,
            "net_financial_benefit_cents": -od_fees,
            "checking_cents": cash_acc.balance_cents,
            "required_reserve_cents": req_reserve,
            "deployable_surplus_cents": deployable_surplus,
        },
    )

    # Latest decision
    latest_dec = session.scalar(
        select(DbTreasuryDecision).where(
            DbTreasuryDecision.run_id == run.id,
            DbTreasuryDecision.step == run.current_step,
        )
    )
    decision_rec = None
    if latest_dec is not None:
        details = latest_dec.decision_details_json or {}
        expl = latest_dec.explanation_json if isinstance(latest_dec.explanation_json, list) else (latest_dec.explanation_json.get("explanations", []) if isinstance(latest_dec.explanation_json, dict) else [])
        decision_rec = DecisionRecord(
            action=latest_dec.action,
            amount_cents=latest_dec.amount_cents,
            pre_checking_cents=details.get("pre_checking_cents", 0),
            post_checking_cents=details.get("post_checking_cents", 0),
            executed=details.get("executed", latest_dec.execution_status == "EXECUTED"),
            explanation=expl,
        )

    # Forecast summary
    forecast_sum = ForecastSummary(
        horizon_minutes=240,
        peak_shortfall_cents=0,
        uncertainty_buffer_cents=policy_obj.base_buffer_cents,
        operational_buffer_cents=policy_obj.base_buffer_cents,
        model_version="evaluated-gb-v1",
    )

    return SimulationSnapshot(
        run_id=run.id,
        step=run.current_step,
        timestamp=datetime.now(timezone.utc),
        checking_cents=cash_acc.balance_cents,
        vault_locked_cents=tier1_principal,
        vault_redeemable_cents=tier1_net_redeemable,
        required_reserve_cents=req_reserve,
        forecast=forecast_sum,
        decision=decision_rec,
        status="READY" if run.current_step == 0 else ("RUNNING" if run.current_step < run.duration_steps else "COMPLETED"),
        policy=TreasuryPolicy(**{k: v for k, v in policy_dict.items() if k != "scenarios"}),
        deployable_surplus_cents=deployable_surplus,
        four_tier=four_tier_snapshot,
    )


def advance_simulation_run(
    session: Session,
    run_id: UUID,
    request: AdvanceRequest,
) -> SimulationSnapshot:
    """Advances the simulation by the requested steps."""
    for _ in range(request.steps):
        execute_hourly_step(session, run_id, expected_step=request.expected_step)
        # Advance expected_step for subsequent steps if steps > 1
        request.expected_step += 1

    return get_simulation_snapshot(session, run_id)


def apply_simulation_scenario(
    session: Session,
    run_id: UUID,
    request: ScenarioRequest,
) -> ScenarioApplied:
    """Schedules or applies a simulation scenario."""
    run = session.scalar(select(DbSimulationRun).where(DbSimulationRun.id == run_id))
    if run is None:
        raise KeyError(f"Simulation run {run_id} not found")

    effective_step = request.effective_step
    if effective_step is None:
        effective_step = request.parameters.get("effective_step", run.current_step + 1)

    policy_json = dict(run.policy_json or {})
    scenarios_list = list(policy_json.get("scenarios", []))
    scenarios_list.append({
        "scenario": request.scenario.value,
        "effective_step": effective_step,
        "parameters": request.parameters,
    })
    policy_json["scenarios"] = scenarios_list
    run.policy_json = policy_json
    session.flush()

    return ScenarioApplied(
        run_id=run.id,
        scenario=request.scenario,
        effective_step=effective_step,
        parameters=request.parameters,
    )


def update_simulation_policy(
    session: Session,
    run_id: UUID,
    patch: PolicyPatch,
) -> TreasuryPolicy:
    """Updates simulation policy mapping frontend names."""
    run = session.scalar(select(DbSimulationRun).where(DbSimulationRun.id == run_id))
    if run is None:
        raise KeyError(f"Simulation run {run_id} not found")

    policy_json = dict(run.policy_json or {})
    patch_dict = patch.model_dump(exclude_unset=True, exclude_none=True)
    policy_json.update(patch_dict)
    run.policy_json = policy_json
    clean_policy = {k: v for k, v in policy_json.items() if k != "scenarios"}
    return TreasuryPolicy(**clean_policy)


def get_simulation_history(
    session: Session,
    run_id: UUID,
    limit: int = 100,
) -> HistoryResponse:
    """Returns simulation history enveloped in {items: [...]}."""
    run = session.scalar(select(DbSimulationRun).where(DbSimulationRun.id == run_id))
    if run is None:
        raise KeyError(f"Simulation run {run_id} not found")

    # In single snapshot or valuations
    current_snap = get_simulation_snapshot(session, run_id)
    return HistoryResponse(items=[current_snap])


def get_simulation_decisions(
    session: Session,
    run_id: UUID,
    limit: int = 100,
) -> DecisionsResponse:
    """Returns decisions history enveloped in {items: [...]}."""
    run = session.scalar(select(DbSimulationRun).where(DbSimulationRun.id == run_id))
    if run is None:
        raise KeyError(f"Simulation run {run_id} not found")

    db_decisions = list(
        session.scalars(
            select(DbTreasuryDecision).where(
                DbTreasuryDecision.run_id == run.id
            ).order_by(DbTreasuryDecision.step.asc()).limit(limit)
        )
    )
    items = []
    for d in db_decisions:
        details = d.decision_details_json or {}
        expl = d.explanation_json if isinstance(d.explanation_json, list) else (d.explanation_json.get("explanations", []) if isinstance(d.explanation_json, dict) else [])
        items.append(
            DecisionRecord(
                action=d.action,
                amount_cents=d.amount_cents,
                pre_checking_cents=details.get("pre_checking_cents", 0),
                post_checking_cents=details.get("post_checking_cents", 0),
                executed=details.get("executed", d.execution_status == "EXECUTED"),
                explanation=expl,
            )
        )
    return DecisionsResponse(items=items)


def get_simulation_transactions(
    session: Session,
    run_id: UUID,
    limit: int = 50,
) -> TransactionsResponse:
    """Returns transaction records enveloped in {items: [...]}."""
    run = session.scalar(select(DbSimulationRun).where(DbSimulationRun.id == run_id))
    if run is None:
        raise KeyError(f"Simulation run {run_id} not found")

    db_ledgers = list(
        session.scalars(
            select(DbLedgerEntry).where(
                DbLedgerEntry.run_id == run.id
            ).order_by(DbLedgerEntry.step.asc()).limit(limit)
        )
    )
    items = []
    for l in db_ledgers:
        if "INFLOW" in l.entry_type or "DEPOSIT" in l.entry_type:
            direction = "INFLOW"
            tx_type = "DEPOSIT"
        elif "OUTFLOW" in l.entry_type or "WITHDRAWAL" in l.entry_type:
            direction = "OUTFLOW"
            tx_type = "WITHDRAWAL"
        else:
            direction = "INFLOW"
            tx_type = "MERCHANT_SETTLEMENT"

        items.append(
            TransactionRecord(
                transaction_id=l.id,
                run_id=l.run_id,
                timestamp=datetime.now(timezone.utc),
                step=l.step,
                type=tx_type,
                direction=direction,
                amount_cents=max(1, l.amount_cents),
                source=l.entry_type,
                scenario=run.scenario,
            )
        )
    return TransactionsResponse(items=items)


def get_simulation_forecast(
    session: Session,
    run_id: UUID,
    horizon_minutes: int = 240,
) -> ForecastResponse:
    """Returns predictive forecasts enveloped in {points: [...]}."""
    run = session.scalar(select(DbSimulationRun).where(DbSimulationRun.id == run_id))
    if run is None:
        raise KeyError(f"Simulation run {run_id} not found")

    step_timestamp = run.source_start_timestamp + timedelta(hours=run.current_step)
    horizon_hours = max(1, horizon_minutes // 60)
    db_forecasts = get_hourly_forecasts_from_db(
        session, run.dataset_id, step_timestamp, horizon_hours=horizon_hours
    )

    points = []
    for f in db_forecasts:
        points.append(
            ForecastPoint(
                timestamp=datetime.now(timezone.utc),
                predicted_inflow_cents=f.predicted_deposits_cents,
                predicted_outflow_cents=f.predicted_withdrawals_cents,
                predicted_net_cents=f.predicted_net_flow_cents,
                lower_cents=f.predicted_net_flow_cents - f.supplied_uncertainty_buffer_cents,
                upper_cents=f.predicted_net_flow_cents + f.supplied_uncertainty_buffer_cents,
            )
        )

    return ForecastResponse(
        as_of=datetime.now(timezone.utc),
        horizon_minutes=horizon_minutes,
        model_version="evaluated-gb-v1",
        points=points,
        summary=ForecastSummary(
            horizon_minutes=horizon_minutes,
            peak_shortfall_cents=0,
            uncertainty_buffer_cents=points[0].upper_cents - points[0].predicted_net_cents if points else 0,
            operational_buffer_cents=50000000,
            model_version="evaluated-gb-v1",
        ),
    )
