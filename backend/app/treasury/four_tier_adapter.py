"""Four-tier treasury integration adapter.

Connects Member 1's quantitative intelligence (liquidity risk calculation,
portfolio state contracts, and hourly forecasting) to Member 2's relational
persistence layer (four-tier positions, audited movements, ledger entries,
and portfolio valuations).

Zero floats: all monetary ledger values are integer cents.
All prices, rates, and yields preserve Decimal precision.
Historical timestamps remain naive (UNSPECIFIED time basis).
"""

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Tuple
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
    RepoPosition as DbRepoPosition,
    SimulationRun as DbSimulationRun,
    TreasuryDecision as DbTreasuryDecision,
)
from treasury_intelligence.hourly_forecasting import forecast_hourly_cashflows
from treasury_intelligence.liquidity_risk import (
    CalibratedForecastAllowance,
    FourTierLiquidityRiskRequest,
    FourTierLiquidityRiskResult,
    RepoCashSettlement,
    calculate_four_tier_liquidity_risk,
)
from treasury_intelligence.portfolio import (
    BondPosition as M1BondPosition,
    CashPosition as M1CashPosition,
    EquityPosition as M1EquityPosition,
    FourTierTreasuryPolicy,
    HourlyForecastPoint,
    MarketPriceObservation,
    MarketRateObservation,
    OverdraftLiability as M1OverdraftLiability,
    PortfolioState,
    PortfolioValuation as M1PortfolioValuation,
    PositionLiquidity,
    RepoPosition as M1RepoPosition,
)


def build_four_tier_policy(
    policy_dict: dict,
    repo_sweep_window_open: bool = False,
) -> FourTierTreasuryPolicy:
    """Constructs Member 1's FourTierTreasuryPolicy from a run's policy dict."""
    return FourTierTreasuryPolicy(
        base_buffer_cents=policy_dict.get(
            "base_buffer_cents",
            policy_dict.get("operational_buffer_cents", 50000000),
        ),
        uncertainty_multiplier_bps=policy_dict.get(
            "uncertainty_multiplier_bps", 19600
        ),
        tolerance_bps=policy_dict.get("tolerance_bps", 500),
        min_transfer_cents=policy_dict.get(
            "min_transfer_cents",
            policy_dict.get("minimum_sweep_cents", 1000000),
        ),
        max_allocation_bps=policy_dict.get("max_allocation_bps", 10000),
        repo_sweep_window_open=repo_sweep_window_open,
        allow_early_repo_redemption=policy_dict.get(
            "allow_early_repo_redemption",
            policy_dict.get("early_redemption_allowed", True),
        ),
        minimum_liquid_reserve_cents=policy_dict.get(
            "minimum_liquid_reserve_cents", 50000000
        ),
        allow_overdraft=policy_dict.get("allow_overdraft", True),
        max_overdraft_cents=policy_dict.get("max_overdraft_cents", 5000000000),
    )


