"""Four-tier treasury integration adapter for Member 1 quantitative intelligence.

Provides high-level bridges between database entities and Member 1's:
1. Canonical PortfolioState and FourTierTreasuryPolicy contracts.
2. calculate_four_tier_liquidity_risk calculation engine.
3. forecast_hourly_cashflows machine learning prediction pipeline.
4. recommend_four_tier_allocation constrained portfolio allocation optimizer.

Financial invariants:
- Zero floats: all balance sheet amounts and valuations are strict integer cents.
- All prices, rates, yields, and fractions preserve exact Decimal precision.
- Historical observation timestamps remain naive (UNSPECIFIED time basis).
"""

from datetime import datetime, timedelta
from contextlib import contextmanager
from decimal import Decimal
from typing import Any, Tuple, NamedTuple
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session
from app.services.accounting import market_cost_basis, paid_financing_costs, repo_interest_cents
from treasury_intelligence.instrument_economics import usd_to_ledger_cents, percentage_cost_cents

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
from treasury_intelligence.optimizer import (
    AllocationOptimizerRequest,
    AllocationOptimizerResult,
    AllocationRewardModel,
    AssetRewardAssumption,
    recommend_four_tier_allocation,
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
        allow_bond_liquidation=policy_dict.get("allow_bond_liquidation", False),
        allow_emergency_equity_liquidation=policy_dict.get("allow_emergency_equity_liquidation", False),
        max_overdraft_cents=policy_dict.get("max_overdraft_cents",
            5000000000 if policy_dict.get("allow_overdraft", True) else 0),
    )


