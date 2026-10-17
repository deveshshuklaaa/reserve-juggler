"""Multi-asset Monte Carlo risk simulation and joint portfolio stress modeling.

Models joint uncertainty of cash flows, bond prices, and equity returns using
strictly causal historical block bootstrap sampling of forecast residuals and
market innovations. Connects directly to canonical FourTierLiquidityRiskRequest.
"""
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, localcontext
import math
import random
from typing import Annotated, Any, Literal, Sequence
from uuid import UUID, uuid5, NAMESPACE_DNS

from pydantic import Field, StrictBool, StrictInt, model_validator

from .instrument_economics import usd_to_ledger_cents
from .liquidity_risk import (
    CommittedObligation,
    FourTierLiquidityRiskRequest,
    FourTierLiquidityRiskResult,
    LiquidityPathPoint,
    LiquidityScenario,
    MarketStress,
    Percentage,
    RepoCashSettlement,
    StressLiquidationResult,
    calculate_four_tier_liquidity_risk,
    _cost,
    _events,
    _liquidations,
)
from .portfolio import (
    Cents,
    ExactDecimal,
    FourTierReserveResult,
    FourTierTreasuryPolicy,
    HourlyForecastPoint,
    Name,
    NonnegativeDecimal,
    OrganizerHourlyObservation,
    PortfolioState,
    PositiveInt,
    SignedCents,
    TimedPortfolioContract,
    Timestamp,
)
from .types import Contract

MONTE_CARLO_RISK_MODEL_VERSION = "multi-asset-block-mc-v1.1"


class PercentileSummary(Contract):
    """Distribution percentiles for multi-asset stress metrics."""
    percentile: ExactDecimal
    peak_requirement_cents: Cents
    funding_shortfall_cents: Cents
    funding_shortfall_after_liquidation_cents: Cents
    tier2_bond_market_loss_cents: Cents
    tier3_equity_market_loss_cents: Cents
    total_market_loss_cents: Cents
    portfolio_value_cents: SignedCents
    portfolio_downside_cents: Cents
    liquidation_costs_cents: Cents
    overdraft_draw_cents: Cents
    overdraft_cost_cents: Cents


class MarketRiskSummary(Contract):
    """Tier 2 bond and Tier 3 equity market-risk summaries under modeled scenarios."""
    tier2_bond_initial_value_cents: Cents
    tier2_bond_mean_loss_cents: Cents
    tier2_bond_loss_p90_cents: Cents
    tier2_bond_loss_p95_cents: Cents
    tier2_bond_loss_p99_cents: Cents
    tier2_bond_max_loss_cents: Cents
    tier3_equity_initial_value_cents: Cents
    tier3_equity_mean_loss_cents: Cents
    tier3_equity_loss_p90_cents: Cents
    tier3_equity_loss_p95_cents: Cents
    tier3_equity_loss_p99_cents: Cents
    tier3_equity_max_loss_cents: Cents
    total_market_loss_mean_cents: Cents
    total_market_loss_p95_cents: Cents
    total_market_loss_max_cents: Cents


class ShortfallDistributionSummary(Contract):
    """Distribution of cash funding shortfall across simulated paths."""
    mean_shortfall_before_liquidation_cents: Cents
    p90_shortfall_before_liquidation_cents: Cents
    p95_shortfall_before_liquidation_cents: Cents
    p99_shortfall_before_liquidation_cents: Cents
    max_shortfall_before_liquidation_cents: Cents
    shortfall_probability_before_liquidation: Annotated[ExactDecimal, Field(ge=0, le=1)]
    mean_shortfall_after_liquidation_cents: Cents
    p95_shortfall_after_liquidation_cents: Cents
    max_shortfall_after_liquidation_cents: Cents
    shortfall_probability_after_liquidation: Annotated[ExactDecimal, Field(ge=0, le=1)]
    expected_unfunded_cash_cents: Cents
    tail_expected_shortfall_cents: Cents


class PortfolioDownsideRiskSummary(Contract):
    """Net portfolio value drawdown and downside loss metrics."""
    initial_net_portfolio_value_cents: SignedCents
    expected_net_portfolio_value_cents: SignedCents
    p90_portfolio_value_cents: SignedCents
    p95_portfolio_value_cents: SignedCents
    p99_portfolio_value_cents: SignedCents
    worst_case_portfolio_value_cents: SignedCents
    p90_downside_loss_cents: Cents
    p95_downside_loss_cents: Cents
    p99_downside_loss_cents: Cents
    max_downside_loss_cents: Cents