def hydrate_portfolio_state(
    session: Session,
    run: DbSimulationRun,
    observation: DbOrganizerObservation,
) -> Tuple[PortfolioState, DbCashAccount, list[DbRepoPosition], list[DbBondPosition], list[DbEquityPosition], list[DbOverdraftLiability]]:
    """Hydrates Member 1's canonical PortfolioState from Member 2's database tables."""
    time_basis = "UNSPECIFIED" if run.source_type == "ORGANIZER_HISTORICAL" else "UTC"
    as_of = observation.timestamp
    src_obs_time = as_of if run.source_type == "ORGANIZER_HISTORICAL" else None

    # 1. Tier 0 Cash
    cash_acc = session.scalar(select(DbCashAccount).where(DbCashAccount.run_id == run.id))
    if cash_acc is None:
        raise ValueError(f"No CashAccount found for run {run.id}")

    cash_cents = cash_acc.balance_cents
    m1_cash = M1CashPosition(
        id=cash_acc.id,
        run_id=run.id,
        source_type=run.source_type,
        dataset_id=run.dataset_id,
        time_basis=time_basis,
        source_observation_timestamp=src_obs_time,
        balance_cents=cash_cents,
        last_ledger_entry_id=cash_acc.last_ledger_entry_id,
        liquidity=PositionLiquidity(
            classification="IMMEDIATE",
            available_cents=cash_cents,
            locked_cents=0,
            liquidatable_value_cents=cash_cents,
        ),
    )

    # 2. Tier 1 Repo Positions
    db_repos = list(
        session.scalars(
            select(DbRepoPosition).where(
                DbRepoPosition.run_id == run.id,
                DbRepoPosition.status.in_(["LOCKED", "MATURED"]),
            ).order_by(DbRepoPosition.entered_at)
        ).all()
    )

    m1_repos: list[M1RepoPosition] = []
    for r in db_repos:
        if r.status == "LOCKED":
            dur_hrs = max(
                0,
                int(
                    (min(as_of, r.scheduled_maturity_at) - r.entered_at).total_seconds()
                    // 3600
                ),
            )
            accrued = int(
                round(
                    r.principal_cents
                    * (r.applicable_apy_pct / Decimal(100))
                    * Decimal(dur_hrs)
                    / Decimal(365 * 24)
                )
            )
            market_val = r.principal_cents + accrued
            avail = 0
            locked = market_val
            haircut_pct = r.early_redemption_haircut_pct
            liquidatable = int(round(market_val * (Decimal(100) - haircut_pct) / Decimal(100)))
            cls_name = "LOCKED"
        else:  # MATURED
            accrued = r.realized_interest_cents or r.accrued_interest_cents or 0
            market_val = r.principal_cents + accrued
            avail = market_val
            locked = 0
            liquidatable = market_val
            cls_name = "IMMEDIATE"

        m1_repos.append(
            M1RepoPosition(
                id=r.id,
                run_id=run.id,
                source_type=run.source_type,
                dataset_id=run.dataset_id,
                time_basis=time_basis,
                source_observation_timestamp=src_obs_time,
                principal_cents=r.principal_cents,
                entered_at=r.entered_at,
                scheduled_maturity_at=r.scheduled_maturity_at,
                applicable_apy_pct=r.applicable_apy_pct,
                status=r.status,
                early_redemption_haircut_pct=r.early_redemption_haircut_pct,
                market_value_cents=market_val,
                accrued_interest_cents=accrued,
                liquidity=PositionLiquidity(
                    classification=cls_name,
                    available_cents=avail,
                    locked_cents=locked,
                    liquidatable_value_cents=liquidatable,
                ),
            )
        )

    # 3. Tier 2 Bonds
    db_bonds = list(
        session.scalars(
            select(DbBondPosition).where(
                DbBondPosition.run_id == run.id,
                DbBondPosition.status == "OPEN",
            ).order_by(DbBondPosition.acquired_at)
        ).all()
    )
    m1_bonds: list[M1BondPosition] = []
    for b in db_bonds:
        # Marked to current market price index
        cur_price = observation.tier2_bond_price_index
        cur_market_val = int(round(b.quantity * cur_price * Decimal(100)))
        haircut = b.liquidation_haircut_pct
        liq_val = int(round(cur_market_val * (Decimal(100) - haircut) / Decimal(100)))
        m1_bonds.append(
            M1BondPosition(
                id=b.id,
                run_id=run.id,
                source_type=run.source_type,
                dataset_id=run.dataset_id,
                time_basis=time_basis,
                source_observation_timestamp=src_obs_time,
                quantity=b.quantity,
                acquisition_price_index=b.acquisition_price_index,
                acquired_at=b.acquired_at,
                current_market_price_index=cur_price,
                current_market_value_cents=cur_market_val,
                supplied_yield_pct=b.supplied_yield_pct,
                modified_duration=b.modified_duration,
                liquidation_haircut_pct=haircut,
                status=b.status,
                liquidity=PositionLiquidity(
                    classification="LIQUIDATABLE",
                    available_cents=0,
                    locked_cents=0,
                    liquidatable_value_cents=liq_val,
                ),
            )
        )

    # 4. Tier 3 Equities
    db_equities = list(
        session.scalars(
            select(DbEquityPosition).where(
                DbEquityPosition.run_id == run.id,
                DbEquityPosition.status == "OPEN",
            ).order_by(DbEquityPosition.acquired_at)
        ).all()
    )
    m1_equities: list[M1EquityPosition] = []
    for eq in db_equities:
        cur_price = observation.tier3_stock_index_price
        cur_market_val = int(round(eq.quantity * cur_price * Decimal(100)))
        haircut = eq.liquidation_haircut_pct
        liq_val = int(round(cur_market_val * (Decimal(100) - haircut) / Decimal(100)))
        m1_equities.append(
            M1EquityPosition(
                id=eq.id,
                run_id=run.id,
                source_type=run.source_type,
                dataset_id=run.dataset_id,
                time_basis=time_basis,
                source_observation_timestamp=src_obs_time,
                quantity=eq.quantity,
                acquisition_price_index=eq.acquisition_price_index,
                acquired_at=eq.acquired_at,
                current_market_price_index=cur_price,
                current_market_value_cents=cur_market_val,
                supplied_volatility_pct=eq.supplied_volatility_pct,
                liquidation_haircut_pct=haircut,
                status=eq.status,
                liquidity=PositionLiquidity(
                    classification="LIQUIDATABLE",
                    available_cents=0,
                    locked_cents=0,
                    liquidatable_value_cents=liq_val,
                ),
            )
        )

    # 5. Overdraft Liabilities
    db_overdrafts = list(
        session.scalars(
            select(DbOverdraftLiability).where(
                DbOverdraftLiability.run_id == run.id,
                DbOverdraftLiability.outstanding_principal_cents > 0,
            ).order_by(DbOverdraftLiability.borrowed_at)
        ).all()
    )
    m1_overdrafts: list[M1OverdraftLiability] = []
    for od in db_overdrafts:
        fin_cost = od.financing_cost_cents or 0
        m1_overdrafts.append(
            M1OverdraftLiability(
                id=od.id,
                run_id=run.id,
                source_type=run.source_type,
                dataset_id=run.dataset_id,
                time_basis=time_basis,
                source_observation_timestamp=src_obs_time,
                borrowed_at=od.borrowed_at,
                borrowed_cents=od.borrowed_cents,
                outstanding_principal_cents=od.outstanding_principal_cents,
                repaid_principal_cents=od.repaid_principal_cents,
                apr_pct=od.apr_pct,
                financing_cost_cents=fin_cost,
                paid_financing_cost_cents=0,
                outstanding_financing_cost_cents=fin_cost,
                breach_id=od.breach_id,
                reference_id=od.reference_id,
            )
        )

    # 6. Reconcile Balance Sheet Valuation
    all_positions = (m1_cash, *m1_repos, *m1_bonds, *m1_equities)
    t0_cents = m1_cash.balance_cents
    t1_principal = sum(p.principal_cents for p in m1_repos)
    t1_val = sum(p.market_value_cents for p in m1_repos)
    t2_val = sum(p.current_market_value_cents for p in m1_bonds)
    t3_val = sum(p.current_market_value_cents for p in m1_equities)
    total_val = t0_cents + t1_val + t2_val + t3_val

    imm_avail = sum(p.liquidity.available_cents for p in all_positions)
    liquidatable = sum(p.liquidity.liquidatable_value_cents for p in all_positions)
    restricted = sum(p.liquidity.locked_cents for p in all_positions)
    total_liabilities = sum(
        o.outstanding_principal_cents + o.outstanding_financing_cost_cents
        for o in m1_overdrafts
    )
    net_val = total_val - total_liabilities

    m1_val = M1PortfolioValuation(
        run_id=run.id,
        source_type=run.source_type,
        dataset_id=run.dataset_id,
        time_basis=time_basis,
        source_observation_timestamp=src_obs_time,
        valued_at=as_of,
        tier0_cash_cents=t0_cents,
        tier1_principal_cents=t1_principal,
        tier1_value_cents=t1_val,
        tier2_market_value_cents=t2_val,
        tier3_market_value_cents=t3_val,
        total_portfolio_value_cents=total_val,
        immediately_available_cents=imm_avail,
        liquidatable_value_cents=liquidatable,
        restricted_value_cents=restricted,
        liabilities_cents=total_liabilities,
        net_portfolio_value_cents=net_val,
        reference_id=f"val-{run.id}-{as_of.strftime('%Y%m%d%H%M%S')}",
    )

    # 7. Market Rates & Prices
    market_rates = MarketRateObservation(
        time_basis=time_basis,
        observed_at=as_of,
        repo_apy_pct=observation.tier1_repo_rate_apy,
        bond_yield_pct=observation.tier2_bond_yield_pct,
        equity_volatility_pct=observation.tier3_stock_volatility_pct,
        overdraft_apr_pct=observation.emergency_overdraft_penalty_apr_pct,
    )
    market_prices = MarketPriceObservation(
        time_basis=time_basis,
        observed_at=as_of,
        bond_price_index=observation.tier2_bond_price_index,
        bond_modified_duration_years=observation.tier2_bond_mod_duration,
        equity_index_price=observation.tier3_stock_index_price,
    )

    state = PortfolioState(
        run_id=run.id,
        source_type=run.source_type,
        dataset_id=run.dataset_id,
        time_basis=time_basis,
        source_observation_timestamp=src_obs_time,
        as_of=as_of,
        native_interval_seconds=run.native_interval_seconds or 3600,
        currency="USD",
        cash=m1_cash,
        repo_positions=tuple(m1_repos),
        bond_positions=tuple(m1_bonds),
        equity_positions=tuple(m1_equities),
        overdrafts=tuple(m1_overdrafts),
        valuation=m1_val,
        market_rates=market_rates,
        market_prices=market_prices,
    )

    return state, cash_acc, db_repos, db_bonds, db_equities, db_overdrafts