def hydrate_portfolio_state(
    session: Session,
    run: DbSimulationRun,
    observation: DbOrganizerObservation,
    *, as_of: datetime | None = None, use_market_data: bool = True,
) -> Tuple[PortfolioState, DbCashAccount, list[DbRepoPosition], list[DbBondPosition], list[DbEquityPosition], list[DbOverdraftLiability]]:
    """Hydrates Member 1's canonical PortfolioState from Member 2's database tables."""
    time_basis = "UNSPECIFIED" if run.source_type == "ORGANIZER_HISTORICAL" else "UTC"
    as_of = as_of or observation.timestamp
    src_obs_time = observation.timestamp if run.source_type == "ORGANIZER_HISTORICAL" else None

    # 1. Tier 0 Cash
    cash_acc = session.scalar(select(DbCashAccount).where(DbCashAccount.run_id == run.id))
    if cash_acc is None:
        cash_acc = DbCashAccount(
            id=uuid4(),
            run_id=run.id,
            source_type=run.source_type,
            dataset_id=run.dataset_id,
            source_observation_timestamp=src_obs_time,
            balance_cents=run.initial_cash_cents,
        )
        session.add(cash_acc)
        session.flush()

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
                DbRepoPosition.status == "LOCKED",
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
            accrued = repo_interest_cents(session, r, as_of,
                (run.policy_json or {}).get("publication_delay_seconds", 0))
            market_val = r.principal_cents + accrued
            avail = 0
            locked = market_val
            haircut_pct = r.early_redemption_haircut_pct
            liquidatable = r.principal_cents - percentage_cost_cents(r.principal_cents, haircut_pct)
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
        basis = market_cost_basis(session, b)
        cur_price = (observation.tier2_bond_price_index if use_market_data
                     else b.current_market_price_index or b.acquisition_price_index)
        cur_market_val = usd_to_ledger_cents(b.quantity * cur_price)
        haircut = b.liquidation_haircut_pct
        liq_val = cur_market_val - percentage_cost_cents(cur_market_val, haircut)
        if use_market_data:
            b.market_observation_timestamp = observation.timestamp
        b.current_market_price_index = cur_price
        b.current_market_value_cents = cur_market_val
        b.unrealized_pnl_cents = cur_market_val - basis
        if use_market_data:
            b.supplied_yield_pct = observation.tier2_bond_yield_pct
            b.modified_duration = observation.tier2_bond_mod_duration
        m1_bonds.append(
            M1BondPosition(
                id=b.id,
                run_id=run.id,
                source_type=run.source_type,
                dataset_id=run.dataset_id,
                time_basis=time_basis,
                source_observation_timestamp=observation.timestamp,
                quantity=b.quantity,
                acquisition_cost_cents=basis,
                realized_pnl_cents=b.realized_pnl_cents or 0,
                unrealized_pnl_cents=b.unrealized_pnl_cents,
                acquisition_price_index=b.acquisition_price_index,
                acquired_at=b.acquired_at,
                current_market_price_index=cur_price,
                current_market_value_cents=cur_market_val,
                supplied_yield_pct=b.supplied_yield_pct,
                modified_duration=b.modified_duration,
                liquidation_haircut_pct=haircut,
                status=b.status,
                market_observation_timestamp=b.market_observation_timestamp or b.acquired_at,
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
        basis = market_cost_basis(session, eq)
        cur_price = (observation.tier3_stock_index_price if use_market_data
                     else eq.current_market_price_index or eq.acquisition_price_index)
        cur_market_val = usd_to_ledger_cents(eq.quantity * cur_price)
        haircut = eq.liquidation_haircut_pct
        liq_val = cur_market_val - percentage_cost_cents(cur_market_val, haircut)
        if use_market_data:
            eq.market_observation_timestamp = observation.timestamp
        eq.current_market_price_index = cur_price
        eq.current_market_value_cents = cur_market_val
        eq.unrealized_pnl_cents = cur_market_val - basis
        if use_market_data:
            eq.supplied_volatility_pct = observation.tier3_stock_volatility_pct
        m1_equities.append(
            M1EquityPosition(
                id=eq.id,
                run_id=run.id,
                source_type=run.source_type,
                dataset_id=run.dataset_id,
                time_basis=time_basis,
                source_observation_timestamp=observation.timestamp,
                quantity=eq.quantity,
                acquisition_cost_cents=basis,
                realized_pnl_cents=eq.realized_pnl_cents or 0,
                unrealized_pnl_cents=eq.unrealized_pnl_cents,
                acquisition_price_index=eq.acquisition_price_index,
                acquired_at=eq.acquired_at,
                current_market_price_index=cur_price,
                current_market_value_cents=cur_market_val,
                supplied_volatility_pct=eq.supplied_volatility_pct,
                liquidation_haircut_pct=haircut,
                status=eq.status,
                market_observation_timestamp=eq.market_observation_timestamp or eq.acquired_at,
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
            ).order_by(DbOverdraftLiability.borrowed_at)
        ).all()
    )
    m1_overdrafts: list[M1OverdraftLiability] = []
    paid_costs = paid_financing_costs(session, run.id)
    for od in db_overdrafts:
        fin_cost = od.financing_cost_cents or 0
        paid_cost = paid_costs.get(od.id, 0)
        if od.outstanding_principal_cents == 0 and fin_cost == paid_cost:
            continue
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
                paid_financing_cost_cents=paid_cost,
                outstanding_financing_cost_cents=fin_cost - paid_cost,
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
        observed_at=observation.timestamp,
        repo_apy_pct=observation.tier1_repo_rate_apy,
        bond_yield_pct=observation.tier2_bond_yield_pct,
        equity_volatility_pct=observation.tier3_stock_volatility_pct,
        overdraft_apr_pct=observation.emergency_overdraft_penalty_apr_pct,
    ) if use_market_data else None
    market_prices = MarketPriceObservation(
        time_basis=time_basis,
        observed_at=observation.timestamp,
        bond_price_index=observation.tier2_bond_price_index,
        bond_modified_duration_years=observation.tier2_bond_mod_duration,
        equity_index_price=observation.tier3_stock_index_price,
    ) if use_market_data else None

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