class MultiAssetMonteCarloRiskResult(TimedPortfolioContract):
    """Typed result of multi-asset Monte Carlo risk simulation."""
    as_of: Timestamp
    planning_horizon_hours: PositiveInt
    scenario_count: PositiveInt
    seed: StrictInt
    model_version: Name
    selected_percentile: Annotated[ExactDecimal, Field(gt=0, le=1)]
    required_reserve: FourTierReserveResult
    shortfall_distribution: ShortfallDistributionSummary
    market_risk: MarketRiskSummary
    portfolio_downside: PortfolioDownsideRiskSummary
    p90_summary: PercentileSummary
    p95_summary: PercentileSummary
    p99_summary: PercentileSummary
    scenarios: tuple[LiquidityScenario, ...]
    liquidity_risk_result: FourTierLiquidityRiskResult
    notes: tuple[Name, ...]
    recommendation_only: Literal[True] = True
    execution_status: Literal["NOT_EXECUTED"] = "NOT_EXECUTED"


def _quantile_val(sorted_values: Sequence[int], p: float) -> int:
    """Return the value at rank ceil(p * n) - 1, clamping to array bounds."""
    if not sorted_values:
        return 0
    n = len(sorted_values)
    idx = max(0, min(n - 1, math.ceil(p * n) - 1))
    return sorted_values[idx]


def _quantile_decimal(sorted_values: Sequence[Decimal], p: float) -> Decimal:
    """Return the Decimal value at rank ceil(p * n) - 1."""
    if not sorted_values:
        return Decimal(0)
    n = len(sorted_values)
    idx = max(0, min(n - 1, math.ceil(p * n) - 1))
    return sorted_values[idx]


def generate_multi_asset_scenarios(
    history: Sequence[OrganizerHourlyObservation],
    nominal_forecast: Sequence[HourlyForecastPoint],
    *,
    as_of: datetime,
    planning_horizon_hours: int = 24,
    scenario_count: int = 500,
    seed: int = 42,
    time_basis: Literal["UNSPECIFIED", "UTC"] = "UNSPECIFIED",
) -> tuple[LiquidityScenario, ...]:
    """Generate reproducible multi-asset risk scenarios via block bootstrap.

    Uses historically available observations (t <= as_of) to sample joint contiguous
    blocks of deposit/withdrawal residuals, bond price/yield changes, and equity price changes.
    Preserves historical multi-asset correlations.
    """
    if planning_horizon_hours <= 0:
        raise ValueError("planning_horizon_hours must be a positive integer")
    if scenario_count <= 0:
        raise ValueError("scenario_count must be a positive integer")
    if len(nominal_forecast) < planning_horizon_hours:
        raise ValueError("nominal_forecast must cover the planning_horizon_hours")

    # Filter history strictly to timestamps <= as_of (no future lookahead)
    valid_history = [obs for obs in history if obs.timestamp <= as_of]
    if len(valid_history) < 24 + planning_horizon_hours:
        raise ValueError(
            f"insufficient history for block sampling: need at least {24 + planning_horizon_hours} "
            f"hourly observations prior to {as_of}, got {len(valid_history)}"
        )

    # Seasonal lags are hourly offsets, so missing hours cannot be skipped.
    for i in range(1, len(valid_history)):
        if valid_history[i].timestamp - valid_history[i - 1].timestamp != timedelta(hours=1):
            raise ValueError("history observations must be contiguous and chronologically ordered hourly rows")

    # Precompute historical 24h seasonal residuals for cash flows
    dep_residuals = []
    with_residuals = []
    for t in range(24, len(valid_history)):
        curr = valid_history[t]
        prior_24 = valid_history[t - 24]
        dep_residuals.append(usd_to_ledger_cents(curr.deposits_usd - prior_24.deposits_usd))
        with_residuals.append(usd_to_ledger_cents(curr.withdrawals_usd - prior_24.withdrawals_usd))

    # Available block start indices in valid_history: [24, len(valid_history) - planning_horizon_hours]
    max_start = len(valid_history) - planning_horizon_hours
    min_start = 24
    if max_start < min_start:
        raise ValueError("history length insufficient for planning horizon block sampling")

    # Reproducible PRNG with user seed
    rng = random.Random(seed)

    # Probability per scenario: exact Decimal
    prob = Decimal("1") / Decimal(scenario_count)
    with localcontext() as ctx:
        ctx.prec = 80
        final_probability = Decimal(1) - prob * (scenario_count - 1)

    scenarios = []
    for i in range(scenario_count):
        # Sample a contiguous historical block
        start_idx = rng.randint(min_start, max_start)
        block = valid_history[start_idx : start_idx + planning_horizon_hours]

        # 1. Cash flow path with residual shocks
        sim_points = []
        for h in range(planning_horizon_hours):
            nom_pt = nominal_forecast[h]
            res_idx = start_idx - 24 + h
            shock_dep = dep_residuals[res_idx]
            shock_with = with_residuals[res_idx]

            # Inflows and outflows are strictly non-negative
            sim_dep = max(0, nom_pt.predicted_deposits_cents + shock_dep)
            sim_with = max(0, nom_pt.predicted_withdrawals_cents + shock_with)
            sim_net = sim_dep - sim_with

            sim_points.append(
                HourlyForecastPoint(
                    time_basis=time_basis,
                    start_at=nom_pt.start_at,
                    predicted_deposits_cents=sim_dep,
                    predicted_withdrawals_cents=sim_with,
                    predicted_net_flow_cents=sim_net,
                    supplied_uncertainty_buffer_cents=0,
                )
            )

        # 2. Market stress over the block
        # Bond drawdown over block
        bond_start = valid_history[start_idx - 1].tier2_bond_price_index
        bond_min = min(obs.tier2_bond_price_index for obs in block)
        bond_dd_pct = max(Decimal(0), (1 - bond_min / bond_start) * 100)

        # Equity drawdown over block
        equity_start = valid_history[start_idx - 1].tier3_stock_index_price
        equity_min = min(obs.tier3_stock_index_price for obs in block)
        equity_dd_pct = max(Decimal(0), (1 - equity_min / equity_start) * 100)

        market_stress = MarketStress(
            bond_method="price_drawdown",
            bond_drawdown_pct=bond_dd_pct.quantize(Decimal("0.0001")),
            bond_yield_change_pct=Decimal("0"),
            equity_drawdown_pct=equity_dd_pct.quantize(Decimal("0.0001")),
            equity_volatility_multiplier=Decimal("0"),
        )

        scenario_id = f"mc_scenario_{i + 1:04d}"
        scenarios.append(
            LiquidityScenario(
                scenario_id=scenario_id,
                probability=prob if i < scenario_count - 1 else final_probability,
                forecast=tuple(sim_points),
                market_stress=market_stress,
            )
        )

    return tuple(scenarios)