def get_information_cutoff(as_of: datetime) -> datetime:
    """Returns the strict causal observation-availability cutoff for decision time as_of.

    Organizer timestamps have unspecified timezone and publication semantics.
    A row timestamped T records the aggregated flows that occurred during hour T.
    Those complete hourly flows are finalized and available only after hour T closes (at T + 1 hour).
    Therefore, at decision timestamp `as_of`, the latest fully observed and published
    hourly observation is `as_of - timedelta(hours=1)`.
    """
    return as_of - timedelta(hours=1)


def generate_hourly_forecast_points(
    session: Session,
    dataset_id: str,
    as_of: datetime,
    horizon_hours: int = 24,
) -> tuple[HourlyForecastPoint, ...]:
    """Generates the forward hourly forecast path for liquidity risk evaluation causally without lookahead."""
    cutoff = get_information_cutoff(as_of)
    history = list(
        session.scalars(
            select(DbOrganizerObservation)
            .where(
                DbOrganizerObservation.dataset_id == dataset_id,
                DbOrganizerObservation.timestamp <= cutoff,
            )
            .order_by(DbOrganizerObservation.timestamp.asc())
        ).all()
    )

    for obs in history:
        if obs.timestamp > cutoff:
            raise ValueError(
                f"Causal violation: observation at {obs.timestamp} is after cutoff {cutoff}"
            )

    result = forecast_hourly_cashflows(
        history,
        as_of=as_of,
        horizon_hours=horizon_hours,
        start_at=as_of,
    )
    points: list[HourlyForecastPoint] = []
    for p in result.points:
        points.append(
            HourlyForecastPoint(
                time_basis="UNSPECIFIED",
                start_at=p.start_at,
                predicted_deposits_cents=p.predicted_deposits_cents,
                predicted_withdrawals_cents=p.predicted_withdrawals_cents,
                predicted_net_flow_cents=p.predicted_net_flow_cents,
                supplied_uncertainty_buffer_cents=p.supplied_uncertainty_buffer_cents,
            )
        )
    return tuple(points)