def get_published_observation(session, dataset_id, as_of, publication_delay_seconds=0):
    return session.scalar(select(DbOrganizerObservation).where(
        DbOrganizerObservation.dataset_id == dataset_id,
        DbOrganizerObservation.timestamp <= get_information_cutoff(as_of, publication_delay_seconds)
    ).order_by(DbOrganizerObservation.timestamp.desc()).limit(1))


def hydrate_decision_portfolio(session, run, execution_observation, publication_delay_seconds=0):
    """Opening decision: consume only rows whose complete source hour has closed.

    Member 1 confirmed t+1h+delay <= decision time. The initial source
    reference is provenance only when no market quote exists.
    """
    at = execution_observation.timestamp
    published = get_published_observation(session, run.dataset_id, at, publication_delay_seconds)
    hydrated = hydrate_portfolio_state(session, run, published or execution_observation,
        as_of=at, use_market_data=published is not None)
    return (*hydrated, published)


def get_information_cutoff(as_of: datetime, publication_delay_seconds: int = 0) -> datetime:
    """Returns the strict causal observation-availability cutoff for decision time as_of.

    Confirmed by Member 1: t+1h+publication_delay <= decision time.
    Source timezone remains UNSPECIFIED; never localize naive source times.
    Those complete hourly flows are finalized and available only after hour T closes (at T + 1 hour).
    Therefore, at decision timestamp `as_of`, the latest fully observed and published
    hourly observation is `as_of - timedelta(hours=1)`.

    Any observation with timestamp >= as_of belongs to the future relative to the decision cutoff
    and is strictly rejected / excluded.
    """
    if type(publication_delay_seconds) is not int or not 0 <= publication_delay_seconds <= 2147483647:
        raise ValueError("Publication delay must be nonnegative integer seconds within int32")
    return as_of - timedelta(hours=1, seconds=publication_delay_seconds)


class _ForecastObservation(NamedTuple):
    timestamp: datetime
    deposits_usd: Decimal
    withdrawals_usd: Decimal
    net_flow_usd: Decimal


@contextmanager
def forecast_history_scope(session):
    """Reuse already-published immutable rows only within one batch/strategy run.

    Never cache between HTTP requests or beyond a failed/rolled-back batch.
    The forecast still receives the entire causal prefix and uses its original
    uncertainty calculation; no history is shortened or approximated.
    """
    key = '_rj_forecast_history'
    previous = session.info.get(key)
    if previous is not None:
        yield
        return
    session.info[key] = {}
    try:
        yield
    finally:
        session.info.pop(key, None)


