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
from app.services.accounting import aggregate_acquisition_price, financial_performance, market_cost_basis
from treasury_intelligence.instrument_economics import percentage_cost_cents
from app.services.hourly_engine import StepConflictError, execute_hourly_step
from app.services.treasury_adapter import (
    build_four_tier_policy,
    get_hourly_forecasts_from_db,
    hydrate_portfolio_state,
    get_published_observation,
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


def _get_or_load_dataset(session: Session, dataset_id: str | None = None) -> DbDatasetSource:
    """Select an explicit dataset, or the bundled organizer; never an arbitrary upload."""
    if dataset_id is not None:
        dataset = session.get(DbDatasetSource, dataset_id)
    else:
        dataset = session.scalar(select(DbDatasetSource).where(
            DbDatasetSource.dataset_name == "treasury_4tier_dataset").order_by(DbDatasetSource.dataset_id).limit(1))
    if dataset is None:
        raise ValueError("Selected dataset was not found. Import the CSV before creating a simulation.")
    return dataset


def create_simulation_run(session: Session, request: CreateRunRequest, run_id: UUID | None = None,
                          *, source_start_timestamp: datetime | None = None) -> RunCreated:
    """Creates a new simulation run with default $20 million in Tier 0 checking."""
    ds = _get_or_load_dataset(session, request.dataset_id)
    policy_dict = request.policy.model_dump(mode="json")
    policy_dict.setdefault("scenarios", [])

    actual_run_id = run_id or uuid4()
    if source_start_timestamp is not None:
        if source_start_timestamp.tzinfo is not None:
            raise ValueError("Organizer source time has unspecified timezone; supply a naive source timestamp")
        if request.start_time is not None:
            raise ValueError("Supply source time or legacy start_time, not both")
        start_ts = source_start_timestamp
    else:
        # Legacy API compatibility: wall-clock source selection, NOT a claim
        # that organizer timestamps have UTC provenance.
        start_ts = request.start_time.replace(tzinfo=None) if request.start_time is not None else ds.first_timestamp
    if (start_ts.minute or start_ts.second or start_ts.microsecond
            or start_ts < ds.first_timestamp
            or start_ts + timedelta(hours=request.duration_steps - 1) > ds.last_timestamp):
        raise ValueError("Complete hourly run window must lie inside the organizer source")
    run = DbSimulationRun(
        id=actual_run_id,
        seed=request.seed,
        scenario=request.scenario.value,
        status="READY",
        current_step=0,
        duration_steps=request.duration_steps,
        initial_cash_cents=request.initial_cash_cents,
        policy_json=policy_dict,
        source_type="ORGANIZER_HISTORICAL",
        dataset_id=ds.dataset_id,
        source_start_timestamp=start_ts,
        source_end_timestamp=start_ts + timedelta(hours=request.duration_steps - 1),
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
        source_observation_timestamp=start_ts,
        balance_cents=request.initial_cash_cents,
    )
    session.add(cash)

    # Initial Portfolio Valuation
    pv = DbPortfolioValuation(
        id=uuid4(),
        run_id=run.id,
        source_type=run.source_type,
        dataset_id=run.dataset_id,
        source_observation_timestamp=start_ts,
        valued_at=start_ts,
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
        source_observation_timestamp=start_ts,
        event_at=start_ts,
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
    publication_delay_seconds = (run.policy_json or {}).get("publication_delay_seconds", 0)
    obs = get_published_observation(session, run.dataset_id, step_timestamp, publication_delay_seconds)
    reference = obs or session.get(DbOrganizerObservation, (run.dataset_id, run.source_start_timestamp))
    if reference is None:
        raise ValueError("Snapshot requires its persisted source provenance")

    (
        portfolio,
        cash_acc,
        db_repos,
        db_bonds,
        db_equities,
        db_overdrafts,
    ) = hydrate_portfolio_state(session, run, reference, as_of=step_timestamp, use_market_data=obs is not None)

    policy_dict = run.policy_json or {}
    policy_obj = build_four_tier_policy(policy_dict)

    # Repo positions
    active_repos = [r for r in db_repos if r.status in ("ACTIVE", "LOCKED")]
    tier1_principal = sum(r.principal_cents for r in active_repos)
    repo_apy_bps = int(obs.tier1_repo_rate_apy * 100) if obs else None
    tier1_accrued = sum(p.accrued_interest_cents or 0 for p in portfolio.repo_positions)
    tier1_break_fee_bps = 50
    tier1_break_fee_cents = sum(percentage_cost_cents(r.principal_cents, r.early_redemption_haircut_pct)
        for r in active_repos) if policy_obj.allow_early_repo_redemption else 0
    tier1_net_redeemable = max(0, tier1_principal - tier1_break_fee_cents) if policy_obj.allow_early_repo_redemption else 0

    # Bonds
    tier2_mkt_val = 0
    tier2_notional = 0
    tier2_unrealized = 0
    for b in db_bonds:
        cost_b = market_cost_basis(session, b)
        tier2_notional += cost_b
        mkt_val = b.current_market_value_cents or 0
        tier2_mkt_val += mkt_val
        tier2_unrealized += (mkt_val - cost_b)

    tier2_haircut_bps = int(obs.tier2_bond_liquidation_haircut_pct * 100) if obs else 200
    tier2_haircut_cents = percentage_cost_cents(tier2_mkt_val,
        obs.tier2_bond_liquidation_haircut_pct if obs else Decimal("2"))
    tier2_avail_liquidity = max(0, tier2_mkt_val - tier2_haircut_cents)

    # Equities
    tier3_mkt_val = 0
    tier3_cost_basis = 0
    tier3_unrealized = 0
    for eq in db_equities:
        cost_b = market_cost_basis(session, eq)
        tier3_cost_basis += cost_b
        mkt_val = eq.current_market_value_cents or 0
        tier3_mkt_val += mkt_val
        tier3_unrealized += (mkt_val - cost_b)

    tier3_slippage_bps = int(obs.tier3_stock_liquidation_haircut_pct * 100) if obs else 1500
    tier3_slippage_cents = percentage_cost_cents(tier3_mkt_val,
        obs.tier3_stock_liquidation_haircut_pct if obs else Decimal("15"))
    tier3_avail_liquidity = max(0, tier3_mkt_val - tier3_slippage_cents)

    # Overdraft
    od_borrowing = sum(od.outstanding_principal_cents for od in db_overdrafts)
    od_fees = sum(od.outstanding_financing_cost_cents for od in portfolio.overdrafts)
    total_liabilities = od_borrowing+od_fees

    gross_assets = portfolio.valuation.total_portfolio_value_cents
    net_value = portfolio.valuation.net_portfolio_value_cents
    realized_returns, net_benefit = financial_performance(session, run, net_value)

    latest_dec = session.scalar(select(DbTreasuryDecision).where(
        DbTreasuryDecision.run_id == run.id, DbTreasuryDecision.step == run.current_step))
    req_reserve = latest_dec.required_reserve_cents if latest_dec is not None else policy_obj.minimum_liquid_reserve_cents
    deployable_surplus = max(0, cash_acc.balance_cents - req_reserve)

    total_immediate_liquidity = (
        cash_acc.balance_cents
        + tier1_net_redeemable
        + tier2_avail_liquidity
        + tier3_avail_liquidity
    )

    four_tier_snapshot = FourTierPortfolioSnapshot(
        timestamp=step_timestamp.strftime("%Y-%m-%d %H:%M:%S"),
        market_data_available=obs is not None,
        market_observation_timestamp=obs.timestamp.isoformat() if obs else None,
        publication_delay_seconds=publication_delay_seconds,
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
            "repo_apy_decimal": str(obs.tier1_repo_rate_apy) if obs else None,
            "accrued_interest_cents": tier1_accrued,
            "realized_interest_cents": sum(p.realized_interest_cents or 0 for p in session.scalars(
                select(DbRepoPosition).where(DbRepoPosition.run_id == run.id))),
            "status": "LOCKED" if tier1_principal > 0 else "MATURED",
            "entry_window_open": step_timestamp.hour == 17,
            "early_redemption_allowed": policy_obj.allow_early_repo_redemption,
            "early_break_fee_bps": tier1_break_fee_bps,
            "break_fee_cents": tier1_break_fee_cents,
            "net_redeemable_cents": tier1_net_redeemable,
            "immediate_liquidity_cents": tier1_net_redeemable,
            "entry_time": "17:00",
            "maturity_time": "08:00",
            "maturity_timestamp": min(r.scheduled_maturity_at for r in active_repos).isoformat() if active_repos else None,
        },
        tier2={
            "tier": 2,
            "id": "BOND-SOV-1",
            "name": "Sovereign Bonds",
            "notional_cents": tier2_notional,
            "quantity": float(sum(b.quantity for b in db_bonds)) if db_bonds else 0.0,
            "acquisition_price": aggregate_acquisition_price(db_bonds),
            "current_price": str(obs.tier2_bond_price_index) if obs else None,
            "market_value_cents": tier2_mkt_val,
            "ytm_bps": int(obs.tier2_bond_yield_pct * 100) if obs else None,
            "ytm_decimal": str(obs.tier2_bond_yield_pct) if obs else None,
            "modified_duration": float(obs.tier2_bond_mod_duration) if obs else None,
            "liquidation_haircut_bps": tier2_haircut_bps,
            "haircut_cents": tier2_haircut_cents,
            "realized_pnl_cents": sum(v or 0 for v in session.scalars(select(DbBondPosition.realized_pnl_cents).where(
                DbBondPosition.run_id == run.id))),
            "unrealized_pnl_cents": tier2_unrealized,
            "available_liquidity_cents": tier2_avail_liquidity,
            "liquidity_status": "2-DAY_SETTLEMENT_OR_HAIRCUT",
        },
        tier3={
            "tier": 3,
            "id": "EQ-IDX-1",
            "name": "Growth Equities",
            "quantity": float(sum(eq.quantity for eq in db_equities)) if db_equities else 0.0,
            "acquisition_price": aggregate_acquisition_price(db_equities),
            "current_price": str(obs.tier3_stock_index_price) if obs else None,
            "market_value_cents": tier3_mkt_val,
            "cost_basis_cents": tier3_cost_basis,
            "volatility_bps": int(obs.tier3_stock_volatility_pct * 100) if obs else None,
            "volatility_decimal": str(obs.tier3_stock_volatility_pct) if obs else None,
            "emergency_slippage_bps": tier3_slippage_bps,
            "slippage_cents": tier3_slippage_cents,
            "realized_pnl_cents": sum(v or 0 for v in session.scalars(select(DbEquityPosition.realized_pnl_cents).where(
                DbEquityPosition.run_id == run.id))),
            "unrealized_pnl_cents": tier3_unrealized,
            "available_liquidity_cents": tier3_avail_liquidity,
            "liquidity_status": "MARKET_VOLATILITY_AND_SLIPPAGE",
        },
        overdraft={
            "borrowing_outstanding_cents": od_borrowing,
            "financing_rate_bps": int(obs.emergency_overdraft_penalty_apr_pct*100) if obs else None,
            "financing_cost_cents": od_fees,
            "liability_status": "ACTIVE" if total_liabilities > 0 else "CLEARED",
            "is_active": (total_liabilities > 0),
        },
        aggregates={
            "gross_assets_cents": gross_assets,
            "total_liabilities_cents": total_liabilities,
            "net_portfolio_value_cents": net_value,
            "total_immediate_liquidity_cents": total_immediate_liquidity,
            "total_realized_returns_cents": realized_returns,
            "total_unrealized_returns_cents": tier1_accrued + tier2_unrealized + tier3_unrealized,
            "net_financial_benefit_cents": net_benefit,
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
        model_version="hourly-seasonal-naive-v1",
    )

    dataset = session.get(DbDatasetSource, run.dataset_id)
    return SimulationSnapshot(
        duration_steps=run.duration_steps,
        source_dataset={
            "dataset_id": dataset.dataset_id, "row_count": dataset.row_count,
            "content_hash": dataset.content_hash, "uploaded": dataset.source_path.startswith("upload/"),
            "start_time": str(run.source_start_timestamp), "end_time": str(run.source_end_timestamp),
            "timezone_status": dataset.timezone_status,
        },
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
        policy=TreasuryPolicy(**{k: v for k, v in policy_dict.items() if k in TreasuryPolicy.model_fields}),
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
    if patch_dict.get("allow_overdraft") is False and "max_overdraft_cents" not in patch_dict:
        policy_json["max_overdraft_cents"] = 0
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
        session, run.dataset_id, step_timestamp, horizon_hours=horizon_hours,
        publication_delay_seconds=(run.policy_json or {}).get("publication_delay_seconds", 0),
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
        model_version="hourly-seasonal-naive-v1",
        points=points,
        summary=ForecastSummary(
            horizon_minutes=horizon_minutes,
            peak_shortfall_cents=0,
            uncertainty_buffer_cents=points[0].upper_cents - points[0].predicted_net_cents if points else 0,
            operational_buffer_cents=50000000,
            model_version="hourly-seasonal-naive-v1",
        ),
    )