def evaluate_liquidity_risk(
    portfolio: PortfolioState,
    policy: FourTierTreasuryPolicy,
    forecast: tuple[HourlyForecastPoint, ...],
    calibrated_allowance: CalibratedForecastAllowance | None = None,
) -> FourTierLiquidityRiskResult:
    """Invokes Member 1's calculate_four_tier_liquidity_risk engine with causal validation."""
    cutoff = get_information_cutoff(portfolio.as_of)
    if calibrated_allowance is not None and calibrated_allowance.calibrated_through > cutoff:
        raise ValueError(
            f"Calibration artifact dated {calibrated_allowance.calibrated_through} "
            f"is after information cutoff {cutoff} (lookahead breach)"
        )
    repo_settlements = tuple(
        RepoCashSettlement(
            time_basis=portfolio.time_basis,
            position_id=p.id,
            available_at=p.scheduled_maturity_at,
            amount_cents=p.principal_cents + (p.accrued_interest_cents or 0),
            already_in_cash=False,
        )
        for p in portfolio.repo_positions
        if p.status == "LOCKED" and p.scheduled_maturity_at <= portfolio.as_of + timedelta(hours=len(forecast))
    )

    req = FourTierLiquidityRiskRequest(
        portfolio=portfolio,
        policy=policy,
        forecast=forecast,
        planning_horizon_hours=len(forecast),
        uncertainty_mode="calibrated_allowance",
        calibrated_allowance=CalibratedForecastAllowance(
            time_basis=portfolio.time_basis,
            amount_cents=policy.base_buffer_cents,
            confidence=Decimal("0.95"),
            calibration_reference="calibrated-baseline",
            calibrated_through=portfolio.as_of,
        ),
        repo_settlements=repo_settlements,
    )
    return calculate_four_tier_liquidity_risk(req)