def get_hourly_forecasts_from_db(
    session: Session,
    dataset_id: str,
    as_of: datetime,
    horizon_hours: int = 4,
    model_version: str = "hourly-seasonal-naive-v1",
    publication_delay_seconds: int = 0,
) -> tuple[HourlyForecastPoint, ...]:
    """Retrieves strictly causal historical observations up to the information cutoff
    and evaluates forward forecasts without lookahead leakage.
    """
    cutoff = get_information_cutoff(as_of, publication_delay_seconds)

    cache = session.info.get('_rj_forecast_history')
    cached = cache.get(dataset_id) if cache is not None else None
    history = cached[1] if cached is not None and cached[0] <= cutoff else []
    query = select(
        DbOrganizerObservation.timestamp, DbOrganizerObservation.deposits_usd,
        DbOrganizerObservation.withdrawals_usd, DbOrganizerObservation.net_flow_usd,
    ).where(DbOrganizerObservation.dataset_id == dataset_id,
            DbOrganizerObservation.timestamp <= cutoff)
    if cached is not None and cached[0] <= cutoff:
        query = query.where(DbOrganizerObservation.timestamp > cached[0])
    history.extend(_ForecastObservation(*row) for row in session.execute(
        query.order_by(DbOrganizerObservation.timestamp.asc())))
    if cache is not None:
        cache[dataset_id] = (cutoff, history)

    # Reject any future observations
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
        model_version=model_version,
        publication_delay_seconds=publication_delay_seconds,
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
    observation: DbOrganizerObservation | None = None,
    forecasts: tuple[HourlyForecastPoint, ...] | list[HourlyForecastPoint] | None = None,
    calibrated_allowance: CalibratedForecastAllowance | None = None,
    horizon_hours: int = 4,
    publication_delay_seconds: int = 0,
) -> FourTierLiquidityRiskResult:
    """Evaluates canonical Member 1 four-tier liquidity risk with causal artifact validation."""
    cutoff = get_information_cutoff(portfolio.as_of, publication_delay_seconds)

    # Validate calibration artifact: reject artifacts fitted/calibrated after cutoff
    if calibrated_allowance is not None:
        if calibrated_allowance.calibrated_through > cutoff:
            raise ValueError(
                f"Calibration artifact dated {calibrated_allowance.calibrated_through} "
                f"is after information cutoff {cutoff} (lookahead breach)"
            )
    else:
        calibrated_allowance = CalibratedForecastAllowance(
            time_basis=portfolio.time_basis,
            amount_cents=policy.base_buffer_cents,
            confidence=Decimal("0.95"),
            calibration_reference="fallback-baseline-v1",
            calibrated_through=cutoff,
        )

    if (observation is not None and observation.timestamp > cutoff) or any(
            quote is not None and quote.observed_at > cutoff
            for quote in (portfolio.market_rates, portfolio.market_prices)):
        raise ValueError("Risk input is after the publication cutoff")

    if forecasts is None or len(forecasts) == 0:
        forecast_tuple = (
            HourlyForecastPoint(
                time_basis=portfolio.time_basis,
                start_at=portfolio.as_of,
                predicted_deposits_cents=0,
                predicted_withdrawals_cents=0,
                predicted_net_flow_cents=0,
                supplied_uncertainty_buffer_cents=policy.base_buffer_cents,
            ),
        )
    else:
        forecast_tuple = tuple(forecasts)
        if any(f.start_at < portfolio.as_of for f in forecast_tuple):
            raise ValueError("Forecast points cannot start in the past relative to portfolio.as_of")

    repo_settlements = tuple(
        RepoCashSettlement(
            time_basis=portfolio.time_basis,
            position_id=p.id,
            available_at=p.scheduled_maturity_at,
            amount_cents=p.principal_cents + (p.accrued_interest_cents or 0),
            already_in_cash=False,
        )
        for p in portfolio.repo_positions
        if p.status == "LOCKED" and p.scheduled_maturity_at <= portfolio.as_of + timedelta(hours=len(forecast_tuple))
    )

    req = FourTierLiquidityRiskRequest(
        portfolio=portfolio,
        policy=policy,
        forecast=forecast_tuple,
        planning_horizon_hours=len(forecast_tuple),
        uncertainty_mode="calibrated_allowance",
        calibrated_allowance=calibrated_allowance,
        repo_settlements=repo_settlements,
    )
    return calculate_four_tier_liquidity_risk(req)