def simulate_multi_asset_monte_carlo_risk(
    portfolio: PortfolioState,
    history: Sequence[OrganizerHourlyObservation],
    nominal_forecast: Sequence[HourlyForecastPoint],
    policy: FourTierTreasuryPolicy,
    *,
    planning_horizon_hours: int = 24,
    scenario_count: int = 500,
    seed: int = 42,
    confidence: Decimal = Decimal("0.95"),
    repo_settlements: Sequence[RepoCashSettlement] = (),
    obligations: Sequence[CommittedObligation] = (),
    available_overdraft_credit_cents: int = 0,
    operational_buffer_cents: int | None = None,
) -> MultiAssetMonteCarloRiskResult:
    """Simulate multi-asset Monte Carlo risk and evaluate joint liquidity/market stress.

    Performs:
    1. Historical block bootstrap sampling of cash flows, bond prices, and equity prices.
    2. Canonical pathwise evaluation via calculate_four_tier_liquidity_risk.
    3. Revaluation of portfolio positions, downside losses, and forced liquidation/overdraft costs.
    4. Distribution summaries at 90th, 95th, and 99th percentiles.
    5. Production of risk-sensitive required reserve.
    """
    if portfolio.source_observation_timestamp is not None and portfolio.source_observation_timestamp > portfolio.as_of:
        raise ValueError("portfolio snapshot cannot reference future observations")

    # Generate canonical joint scenarios
    scenarios = generate_multi_asset_scenarios(
        history,
        nominal_forecast,
        as_of=portfolio.as_of,
        planning_horizon_hours=planning_horizon_hours,
        scenario_count=scenario_count,
        seed=seed,
        time_basis=portfolio.time_basis,
    )

    # Evaluate through canonical liquidity risk framework
    risk_request = FourTierLiquidityRiskRequest(
        portfolio=portfolio,
        policy=policy,
        forecast=nominal_forecast,
        planning_horizon_hours=planning_horizon_hours,
        uncertainty_mode="scenario_quantile",
        confidence=confidence,
        scenarios=scenarios,
        repo_settlements=repo_settlements,
        obligations=obligations,
        available_overdraft_credit_cents=available_overdraft_credit_cents,
        operational_buffer_cents=operational_buffer_cents,
        modeled_overdraft_apr_pct=(portfolio.market_rates.overdraft_apr_pct if portfolio.market_rates
            else next((o.emergency_overdraft_penalty_apr_pct for o in reversed(history)
                       if o.timestamp <= portfolio.as_of), None)),
    )
    risk_result = calculate_four_tier_liquidity_risk(risk_request)

    # Initial values
    cash_0 = portfolio.cash.balance_cents
    repo_0 = portfolio.valuation.tier1_value_cents
    bond_0 = portfolio.valuation.tier2_market_value_cents
    equity_0 = portfolio.valuation.tier3_market_value_cents
    liab_0 = portfolio.valuation.liabilities_cents
    init_npv = portfolio.valuation.net_portfolio_value_cents

    # Collect pathwise metrics across all scenarios
    peak_reqs = []
    shortfalls_before = []
    shortfalls_after = []
    bond_losses = []
    equity_losses = []
    total_market_losses = []
    liquidation_costs = []
    overdraft_draws = []
    overdraft_costs = []
    portfolio_values = []
    downside_losses = []

    # Map scenarios to their evaluated results
    scen_result_map = {sr.scenario_id: sr for sr in risk_result.scenarios}

    # APR for overdraft
    overdraft_apr = risk_request.modeled_overdraft_apr_pct
    if overdraft_apr is None and portfolio.market_rates is not None:
        overdraft_apr = portfolio.market_rates.overdraft_apr_pct

    end_time = nominal_forecast[planning_horizon_hours - 1].start_at + timedelta(hours=1)
    span = end_time - portfolio.as_of
    micros = (span.days * 86400 + span.seconds) * 1_000_000 + span.microseconds

    for scenario in scenarios:
        sr = scen_result_map[scenario.scenario_id]

        peak_reqs.append(sr.peak_cash_requirement_cents)
        shortfalls_before.append(sr.funding_shortfall_before_liquidation_cents)
        shortfalls_after.append(sr.funding_shortfall_after_liquidation_cents)

        # Market losses per tier
        # Bond loss
        sales = _liquidations(risk_request, scenario.market_stress)
        bond_loss = sum(s.modeled_market_loss_cents for s in sales if s.tier == 2)
        bond_losses.append(bond_loss)

        # Equity loss
        equity_loss = sum(s.modeled_market_loss_cents for s in sales if s.tier == 3)
        equity_losses.append(equity_loss)

        total_market_loss = bond_loss + equity_loss
        total_market_losses.append(total_market_loss)

        # Forced liquidations and costs
        executed_sales = tuple(s for s in sales if s.permitted and s.available_at <= end_time)
        liq_cost = sum(s.liquidation_cost_cents for s in executed_sales)
        liquidation_costs.append(liq_cost)

        # Overdraft draw and financing
        outstanding_debt = sum(o.outstanding_principal_cents for o in portfolio.overdrafts)
        capacity = max(0, policy.max_overdraft_cents - outstanding_debt) if policy.allow_overdraft else 0
        capacity = min(capacity, available_overdraft_credit_cents)
        draw = min(sr.funding_shortfall_after_liquidation_cents, capacity)
        overdraft_draws.append(draw)

        od_cost = 0
        if draw > 0:
            if overdraft_apr is None:
                raise ValueError("overdraft APR is required to model positive borrowing costs")
            od_cost = int((Decimal(draw) * overdraft_apr * micros / (100 * 365 * 86400 * 1_000_000)).to_integral_value(rounding=ROUND_CEILING))
        # Existing principal also incurs financing; previously booked costs remain
        # in opening liabilities and are not charged twice or compounded.
        od_cost += sum(int((Decimal(o.outstanding_principal_cents) * o.apr_pct * micros
                           / (100 * 365 * 86400 * 1_000_000)).to_integral_value(rounding=ROUND_CEILING))
                       for o in portfolio.overdrafts)
        overdraft_costs.append(od_cost)

        # Revalue ending portfolio state:
        # Net cash change: cash_0 minus cumulative cash flow demand
        # Ending cash after operational flows and liquidations
        _, ending_path = _events(risk_request, scenario.forecast, liquidations=executed_sales)
        sim_ending_cash = ending_path[-1].projected_cash_cents + draw
        # A settled claim is removed when its cash receipt is credited. Full
        # hypothetical market sales likewise remove the corresponding asset.
        redeemed = {s.position_id for s in executed_sales if s.tier == 1}
        settled = {s.position_id for s in repo_settlements
                   if not s.already_in_cash and s.available_at <= end_time}
        sim_repo_value = repo_0 - sum(r.market_value_cents for r in portfolio.repo_positions
                                     if r.id in redeemed | settled)
        sim_bond_value = max(0, bond_0 - bond_loss)
        sim_equity_value = max(0, equity_0 - equity_loss)
        sim_bond_value -= sum(s.stressed_value_cents for s in executed_sales if s.tier == 2)
        sim_equity_value -= sum(s.stressed_value_cents for s in executed_sales if s.tier == 3)
        sim_liab = liab_0 + draw + od_cost

        sim_npv = sim_ending_cash + sim_repo_value + sim_bond_value + sim_equity_value - sim_liab
        portfolio_values.append(sim_npv)

        downside = max(0, init_npv - sim_npv)
        downside_losses.append(downside)

    # Sort arrays for percentile computation
    peak_reqs_sorted = sorted(peak_reqs)
    shortfalls_before_sorted = sorted(shortfalls_before)
    shortfalls_after_sorted = sorted(shortfalls_after)
    bond_losses_sorted = sorted(bond_losses)
    equity_losses_sorted = sorted(equity_losses)
    total_market_losses_sorted = sorted(total_market_losses)
    downside_losses_sorted = sorted(downside_losses)
    portfolio_values_sorted = sorted(portfolio_values)  # ascending: worst portfolio value is first!
    liq_costs_sorted = sorted(liquidation_costs)
    od_draws_sorted = sorted(overdraft_draws)
    od_costs_sorted = sorted(overdraft_costs)

    n = len(scenarios)

    def make_percentile_summary(pct: float) -> PercentileSummary:
        pct_dec = Decimal(str(int(pct * 100)))
        # For portfolio value: quantile from worst (1 - pct) so that higher stress shows lower value
        val_idx = max(0, min(n - 1, n - math.ceil(pct * n)))
        return PercentileSummary(
            percentile=pct_dec,
            peak_requirement_cents=_quantile_val(peak_reqs_sorted, pct),
            funding_shortfall_cents=_quantile_val(shortfalls_before_sorted, pct),
            funding_shortfall_after_liquidation_cents=_quantile_val(shortfalls_after_sorted, pct),
            tier2_bond_market_loss_cents=_quantile_val(bond_losses_sorted, pct),
            tier3_equity_market_loss_cents=_quantile_val(equity_losses_sorted, pct),
            total_market_loss_cents=_quantile_val(total_market_losses_sorted, pct),
            portfolio_value_cents=portfolio_values_sorted[val_idx],
            portfolio_downside_cents=_quantile_val(downside_losses_sorted, pct),
            liquidation_costs_cents=_quantile_val(liq_costs_sorted, pct),
            overdraft_draw_cents=_quantile_val(od_draws_sorted, pct),
            overdraft_cost_cents=_quantile_val(od_costs_sorted, pct),
        )

    p90_summary = make_percentile_summary(0.90)
    p95_summary = make_percentile_summary(0.95)
    p99_summary = make_percentile_summary(0.99)

    # Market risk summary
    market_risk = MarketRiskSummary(
        tier2_bond_initial_value_cents=bond_0,
        tier2_bond_mean_loss_cents=int((Decimal(sum(bond_losses)) / n).to_integral_value(rounding=ROUND_HALF_UP)),
        tier2_bond_loss_p90_cents=_quantile_val(bond_losses_sorted, 0.90),
        tier2_bond_loss_p95_cents=_quantile_val(bond_losses_sorted, 0.95),
        tier2_bond_loss_p99_cents=_quantile_val(bond_losses_sorted, 0.99),
        tier2_bond_max_loss_cents=bond_losses_sorted[-1],
        tier3_equity_initial_value_cents=equity_0,
        tier3_equity_mean_loss_cents=int((Decimal(sum(equity_losses)) / n).to_integral_value(rounding=ROUND_HALF_UP)),
        tier3_equity_loss_p90_cents=_quantile_val(equity_losses_sorted, 0.90),
        tier3_equity_loss_p95_cents=_quantile_val(equity_losses_sorted, 0.95),
        tier3_equity_loss_p99_cents=_quantile_val(equity_losses_sorted, 0.99),
        tier3_equity_max_loss_cents=equity_losses_sorted[-1],
        total_market_loss_mean_cents=int((Decimal(sum(total_market_losses)) / n).to_integral_value(rounding=ROUND_HALF_UP)),
        total_market_loss_p95_cents=_quantile_val(total_market_losses_sorted, 0.95),
        total_market_loss_max_cents=total_market_losses_sorted[-1],
    )

    # Shortfall distribution summary
    shortfall_count_before = sum(1 for s in shortfalls_before if s > 0)
    shortfall_count_after = sum(1 for s in shortfalls_after if s > 0)
    shortfall_prob_before = (Decimal(shortfall_count_before) / Decimal(n)).quantize(Decimal("0.0001"))
    shortfall_prob_after = (Decimal(shortfall_count_after) / Decimal(n)).quantize(Decimal("0.0001"))

    shortfall_dist = ShortfallDistributionSummary(
        mean_shortfall_before_liquidation_cents=int((Decimal(sum(shortfalls_before)) / n).to_integral_value(rounding=ROUND_HALF_UP)),
        p90_shortfall_before_liquidation_cents=_quantile_val(shortfalls_before_sorted, 0.90),
        p95_shortfall_before_liquidation_cents=_quantile_val(shortfalls_before_sorted, 0.95),
        p99_shortfall_before_liquidation_cents=_quantile_val(shortfalls_before_sorted, 0.99),
        max_shortfall_before_liquidation_cents=shortfalls_before_sorted[-1],
        shortfall_probability_before_liquidation=shortfall_prob_before,
        mean_shortfall_after_liquidation_cents=int((Decimal(sum(shortfalls_after)) / n).to_integral_value(rounding=ROUND_HALF_UP)),
        p95_shortfall_after_liquidation_cents=_quantile_val(shortfalls_after_sorted, 0.95),
        max_shortfall_after_liquidation_cents=shortfalls_after_sorted[-1],
        shortfall_probability_after_liquidation=shortfall_prob_after,
        expected_unfunded_cash_cents=risk_result.expected_unfunded_cash_cents or 0,
        tail_expected_shortfall_cents=risk_result.tail_expected_shortfall_cents or 0,
    )

    # Portfolio downside risk summary
    portfolio_downside = PortfolioDownsideRiskSummary(
        initial_net_portfolio_value_cents=init_npv,
        expected_net_portfolio_value_cents=int((Decimal(sum(portfolio_values)) / n).to_integral_value(rounding=ROUND_HALF_UP)),
        p90_portfolio_value_cents=portfolio_values_sorted[max(0, n - math.ceil(0.90 * n))],
        p95_portfolio_value_cents=portfolio_values_sorted[max(0, n - math.ceil(0.95 * n))],
        p99_portfolio_value_cents=portfolio_values_sorted[max(0, n - math.ceil(0.99 * n))],
        worst_case_portfolio_value_cents=portfolio_values_sorted[0],
        p90_downside_loss_cents=_quantile_val(downside_losses_sorted, 0.90),
        p95_downside_loss_cents=_quantile_val(downside_losses_sorted, 0.95),
        p99_downside_loss_cents=_quantile_val(downside_losses_sorted, 0.99),
        max_downside_loss_cents=downside_losses_sorted[-1],
    )

    notes = (
        f"Simulated {scenario_count} reproducible joint multi-asset paths via block bootstrap with seed={seed}.",
        "Cash flows modeled using 24h seasonal forecast residual innovations; negative flows clipped to zero.",
        "Market stress captures contemporaneous bond price index and equity index drawdowns within each block.",
        "Scenario probabilities represent empirical relative frequencies, not guaranteed real-world confidence intervals.",
        "NAV is a hypothetical full permitted-liquidation stress endpoint, not a trade recommendation or realized account; negative cash denotes unfunded obligations.",
        "Required reserve derived directly from scenario quantile peak cash requirement under FourTierReserveResult.",
    )

    return MultiAssetMonteCarloRiskResult(
        time_basis=portfolio.time_basis,
        as_of=portfolio.as_of,
        planning_horizon_hours=planning_horizon_hours,
        scenario_count=scenario_count,
        seed=seed,
        model_version=MONTE_CARLO_RISK_MODEL_VERSION,
        selected_percentile=confidence,
        required_reserve=risk_result.reserve,
        shortfall_distribution=shortfall_dist,
        market_risk=market_risk,
        portfolio_downside=portfolio_downside,
        p90_summary=p90_summary,
        p95_summary=p95_summary,
        p99_summary=p99_summary,
        scenarios=scenarios,
        liquidity_risk_result=risk_result,
        notes=notes,
    )