def step_simulation_hour(session: Session, run_id: UUID) -> dict[str, Any]:
    """Advances the simulation by one hourly step.
    
    1. Loads current observation for the step.
    2. Redems mature Tier 1 Repos (08:00) with accrued interest.
    3. Posts customer deposits/withdrawals to Tier 0 Cash.
    4. Handles shortfall via emergency Overdraft (logging a Liquidity Breach).
    5. Repays overdrafts if surplus cash is available.
    6. Executes Tier 1 Repo Sweeps (17:00) if safe surplus above reserve exists.
    7. Revalues portfolio across all 4 tiers and persists decision and audit trail.
    """
    run = session.scalar(select(DbSimulationRun).where(DbSimulationRun.id == run_id))
    if run is None:
        raise ValueError(f"Run {run_id} not found")

    step = run.current_step
    # Determine observation timestamp for this step
    start_ts = run.source_start_timestamp
    if start_ts is None:
        raise ValueError(f"Run {run_id} does not have source_start_timestamp")

    step_ts = start_ts + timedelta(hours=step)
    observation = session.scalar(
        select(DbOrganizerObservation).where(
            DbOrganizerObservation.dataset_id == run.dataset_id,
            DbOrganizerObservation.timestamp == step_ts,
        )
    )
    if observation is None:
        raise ValueError(f"No observation found for dataset {run.dataset_id} at {step_ts}")

    # A. Hydrate State
    (
        portfolio_state,
        cash_acc,
        db_repos,
        db_bonds,
        db_equities,
        db_overdrafts,
    ) = hydrate_portfolio_state(session, run, observation)

    # B. Hydrate Policy & Forecast, Call Member 1 Risk Engine
    policy = build_four_tier_policy(
        run.policy_json or {},
        repo_sweep_window_open=observation.repo_sweep_window_open,
    )
    horizon = int((run.policy_json or {}).get("planning_horizon_hours", 4))
    forecast = generate_hourly_forecast_points(
        session, run.dataset_id, observation.timestamp, horizon_hours=horizon
    )
    risk_result = evaluate_liquidity_risk(portfolio_state, policy, forecast)
    required_reserve = risk_result.reserve.required_reserve_cents

    cash_cents = cash_acc.balance_cents
    action_taken = "HOLD"
    action_amount_cents = 0
    orders_executed = []
    breach_occurred = False
    overdraft_borrowed_cents = 0

    # C. Rule 4: Mature Tier 1 Repos scheduled at or before this hour
    for repo in db_repos:
        if repo.status == "LOCKED" and observation.timestamp >= repo.scheduled_maturity_at:
            dur_hrs = max(
                1,
                int((repo.scheduled_maturity_at - repo.entered_at).total_seconds() // 3600),
            )
            interest = int(
                round(
                    repo.principal_cents
                    * (repo.applicable_apy_pct / Decimal(100))
                    * Decimal(dur_hrs)
                    / Decimal(365 * 24)
                )
            )
            proceeds = repo.principal_cents + interest

            # Update Repo
            repo.status = "REDEEMED"
            repo.realized_interest_cents = interest
            repo.proceeds_returned_cents = proceeds

            # Update Cash
            old_cash = cash_cents
            cash_cents += proceeds

            # Ledger & Movement Audit
            ref = f"repo-mature-{repo.id}-{step}"
            ledger = DbLedgerEntry(
                id=uuid4(),
                run_id=run.id,
                step=step,
                event_at=observation.timestamp,
                entry_type="REPO_MATURITY",
                amount_cents=proceeds,
                balance_before_cents=old_cash,
                balance_after_cents=cash_cents,
                reference_id=ref,
                source_type=run.source_type,
                dataset_id=run.dataset_id,
                source_observation_timestamp=observation.timestamp,
            )
            session.add(ledger)
            session.flush()

            movement = DbInvestmentMovement(
                id=uuid4(),
                run_id=run.id,
                source_type=run.source_type,
                dataset_id=run.dataset_id,
                source_observation_timestamp=observation.timestamp,
                kind="MATURITY",
                occurred_at=observation.timestamp,
                cash_delta_cents=proceeds,
                principal_cents=repo.principal_cents,
                interest_cents=interest,
                haircut_cost_cents=0,
                ledger_entry_id=ledger.id,
                reference_id=ref,
                tier=1,
                repo_position_id=repo.id,
            )
            session.add(movement)
            action_taken = "WITHDRAW"
            action_amount_cents = proceeds
            orders_executed.append(
                {"action": "REDEEM_REPO", "amount_cents": proceeds, "repo_id": str(repo.id)}
            )

    # D. Customer Cash Flows for the hour
    inflows = int(round(observation.deposits_usd * Decimal(100)))
    outflows = int(round(observation.withdrawals_usd * Decimal(100)))
    net_flow = inflows - outflows

    old_cash = cash_cents
    cash_cents += net_flow
    ref_flow = f"flow-{run.id}-{step}"
    ledger_flow = DbLedgerEntry(
        id=uuid4(),
        run_id=run.id,
        step=step,
        event_at=observation.timestamp,
        entry_type="CUSTOMER_NET_FLOW",
        amount_cents=abs(net_flow),
        balance_before_cents=old_cash,
        balance_after_cents=max(0, cash_cents),
        reference_id=ref_flow,
        source_type=run.source_type,
        dataset_id=run.dataset_id,
        source_observation_timestamp=observation.timestamp,
    )
    session.add(ledger_flow)
    session.flush()

    # E. Rule 6: Handle Liquidity Shortfall / Negative Cash -> Emergency Overdraft
    if cash_cents < 0:
        shortfall = -cash_cents
        breach_occurred = True
        overdraft_borrowed_cents = shortfall

        breach_ref = f"breach-{run.id}-{step}"
        breach = DbLiquidityBreach(
            id=uuid4(),
            run_id=run.id,
            source_type=run.source_type,
            dataset_id=run.dataset_id,
            source_observation_timestamp=observation.timestamp,
            occurred_at=observation.timestamp,
            shortfall_cents=shortfall,
            description=f"Negative cash drain of {shortfall} cents; triggered overdraft.",
            reference_id=breach_ref,
        )
        session.add(breach)
        session.flush()

        od_ref = f"overdraft-{run.id}-{step}"
        od_liability = DbOverdraftLiability(
            id=uuid4(),
            run_id=run.id,
            source_type=run.source_type,
            dataset_id=run.dataset_id,
            source_observation_timestamp=observation.timestamp,
            borrowed_at=observation.timestamp,
            borrowed_cents=shortfall,
            outstanding_principal_cents=shortfall,
            repaid_principal_cents=0,
            apr_pct=observation.emergency_overdraft_penalty_apr_pct,
            financing_cost_cents=0,
            breach_id=breach.id,
            reference_id=od_ref,
        )
        session.add(od_liability)
        session.flush()

        old_cash = cash_cents
        cash_cents = 0  # Replaced by borrowed overdraft liability

        od_ledger = DbLedgerEntry(
            id=uuid4(),
            run_id=run.id,
            step=step,
            event_at=observation.timestamp,
            entry_type="OVERDRAFT_BORROW",
            amount_cents=shortfall,
            balance_before_cents=0,
            balance_after_cents=0,
            reference_id=f"od-borrow-{run.id}-{step}",
            source_type=run.source_type,
            dataset_id=run.dataset_id,
            source_observation_timestamp=observation.timestamp,
        )
        session.add(od_ledger)
        session.flush()

        od_mov = DbOverdraftMovement(
            id=uuid4(),
            run_id=run.id,
            source_type=run.source_type,
            dataset_id=run.dataset_id,
            source_observation_timestamp=observation.timestamp,
            liability_id=od_liability.id,
            occurred_at=observation.timestamp,
            kind="BORROW",
            principal_cents=shortfall,
            financing_cost_cents=0,
            cash_delta_cents=shortfall,
            ledger_entry_id=od_ledger.id,
            reference_id=f"od-mov-{run.id}-{step}",
        )
        session.add(od_mov)
        action_taken = "LIQUIDITY_WARNING"
        action_amount_cents = shortfall
        orders_executed.append(
            {"action": "BORROW_OVERDRAFT", "amount_cents": shortfall, "liability_id": str(od_liability.id)}
        )

    # F. Repay existing overdrafts if surplus cash is available
    if cash_cents > required_reserve:
        surplus = cash_cents - required_reserve
        for od in db_overdrafts:
            if od.outstanding_principal_cents > 0 and surplus > 0:
                repay = min(surplus, od.outstanding_principal_cents)
                od.outstanding_principal_cents -= repay
                od.repaid_principal_cents += repay
                old_cash = cash_cents
                cash_cents -= repay
                surplus -= repay

                ref_repay = f"od-repay-{od.id}-{step}"
                repay_ledger = DbLedgerEntry(
                    id=uuid4(),
                    run_id=run.id,
                    step=step,
                    event_at=observation.timestamp,
                    entry_type="OVERDRAFT_REPAYMENT",
                    amount_cents=repay,
                    balance_before_cents=old_cash,
                    balance_after_cents=cash_cents,
                    reference_id=ref_repay,
                    source_type=run.source_type,
                    dataset_id=run.dataset_id,
                    source_observation_timestamp=observation.timestamp,
                )
                session.add(repay_ledger)
                session.flush()

                session.add(
                    DbOverdraftMovement(
                        id=uuid4(),
                        run_id=run.id,
                        source_type=run.source_type,
                        dataset_id=run.dataset_id,
                        source_observation_timestamp=observation.timestamp,
                        liability_id=od.id,
                        occurred_at=observation.timestamp,
                        kind="REPAYMENT",
                        principal_cents=repay,
                        financing_cost_cents=0,
                        cash_delta_cents=-repay,
                        ledger_entry_id=repay_ledger.id,
                        reference_id=f"od-repay-mov-{od.id}-{step}",
                    )
                )

    # G. Rule 3: Tier 1 Repo Sweep at 17:00 if safe surplus above reserve exists
    if observation.repo_sweep_window_open and cash_cents > required_reserve:
        surplus = cash_cents - required_reserve
        min_sweep = policy.min_transfer_cents
        if surplus >= min_sweep:
            sweep_cents = surplus
            old_cash = cash_cents
            cash_cents -= sweep_cents

            repo_id = uuid4()
            sweep_ref = f"repo-sweep-{repo_id}-{step}"
            sweep_ledger = DbLedgerEntry(
                id=uuid4(),
                run_id=run.id,
                step=step,
                event_at=observation.timestamp,
                entry_type="REPO_INVEST",
                amount_cents=sweep_cents,
                balance_before_cents=old_cash,
                balance_after_cents=cash_cents,
                reference_id=sweep_ref,
                source_type=run.source_type,
                dataset_id=run.dataset_id,
                source_observation_timestamp=observation.timestamp,
            )
            session.add(sweep_ledger)
            session.flush()

            new_repo = DbRepoPosition(
                id=repo_id,
                run_id=run.id,
                source_type=run.source_type,
                dataset_id=run.dataset_id,
                source_observation_timestamp=observation.timestamp,
                principal_cents=sweep_cents,
                entered_at=observation.timestamp,
                scheduled_maturity_at=observation.timestamp + timedelta(hours=15),
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
                    source_type=run.source_type,
                    dataset_id=run.dataset_id,
                    source_observation_timestamp=observation.timestamp,
                    kind="INVESTMENT",
                    occurred_at=observation.timestamp,
                    cash_delta_cents=-sweep_cents,
                    principal_cents=sweep_cents,
                    interest_cents=0,
                    haircut_cost_cents=0,
                    ledger_entry_id=sweep_ledger.id,
                    reference_id=sweep_ref,
                    tier=1,
                    repo_position_id=new_repo.id,
                )
            )
            action_taken = "SWEEP"
            action_amount_cents = sweep_cents
            orders_executed.append(
                {"action": "INVEST_REPO", "amount_cents": sweep_cents, "repo_id": str(new_repo.id)}
            )

    # H. Revalue and Persist End-of-Hour Balances
    cash_acc.balance_cents = cash_cents
    session.flush()

    # Re-query active repos and liabilities
    active_repos = list(
        session.scalars(
            select(DbRepoPosition).where(
                DbRepoPosition.run_id == run.id,
                DbRepoPosition.status == "LOCKED",
            )
        ).all()
    )
    active_ods = list(
        session.scalars(
            select(DbOverdraftLiability).where(
                DbOverdraftLiability.run_id == run.id,
                DbOverdraftLiability.outstanding_principal_cents > 0,
            )
        ).all()
    )

    t0 = cash_cents
    t1_p = sum(r.principal_cents for r in active_repos)
    t1_v = t1_p  # Locked repo principal is current baseline value
    t2_v = sum(
        int(round(b.quantity * observation.tier2_bond_price_index * Decimal(100)))
        for b in db_bonds
    )
    t3_v = sum(
        int(round(eq.quantity * observation.tier3_stock_index_price * Decimal(100)))
        for eq in db_equities
    )
    total_val = t0 + t1_v + t2_v + t3_v
    total_liab = sum(o.outstanding_principal_cents + (o.financing_cost_cents or 0) for o in active_ods)
    net_val = total_val - total_liab

    imm_avail = t0
    restr_val = t1_v
    liq_val = (
        sum(int(round(r.principal_cents * (Decimal(100) - r.early_redemption_haircut_pct) / Decimal(100))) for r in active_repos)
        + sum(int(round(b.quantity * observation.tier2_bond_price_index * Decimal(100) * (Decimal(100) - b.liquidation_haircut_pct) / Decimal(100))) for b in db_bonds)
        + sum(int(round(eq.quantity * observation.tier3_stock_index_price * Decimal(100) * (Decimal(100) - eq.liquidation_haircut_pct) / Decimal(100))) for eq in db_equities)
    )

    pv = DbPortfolioValuation(
        id=uuid4(),
        run_id=run.id,
        source_type=run.source_type,
        dataset_id=run.dataset_id,
        source_observation_timestamp=observation.timestamp,
        valued_at=observation.timestamp,
        tier0_cash_cents=t0,
        tier1_principal_cents=t1_p,
        tier1_value_cents=t1_v,
        tier2_market_value_cents=t2_v,
        tier3_market_value_cents=t3_v,
        total_portfolio_value_cents=total_val,
        immediately_available_cents=imm_avail,
        liquidatable_value_cents=liq_val,
        restricted_value_cents=restr_val,
        liabilities_cents=total_liab,
        net_portfolio_value_cents=net_val,
        reference_id=f"val-{run.id}-{step}",
    )
    session.add(pv)

    # Persist Treasury Decision
    decision = DbTreasuryDecision(
        id=uuid4(),
        run_id=run.id,
        step=step,
        action=action_taken,
        amount_cents=action_amount_cents,
        execution_status="EXECUTED",
        explanation_json={"orders": orders_executed, "net_flow_cents": net_flow},
        decision_details_json={"risk_summary": risk_result.model_dump(mode="json")},
        dataset_id=run.dataset_id,
        source_type=run.source_type,
        source_observation_timestamp=observation.timestamp,
        tier0_target_cents=t0,
        tier1_allocation_cents=t1_v,
        tier2_allocation_cents=t2_v,
        tier3_allocation_cents=t3_v,
        required_reserve_cents=required_reserve,
        available_liquidity_cents=t0,
        expected_inflow_cents=inflows,
        expected_outflow_cents=outflows,
        uncertainty_cents=policy.base_buffer_cents,
    )
    session.add(decision)

    # Advance Run
    run.current_step = step + 1
    session.flush()

    return {
        "run_id": str(run.id),
        "step": step,
        "timestamp": observation.timestamp.isoformat(),
        "tier0_cash_cents": t0,
        "tier1_value_cents": t1_v,
        "tier2_market_value_cents": t2_v,
        "tier3_market_value_cents": t3_v,
        "total_portfolio_value_cents": total_val,
        "liabilities_cents": total_liab,
        "net_portfolio_value_cents": net_val,
        "required_reserve_cents": required_reserve,
        "available_liquidity_cents": t0,
        "action_taken": action_taken,
        "action_amount_cents": action_amount_cents,
        "breach_occurred": breach_occurred,
        "overdraft_borrowed_cents": overdraft_borrowed_cents,
        "orders_executed": orders_executed,
    }