def recommend_four_tier_allocation_decision(
    portfolio: PortfolioState,
    policy: FourTierTreasuryPolicy,
    observation: DbOrganizerObservation | None,
    forecasts: tuple[HourlyForecastPoint, ...] | list[HourlyForecastPoint] | None = None,
    calibrated_allowance: CalibratedForecastAllowance | None = None,
    horizon_hours: int = 15,
    risk_aversion: Decimal | str = "1",
    publication_delay_seconds: int = 0,
) -> AllocationOptimizerResult:
    """Invokes canonical Member 1 recommend_four_tier_allocation with validated inputs."""
    cutoff = get_information_cutoff(portfolio.as_of, publication_delay_seconds)
    if observation is not None and observation.timestamp > cutoff:
        raise ValueError("Market observation is after the publication cutoff")
    if any(quote is not None and quote.observed_at > cutoff
           for quote in (portfolio.market_rates, portfolio.market_prices)):
        raise ValueError("Market quote is after the publication cutoff")
    if calibrated_allowance is not None and calibrated_allowance.calibrated_through > cutoff:
        raise ValueError(
            f"Calibration artifact dated {calibrated_allowance.calibrated_through} "
            f"is after information cutoff {cutoff} (lookahead breach)"
        )
    if calibrated_allowance is None:
        calibrated_allowance = CalibratedForecastAllowance(
            time_basis=portfolio.time_basis,
            amount_cents=policy.base_buffer_cents,
            confidence=Decimal("0.95"),
            calibration_reference="fallback-baseline-v1",
            calibrated_through=cutoff,
        )

    if forecasts is None or len(forecasts) == 0:
        forecast_tuple = (
            HourlyForecastPoint(
                time_basis=portfolio.time_basis,
                start_at=portfolio.as_of,
                predicted_deposits_cents=0,
                predicted_withdrawals_cents=0,
                predicted_net_flow_cents=0,
                supplied_uncertainty_buffer_cents=policy.base_buffer_cents,
            ),
        )
    else:
        forecast_tuple = tuple(forecasts)
        if any(f.start_at < portfolio.as_of for f in forecast_tuple):
            raise ValueError("Forecast points cannot start in the past relative to portfolio.as_of")

    repo_settlements = tuple(
        RepoCashSettlement(
            time_basis=portfolio.time_basis,
            position_id=p.id,
            available_at=p.scheduled_maturity_at,
            amount_cents=p.principal_cents + (p.accrued_interest_cents or 0),
            already_in_cash=False,
        )
        for p in portfolio.repo_positions
        if p.status == "LOCKED" and p.scheduled_maturity_at <= portfolio.as_of + timedelta(hours=len(forecast_tuple))
    )

    liquidity_req = FourTierLiquidityRiskRequest(
        portfolio=portfolio,
        policy=policy,
        forecast=forecast_tuple,
        planning_horizon_hours=horizon_hours,
        uncertainty_mode="calibrated_allowance",
        calibrated_allowance=calibrated_allowance,
        repo_settlements=repo_settlements,
    )

    # With no published row, only organizer-specified fee constants are known;
    # market prices/rates remain absent, so no first-hour acquisition is eligible.
    t1_haircut = observation.tier1_early_redemption_haircut_pct if observation else Decimal("0.5")
    t2_haircut = observation.tier2_bond_liquidation_haircut_pct if observation else Decimal("2.0")
    t3_haircut = observation.tier3_stock_liquidation_haircut_pct if observation else Decimal("15.0")

    assets = (
        AssetRewardAssumption(
            tier=1,
            stress_loss_pct=Decimal("0"),
            forced_liquidation_probability=Decimal("0"),
            liquidation_haircut_pct=t1_haircut,
            usd_per_index_point_per_unit=None,
        ),
        AssetRewardAssumption(
            tier=2,
            stress_loss_pct=Decimal("0"),
            forced_liquidation_probability=Decimal("0"),
            liquidation_haircut_pct=t2_haircut,
            usd_per_index_point_per_unit=Decimal("1"),
        ),
        AssetRewardAssumption(
            tier=3,
            stress_loss_pct=Decimal("0"),
            forced_liquidation_probability=Decimal("0"),
            liquidation_haircut_pct=t3_haircut,
            usd_per_index_point_per_unit=Decimal("1"),
        ),
    )

    rewards = AllocationRewardModel(
        time_basis="UNSPECIFIED",
        model_version="hourly-runtime-v1",
        policy_version="v1",
        assumption_reference="organizer-source-rates-policy-baseline",
        assumptions_available_at=(observation.timestamp + timedelta(hours=1, seconds=publication_delay_seconds)
                                  if observation else cutoff),
        holding_hours=15,
        risk_aversion=Decimal(str(risk_aversion)),
        assets=assets,
    )

    opt_req = AllocationOptimizerRequest(
        request_id=f"opt-{portfolio.run_id}-{portfolio.as_of.strftime('%Y%m%d%H%M%S')}",
        liquidity=liquidity_req,
        rewards=rewards,
    )

    return recommend_four_tier_allocation(opt_req)


