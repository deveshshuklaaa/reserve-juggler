"""Pure, canonical four-tier hourly reserve and scenario risk calculations."""
from datetime import timedelta
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, localcontext
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, StrictBool, StrictInt, model_validator

from .portfolio import (
    Cents, ExactDecimal, FourTierReserveResult, FourTierTreasuryPolicy, HourlyForecastPoint,
    Name, NonnegativeDecimal, PortfolioState, PositiveInt, TimeBasis, TimedPortfolioContract, Timestamp,
)
from .types import Contract

Probability = Annotated[ExactDecimal, Field(gt=0, le=1)]
Percentage = Annotated[ExactDecimal, Field(ge=0, le=100)]


class RepoCashSettlement(TimedPortfolioContract):
    position_id: UUID
    available_at: Timestamp
    amount_cents: Cents
    already_in_cash: StrictBool = False


class CommittedObligation(TimedPortfolioContract):
    obligation_id: Name
    due_at: Timestamp
    amount_cents: Cents
    already_in_forecast: StrictBool = False


class LiquidationSettlement(TimedPortfolioContract):
    position_id: UUID
    available_at: Timestamp


class CalibratedForecastAllowance(TimedPortfolioContract):
    amount_cents: Cents
    calibration_reference: Name
    calibrated_through: Timestamp
    confidence: Probability


class MarketStress(Contract):
    bond_method: Literal["price_drawdown", "yield_shock"] = "price_drawdown"
    bond_drawdown_pct: Percentage = Decimal("0")
    bond_yield_change_pct: ExactDecimal = Decimal("0")
    equity_drawdown_pct: Percentage = Decimal("0")
    equity_volatility_multiplier: NonnegativeDecimal = Decimal("0")

    @model_validator(mode="after")
    def single_bond_stress(self):
        if (self.bond_method == "price_drawdown" and self.bond_yield_change_pct != 0
                or self.bond_method == "yield_shock" and self.bond_drawdown_pct != 0):
            raise ValueError("choose price drawdown OR hypothetical yield stress, not both")
        return self


class LiquidityScenario(Contract):
    scenario_id: Name
    probability: Probability
    forecast: Annotated[tuple[HourlyForecastPoint, ...], Field(min_length=1)]
    market_stress: MarketStress = Field(default_factory=MarketStress)


