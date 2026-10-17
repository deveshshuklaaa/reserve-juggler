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


def get_hourly_forecasts_from_db(
    session: Session,
    dataset_id: str,
    as_of: datetime,
    horizon_hours: int = 4,
) -> tuple[HourlyForecastPoint, ...]:
    """Retrieves upcoming hourly observations and builds canonical forecast points."""
    future_obs = list(
        session.scalars(
            select(DbOrganizerObservation).where(
                DbOrganizerObservation.dataset_id == dataset_id,
                DbOrganizerObservation.timestamp >= as_of,
            ).order_by(DbOrganizerObservation.timestamp.asc()).limit(horizon_hours)
        )
    )
    points: list[HourlyForecastPoint] = []
    for i in range(horizon_hours):
        start_time = as_of + timedelta(hours=i)
        if i < len(future_obs):
            obs = future_obs[i]
            dep_cents = int(round(obs.deposits_usd * Decimal(100)))
            wd_cents = int(round(obs.withdrawals_usd * Decimal(100)))
            net_cents = dep_cents - wd_cents
        else:
            dep_cents = 0
            wd_cents = 0
            net_cents = 0

        uncert_cents = int(round(abs(Decimal(net_cents)) * Decimal("0.10"))) + 5000000

        points.append(
            HourlyForecastPoint(
                time_basis="UNSPECIFIED",
                start_at=start_time,
                predicted_deposits_cents=dep_cents,
                predicted_withdrawals_cents=wd_cents,
                predicted_net_flow_cents=net_cents,
                supplied_uncertainty_buffer_cents=uncert_cents,
            )
        )
    return tuple(points)


def evaluate_liquidity_risk(
    portfolio: PortfolioState,
    policy: FourTierTreasuryPolicy,
    observation: DbOrganizerObservation | None = None,
    forecasts: tuple[HourlyForecastPoint, ...] | list[HourlyForecastPoint] | None = None,
    horizon_hours: int = 4,
) -> FourTierLiquidityRiskResult:
    """Evaluates canonical Member 1 four-tier liquidity risk."""
    if forecasts is None or len(forecasts) == 0:
        forecast_tuple = (
            HourlyForecastPoint(
                time_basis=portfolio.time_basis,
                start_at=portfolio.as_of,
                predicted_deposits_cents=int(round(observation.deposits_usd * Decimal(100))) if observation else 0,
                predicted_withdrawals_cents=int(round(observation.withdrawals_usd * Decimal(100))) if observation else 0,
                predicted_net_flow_cents=int(round(observation.net_flow_usd * Decimal(100))) if observation else 0,
                supplied_uncertainty_buffer_cents=5000000,
            ),
        )
    else:
        forecast_tuple = tuple(forecasts)

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