class FourTierLiquidityRiskRequest(Contract):
    portfolio: PortfolioState
    policy: FourTierTreasuryPolicy
    forecast: Annotated[tuple[HourlyForecastPoint, ...], Field(min_length=1)]
    planning_horizon_hours: PositiveInt
    uncertainty_mode: Literal["calibrated_allowance", "scenario_quantile"]
    calibrated_allowance: CalibratedForecastAllowance | None = None
    confidence: Probability = Decimal("0.95")
    scenarios: tuple[LiquidityScenario, ...] = ()
    repo_settlements: tuple[RepoCashSettlement, ...] = ()
    obligations: tuple[CommittedObligation, ...] = ()
    liquidation_settlements: tuple[LiquidationSettlement, ...] = ()
    default_liquidation_delay_hours: Annotated[StrictInt, Field(ge=0)] = 1
    operational_buffer_cents: Cents | None = None
    market_stress: MarketStress = Field(default_factory=MarketStress)
    available_overdraft_credit_cents: Cents = 0
    modeled_overdraft_apr_pct: NonnegativeDecimal | None = None

    @model_validator(mode="after")
    def validate_inputs(self):
        p = self.portfolio
        if len(self.forecast) < self.planning_horizon_hours:
            raise ValueError("forecast must cover the planning horizon")
        if self.forecast[0].start_at != p.as_of:
            raise ValueError("risk path must cover the first hour from portfolio.as_of; do not assume a missing hour is zero")
        def check_path(path):
            if len(path) < self.planning_horizon_hours:
                raise ValueError("scenario must cover the planning horizon")
            if any(f.time_basis != p.time_basis or f.start_at < p.as_of for f in path):
                raise ValueError("forecast must share portfolio clock and cannot start in the past")
            if any(b.start_at - a.start_at != timedelta(hours=1) for a, b in zip(path, path[1:])):
                raise ValueError("forecast must be contiguous hourly points")
            if tuple(f.start_at for f in path[:self.planning_horizon_hours]) != tuple(f.start_at for f in self.forecast[:self.planning_horizon_hours]):
                raise ValueError("scenario times must match nominal forecast times")
        check_path(self.forecast)
        for scenario in self.scenarios:
            check_path(scenario.forecast)
        if len({s.scenario_id for s in self.scenarios}) != len(self.scenarios):
            raise ValueError("scenario IDs must be unique")
        # Exact finite-decimal sum; never silently renormalize supplied probabilities.
        with localcontext() as ctx:
            ctx.prec = 80 + sum(len(s.probability.as_tuple().digits) + abs(s.probability.as_tuple().exponent) for s in self.scenarios)
            if self.scenarios and sum(s.probability for s in self.scenarios) != 1:
                raise ValueError("scenario probabilities must sum exactly to one")
        if self.uncertainty_mode == "scenario_quantile":
            if not self.scenarios or self.calibrated_allowance is not None:
                raise ValueError("scenario quantiles require scenarios and forbid a second uncertainty allowance")
        elif self.calibrated_allowance is None:
            raise ValueError("calibrated mode requires an explicit calibration allowance/reference")
        allowance = self.calibrated_allowance
        if allowance is not None and (allowance.time_basis != p.time_basis or allowance.calibrated_through > p.as_of):
            raise ValueError("calibration cannot use a different clock or future data")
        if self.uncertainty_mode == "calibrated_allowance" and allowance.confidence != self.confidence:
            raise ValueError("request and calibration confidence must agree")
        repos = {r.id: r for r in p.repo_positions}
        seen = set()
        for settlement in self.repo_settlements:
            if settlement.position_id in seen:
                raise ValueError("duplicate repo settlement")
            seen.add(settlement.position_id)
            if settlement.time_basis != p.time_basis:
                raise ValueError("settlement clock mismatch")
            if settlement.already_in_cash:
                if settlement.position_id in repos or settlement.available_at > p.as_of:
                    raise ValueError("booked repo cash cannot also remain a position or be future-dated")
                continue
            repo = repos.get(settlement.position_id)
            if repo is None or settlement.available_at < max(p.as_of, repo.scheduled_maturity_at):
                raise ValueError("unbooked settlement needs an existing repo and actual post-maturity availability")
            # No speculative floating interest; caller may attest no more than known principal/accrual.
            if settlement.amount_cents > max(0, repo.principal_cents + (repo.accrued_interest_cents or 0)):
                raise ValueError("settlement exceeds known principal and accrued interest")
        if len({o.obligation_id for o in self.obligations}) != len(self.obligations):
            raise ValueError("obligation IDs must be unique")
        for obligation in self.obligations:
            if obligation.time_basis != p.time_basis or obligation.due_at < p.as_of:
                raise ValueError("obligations must share clock and cannot predate the snapshot")
        holdings = {r.id for r in (*p.repo_positions, *p.bond_positions, *p.equity_positions)}
        if len({s.position_id for s in self.liquidation_settlements}) != len(self.liquidation_settlements):
            raise ValueError("duplicate liquidation settlement")
        if any(s.position_id not in holdings or s.time_basis != p.time_basis or s.available_at < p.as_of
               for s in self.liquidation_settlements):
            raise ValueError("liquidation schedule must reference current holdings and a valid clock/time")
        return self


class LiquidityPathPoint(TimedPortfolioContract):
    at: Timestamp
    forecast_inflow_cents: Cents
    forecast_outflow_cents: Cents
    committed_obligation_cents: Cents
    repo_maturity_cents: Cents
    liquidation_inflow_cents: Cents
    cumulative_net_requirement_cents: StrictInt
    projected_cash_cents: StrictInt
    peak_requirement_cents: Cents


class StressLiquidationResult(TimedPortfolioContract):
    position_id: UUID
    tier: Literal[1, 2, 3]
    available_at: Timestamp
    observed_value_cents: Cents
    stressed_value_cents: Cents
    modeled_market_loss_cents: Cents
    liquidation_cost_cents: Cents
    net_proceeds_cents: Cents
    permitted: StrictBool
    reason: Name


class ScenarioLiquidityResult(Contract):
    scenario_id: Name
    probability: Probability
    peak_cash_requirement_cents: Cents
    funding_shortfall_before_liquidation_cents: Cents
    funding_shortfall_after_liquidation_cents: Cents
    market_stress_loss_cents: Cents


class FourTierLiquidityRiskResult(TimedPortfolioContract):
    as_of: Timestamp
    planning_end_at: Timestamp
    reserve: FourTierReserveResult
    uncertainty_mode: Literal["calibrated_allowance", "scenario_quantile"]
    calibration_reference: Name | None
    confidence: Probability
    nominal_peak_requirement_cents: Cents
    configured_operational_buffer_cents: Cents
    minimum_reserve_topup_cents: Cents
    available_cash_cents: Cents
    restricted_liquidity_cents: Cents
    reported_immediately_available_cents: Cents
    existing_liabilities_cents: Cents
    permitted_stress_liquidation_cents: Cents
    modeled_market_loss_cents: Cents
    worst_scenario_market_loss_cents: Cents
    funding_shortfall_before_liquidation_cents: Cents
    funding_shortfall_after_liquidation_cents: Cents
    reserve_breach: StrictBool
    projected_funding_failure_before_liquidation: StrictBool
    projected_funding_failure_after_liquidation: StrictBool
    actual_payout_failure: None = None
    scenario_metrics_basis: Literal["supplied_weighted_scenarios", "not_estimated"]
    expected_unfunded_cash_cents: Cents | None
    tail_expected_shortfall_cents: Cents | None
    scenario_reserve_breach_probability: Annotated[ExactDecimal, Field(ge=0, le=1)] | None
    scenario_funding_failure_probability_before: Annotated[ExactDecimal, Field(ge=0, le=1)] | None
    scenario_funding_failure_probability_after: Annotated[ExactDecimal, Field(ge=0, le=1)] | None
    modeled_overdraft_draw_cents: Cents
    modeled_overdraft_financing_cost_cents: Cents | None
    funding_gap_after_modeled_overdraft_cents: Cents
    policy_violations: tuple[Name, ...]
    path_before_liquidation: tuple[LiquidityPathPoint, ...]
    path_after_liquidation: tuple[LiquidityPathPoint, ...]
    liquidations: tuple[StressLiquidationResult, ...]
    scenarios: tuple[ScenarioLiquidityResult, ...]
    explanations: tuple[Name, ...]
    recommendation_only: Literal[True] = True
    execution_status: Literal["NOT_EXECUTED"] = "NOT_EXECUTED"


def _ceil(value):
    return int(value.to_integral_value(rounding=ROUND_CEILING))


def _cost(cents, pct):
    return _ceil(Decimal(cents) * pct / 100)


def _events(request, forecast, *, liquidations=()):
    end = request.forecast[request.planning_horizon_hours - 1].start_at + timedelta(hours=1)
    events = {}
    def add(at, kind, cents):
        if request.portfolio.as_of <= at <= end:
            events.setdefault(at, [0, 0, 0, 0, 0])[kind] += cents
    add(request.portfolio.as_of, 0, 0)
    add(end, 0, 0)
    for f in forecast[:request.planning_horizon_hours]:
        add(f.start_at, 1, f.predicted_withdrawals_cents)
        add(f.start_at + timedelta(hours=1), 0, f.predicted_deposits_cents)
    for obligation in request.obligations:
        if not obligation.already_in_forecast:
            add(obligation.due_at, 2, obligation.amount_cents)
    redeemed = {r.position_id for r in liquidations if r.permitted and r.tier == 1 and r.available_at <= end}
    for settlement in request.repo_settlements:
        if not settlement.already_in_cash and settlement.position_id not in redeemed:
            add(settlement.available_at, 3, settlement.amount_cents)
    for sale in liquidations:
        if sale.permitted:
            add(sale.available_at, 4, sale.net_proceeds_cents)
    net = peak = 0
    path = []
    for at, (inflow, outflow, obligation, maturity, sale) in sorted(events.items()):
        # Credits available at the same instant precede debits; no intrahour borrowing.
        net += outflow + obligation - inflow - maturity - sale
        peak = max(peak, net)
        path.append(LiquidityPathPoint(time_basis=request.portfolio.time_basis, at=at,
            forecast_inflow_cents=inflow, forecast_outflow_cents=outflow,
            committed_obligation_cents=obligation, repo_maturity_cents=maturity,
            liquidation_inflow_cents=sale, cumulative_net_requirement_cents=net,
            projected_cash_cents=request.portfolio.cash.balance_cents - net, peak_requirement_cents=peak))
    return peak, tuple(path)


def _liquidations(request, stress):
    p = request.portfolio
    dates = {s.position_id: s.available_at for s in request.liquidation_settlements}
    default = p.as_of + timedelta(hours=request.default_liquidation_delay_hours)
    results = []
    for repo in p.repo_positions:
        at = dates.get(repo.id, default)
        # Only early break here; normal maturities are exclusively the attested schedule.
        if at >= repo.scheduled_maturity_at:
            continue
        permitted = (request.policy.allow_early_repo_redemption and repo.early_redemption_allowed is True
                     and repo.liquidity.classification != "UNAVAILABLE")
        principal = max(0, repo.principal_cents + min(0, repo.accrued_interest_cents or 0))
        cost = _cost(repo.principal_cents, repo.early_redemption_haircut_pct)
        permitted = permitted and principal >= cost
        results.append(StressLiquidationResult(time_basis=p.time_basis, position_id=repo.id, tier=1,
            available_at=at, observed_value_cents=repo.market_value_cents, stressed_value_cents=principal,
            modeled_market_loss_cents=0, liquidation_cost_cents=cost, net_proceeds_cents=max(0, principal - cost),
            permitted=permitted, reason="Early break requires policy/position permission and self-funding fees; positive interest excluded; maturity removed if broken."))
    for position in (*p.bond_positions, *p.equity_positions):
        if position.tier == 2:
            shock = (stress.bond_drawdown_pct / 100 if stress.bond_method == "price_drawdown"
                     else max(Decimal(0), position.modified_duration * stress.bond_yield_change_pct / 100))
            allowed = request.policy.allow_bond_liquidation
        else:
            sigma = position.supplied_volatility_pct / 100 * (Decimal(request.planning_horizon_hours) / 8760).sqrt()
            shock = stress.equity_drawdown_pct / 100 + stress.equity_volatility_multiplier * sigma
            allowed = request.policy.allow_emergency_equity_liquidation
        shock = min(Decimal(1), shock)
        value = position.current_market_value_cents
        stressed = int((Decimal(value) * (1 - shock)).to_integral_value(rounding=ROUND_FLOOR))
        fee = _cost(stressed, position.liquidation_haircut_pct)
        results.append(StressLiquidationResult(time_basis=p.time_basis, position_id=position.id, tier=position.tier,
            available_at=dates.get(position.id, default), observed_value_cents=value, stressed_value_cents=stressed,
            modeled_market_loss_cents=value - stressed, liquidation_cost_cents=fee,
            net_proceeds_cents=stressed - fee,
            permitted=allowed and position.liquidity.classification == "LIQUIDATABLE",
            reason="Hypothetical stress on supplied current mark, then supplied haircut; not a second realized price loss."))
    return tuple(results)


def _quantile(items, confidence):
    cumulative = Decimal(0)
    for value, probability in sorted(items):
        cumulative += probability
        if cumulative >= confidence:
            return value
    return max(value for value, _ in items)


def _tail_mean(items, confidence):
    if confidence == 1:
        return max(value for value, _ in items)
    remaining = 1 - confidence
    total = Decimal(0)
    for value, probability in sorted(items, reverse=True):
        take = min(remaining, probability)
        total += value * take
        remaining -= take
        if not remaining:
            break
    return _ceil(total / (1 - confidence))


def calculate_four_tier_liquidity_risk(request: FourTierLiquidityRiskRequest) -> FourTierLiquidityRiskResult:
    """No optimization or execution; supplied calibration/scenarios are caller attestations."""
    if not isinstance(request, FourTierLiquidityRiskRequest):
        raise ValueError("use a validated canonical FourTierLiquidityRiskRequest")
    # Cover all supplied Decimal coefficients/exponents, retaining cent boundaries.
    decimals = []
    def collect(value):
        if isinstance(value, Decimal):
            decimals.append(value)
        elif type(value) is int:
            decimals.append(Decimal(value))
        elif isinstance(value, dict):
            for child in value.values(): collect(child)
        elif isinstance(value, (list, tuple)):
            for child in value: collect(child)
    collect(request.model_dump())
    with localcontext() as ctx:
        ctx.prec = 80 + sum(len(d.as_tuple().digits) + abs(d.as_tuple().exponent) for d in decimals)
        return _calculate(request)


def _calculate(request):
    p = request.portfolio
    cash = p.cash.balance_cents
    peak, before = _events(request, request.forecast)
    sales = _liquidations(request, request.market_stress)
    after_peak, after = _events(request, request.forecast, liquidations=sales)
    scenarios = []
    for scenario in request.scenarios:
        scenario_peak, _ = _events(request, scenario.forecast)
        scenario_sales = _liquidations(request, scenario.market_stress)
        scenario_after, _ = _events(request, scenario.forecast, liquidations=scenario_sales)
        scenarios.append(ScenarioLiquidityResult(scenario_id=scenario.scenario_id, probability=scenario.probability,
            peak_cash_requirement_cents=scenario_peak,
            funding_shortfall_before_liquidation_cents=max(0, scenario_peak - cash),
            funding_shortfall_after_liquidation_cents=max(0, scenario_after - cash),
            market_stress_loss_cents=sum(s.modeled_market_loss_cents for s in scenario_sales)))
    base = peak
    allowance = request.calibrated_allowance.amount_cents if request.calibrated_allowance else 0
    if request.uncertainty_mode == "scenario_quantile":
        base = _quantile([(s.peak_cash_requirement_cents, s.probability) for s in scenarios], request.confidence)
    operational = request.policy.base_buffer_cents if request.operational_buffer_cents is None else request.operational_buffer_cents
    floor_topup = max(0, request.policy.minimum_liquid_reserve_cents - base - allowance - operational)
    reserve = FourTierReserveResult(time_basis=p.time_basis, as_of=p.as_of, net_drain_cents=base,
        uncertainty_buffer_cents=allowance, base_buffer_cents=operational + floor_topup,
        required_reserve_cents=base + allowance + operational + floor_topup)
    shortfall = max(0, peak - cash)
    after_shortfall = max(0, after_peak - cash)
    expected = tail = breach_probability = failure_before = failure_after = None
    if scenarios:
        deficits = [(s.funding_shortfall_before_liquidation_cents, s.probability) for s in scenarios]
        expected = _ceil(sum(value * weight for value, weight in deficits))
        tail = _tail_mean(deficits, request.confidence)
        # Scenario peaks already carry scenario uncertainty: never add allowance again.
        breach_probability = sum((s.probability for s in scenarios if cash < max(request.policy.minimum_liquid_reserve_cents,
            s.peak_cash_requirement_cents + operational)), Decimal(0))
        failure_before = sum((s.probability for s in scenarios if s.funding_shortfall_before_liquidation_cents), Decimal(0))
        failure_after = sum((s.probability for s in scenarios if s.funding_shortfall_after_liquidation_cents), Decimal(0))
    outstanding_principal = sum(o.outstanding_principal_cents for o in p.overdrafts)
    capacity = min(request.available_overdraft_credit_cents, max(0, request.policy.max_overdraft_cents - outstanding_principal)) if request.policy.allow_overdraft else 0
    draw = min(after_shortfall, capacity)
    apr = request.modeled_overdraft_apr_pct
    if apr is None and p.market_rates is not None:
        apr = p.market_rates.overdraft_apr_pct
    financing = None
    if not draw:
        financing = 0
    elif apr is not None:
        span = before[-1].at - p.as_of
        micros = (span.days * 86400 + span.seconds) * 1_000_000 + span.microseconds
        financing = _ceil(Decimal(draw) * apr * micros / (100 * 365 * 86400 * 1_000_000))
    violations = []
    tier_values = (p.cash.balance_cents, p.valuation.tier1_value_cents,
                   p.valuation.tier2_market_value_cents, p.valuation.tier3_market_value_cents)
    for limit in request.policy.tier_limits:
        value = tier_values[limit.tier] * 10000
        if value > limit.max_allocation_bps * p.valuation.total_portfolio_value_cents:
            violations.append(f"Tier {limit.tier} current exposure exceeds maximum {limit.max_allocation_bps} bps")
        if value < limit.min_allocation_bps * p.valuation.total_portfolio_value_cents:
            violations.append(f"Tier {limit.tier} current exposure is below minimum {limit.min_allocation_bps} bps")
    market_loss = sum(s.modeled_market_loss_cents for s in sales)
    worst_market_loss = max((s.market_stress_loss_cents for s in scenarios), default=0)
    if request.policy.max_estimated_loss_cents is not None and max(market_loss, worst_market_loss) > request.policy.max_estimated_loss_cents:
        violations.append("Modeled market stress exceeds max_estimated_loss_cents")
    if outstanding_principal > request.policy.max_overdraft_cents:
        violations.append("Existing overdraft principal exceeds policy borrowing limit")
    reference = request.calibrated_allowance.calibration_reference if request.calibrated_allowance else None
    return FourTierLiquidityRiskResult(time_basis=p.time_basis, as_of=p.as_of, planning_end_at=before[-1].at,
        reserve=reserve, uncertainty_mode=request.uncertainty_mode, calibration_reference=reference,
        confidence=request.confidence, nominal_peak_requirement_cents=peak,
        configured_operational_buffer_cents=operational, minimum_reserve_topup_cents=floor_topup,
        available_cash_cents=cash, restricted_liquidity_cents=p.valuation.restricted_value_cents,
        reported_immediately_available_cents=p.valuation.immediately_available_cents,
        existing_liabilities_cents=p.valuation.liabilities_cents,
        permitted_stress_liquidation_cents=sum(s.net_proceeds_cents for s in sales if s.permitted and s.available_at <= before[-1].at),
        modeled_market_loss_cents=market_loss, worst_scenario_market_loss_cents=worst_market_loss,
        funding_shortfall_before_liquidation_cents=shortfall,
        funding_shortfall_after_liquidation_cents=after_shortfall,
        reserve_breach=cash < reserve.required_reserve_cents,
        projected_funding_failure_before_liquidation=shortfall > 0,
        projected_funding_failure_after_liquidation=after_shortfall > 0,
        scenario_metrics_basis="supplied_weighted_scenarios" if scenarios else "not_estimated",
        expected_unfunded_cash_cents=expected, tail_expected_shortfall_cents=tail,
        scenario_reserve_breach_probability=breach_probability,
        scenario_funding_failure_probability_before=failure_before, scenario_funding_failure_probability_after=failure_after,
        modeled_overdraft_draw_cents=draw, modeled_overdraft_financing_cost_cents=financing,
        funding_gap_after_modeled_overdraft_cents=after_shortfall - draw,
        policy_violations=tuple(violations), path_before_liquidation=before, path_after_liquidation=after,
        liquidations=sales, scenarios=tuple(scenarios), explanations=(
            "Withdrawals debit at hour start; deposits credit at hour end; contractual settlements credit only at actual availability.",
            f"peak_cents={peak}; reserve_basis_cents={base}; allowance_cents={allowance}; operational_cents={operational}; minimum_topup_cents={floor_topup}",
            "Forecast deposits/withdrawals drive timing; independent source-net forecasts are not rewritten or implicitly substituted.",
            "Per-point provisional uncertainty is not added; only explicit calibration OR scenario peak quantile enters reserve.",
            "Scenario probabilities are supplied scenario-model weights, not empirically measured failure frequencies.",
            "Stress liquidations are hypothetical full sales at modeled settlement times; they are not trades or settled cash.",
            "Overdraft capacity is new borrowing, excluded from existing assets/reserve; quoted APR held constant over full horizon for conservative cost illustration.",
            "Expected unfunded cash and tail expected shortfall are scenario funding-gap statistics, not observed payout failures.",
            "No payouts are executed or observed: actual_payout_failure is null; reserve breach can occur without a projected payout funding failure.",
        ))
