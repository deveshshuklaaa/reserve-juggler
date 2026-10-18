"""Deterministic constrained candidate search; recommendations, never execution."""
from dataclasses import dataclass, field
from datetime import time, timedelta
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, localcontext
from itertools import product
from typing import Annotated, Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import Field, StrictBool, StrictInt, field_validator, model_validator

from .liquidity_risk import FourTierLiquidityRiskRequest, FourTierLiquidityRiskResult, calculate_four_tier_liquidity_risk
from .portfolio import (
    AllocationTargets, CostBreakdown, ExactDecimal, FourTierDecisionResult, FourTierReserveResult,
    InstrumentId, InstrumentReturnEstimate, Name, NonnegativeDecimal, PositiveDecimal,
    RecommendedOrder, TimedPortfolioContract, Timestamp,
)
from .types import Cents, Contract, PositiveInt

Pct = Annotated[ExactDecimal, Field(ge=0, le=100)]
Fraction = Annotated[ExactDecimal, Field(ge=0, le=1)]


class AssetRewardAssumption(Contract):
    tier: Literal[1, 2, 3]
    expected_income_pct: ExactDecimal = Decimal(0)
    expected_price_return_pct: ExactDecimal = Decimal(0)
    stress_loss_pct: Pct
    forced_liquidation_probability: Fraction
    liquidation_haircut_pct: Pct
    trade_fee_pct: Pct = Decimal(0)
    fixed_trade_fee_cents: Cents = 0
    usd_per_index_point_per_unit: PositiveDecimal | None = None
    quantity_decimal_places: Annotated[StrictInt, Field(ge=0, le=36)] = 8

    @field_validator("tier", mode="before")
    @classmethod
    def integer_tier(cls, value):
        if type(value) is not int: raise ValueError("tier must be an integer")
        return value

    @model_validator(mode="after")
    def instrument_assumptions(self):
        if self.tier == 1 and (self.expected_income_pct or self.expected_price_return_pct or self.usd_per_index_point_per_unit is not None):
            raise ValueError("repo income uses the current floating quote; no price gain or market-unit convention")
        if self.tier in (2, 3) and self.usd_per_index_point_per_unit is None:
            raise ValueError("market purchases require an explicit quantity/index convention")
        return self


class AllocationRewardModel(TimedPortfolioContract):
    model_version: Name
    policy_version: Name
    assumption_reference: Name
    assumption_status: Literal["user_supplied", "calibrated"] = "user_supplied"
    calibration_reference: Name | None = None
    assumptions_available_at: Timestamp
    holding_hours: PositiveInt
    risk_aversion: NonnegativeDecimal = Decimal(1)
    equity_volatility_multiplier: NonnegativeDecimal = Decimal(2)
    assets: tuple[AssetRewardAssumption, ...]

    @model_validator(mode="after")
    def complete_assets(self):
        if len(self.assets) != 3 or {a.tier for a in self.assets} != {1, 2, 3}:
            raise ValueError("supply exactly one explicit assumption for each investment tier")
        if (self.assumption_status == "calibrated") != (self.calibration_reference is not None):
            raise ValueError("calibrated rewards require an actual supplied calibration reference")
        return self


class AllocationOptimizerRequest(Contract):
    request_id: Name
    liquidity: FourTierLiquidityRiskRequest
    rewards: AllocationRewardModel
    supplied_reserve: FourTierReserveResult | None = None
    allocation_grid_bps: tuple[Annotated[StrictInt, Field(ge=0, le=10000)], ...] = (0, 5000, 10000)
    max_candidates: Annotated[StrictInt, Field(ge=1, le=10000)] = 2048
    new_repo_settlement_delay_hours: Annotated[StrictInt, Field(ge=0)] = 0

    @model_validator(mode="after")
    def source_and_horizon(self):
        p = self.liquidity.portfolio
        if p.currency != "USD":
            raise ValueError("quantity conventions are explicitly USD; no implicit FX conversion")
        if self.rewards.time_basis != p.time_basis or self.rewards.assumptions_available_at > p.as_of:
            raise ValueError("reward assumptions must share the clock and be available at decision time")
        if self.rewards.holding_hours > self.liquidity.planning_horizon_hours:
            raise ValueError("liquidity forecast must cover the reward holding horizon")
        if not self.allocation_grid_bps or len(set(self.allocation_grid_bps)) != len(self.allocation_grid_bps):
            raise ValueError("allocation grid must be nonempty and unique")
        if self.supplied_reserve is not None and (self.supplied_reserve.as_of != p.as_of or self.supplied_reserve.time_basis != p.time_basis):
            raise ValueError("supplied reserve must match portfolio time and basis")
        return self


class CandidateAssessment(Contract):
    candidate: Name
    feasible: StrictBool
    objective_cents: ExactDecimal | None
    reason: Name


class AllocationOptimizerResult(Contract):
    summary_action: Literal["HOLD", "INVEST", "REBALANCE", "LIQUIDATE", "WARNING"]
    decision: FourTierDecisionResult
    risk: FourTierLiquidityRiskResult
    model_version: Name
    policy_version: Name
    assumption_reference: Name
    reward_assumptions: AllocationRewardModel
    objective_cents: ExactDecimal | None
    estimated_income_cents: StrictInt
    estimated_price_change_cents: StrictInt
    expected_forced_liquidation_cost_cents: Cents
    modeled_financing_cost_cents: Cents
    estimated_financing_savings_cents: Cents
    immediate_wealth_loss_cents: Cents
    cash_available_at_decision_after_orders_cents: Cents
    projected_nominal_funding_gap_cents: Cents
    projected_scenario_failure_weight: Fraction | None
    evaluated_candidates: PositiveInt
    feasible_candidates: Cents
    search_truncated: StrictBool
    assessments: tuple[CandidateAssessment, ...]
    legacy_action_hint: Literal["HOLD", "SWEEP", "WITHDRAW", "LIQUIDITY_WARNING"] | None
    recommendation_only: Literal[True] = True
    execution_status: Literal["NOT_EXECUTED"] = "NOT_EXECUTED"

    @model_validator(mode="after")
    def consistent_action(self):
        expected = "HOLD" if self.summary_action == "HOLD" else "LIQUIDITY_WARNING" if self.summary_action == "WARNING" else "ALLOCATE"
        if self.decision.action != expected:
            raise ValueError("summary and canonical decision actions disagree")
        if self.model_version != self.reward_assumptions.model_version or self.policy_version != self.reward_assumptions.policy_version:
            raise ValueError("versions must match the disclosed reward model")
        if self.decision.as_of != self.risk.as_of or self.decision.time_basis != self.risk.time_basis:
            raise ValueError("risk and recommendation clocks must agree")
        if self.decision.feasible and self.projected_nominal_funding_gap_cents:
            raise ValueError("feasible recommendations cannot contain a nominal funding gap")
        if self.decision.feasible and self.projected_scenario_failure_weight is not None:
            with localcontext() as ctx:
                ctx.prec = 80 + len(self.risk.confidence.as_tuple().digits) + len(self.projected_scenario_failure_weight.as_tuple().digits)
                if self.projected_scenario_failure_weight > 1 - self.risk.confidence:
                    raise ValueError("feasible recommendation exceeds the scenario funding-risk budget")
        return self


@dataclass
class _Plan:
    targets: list[int]
    cash_now: int
    debt: int
    orders: list[RecommendedOrder] = field(default_factory=list)
    sold_repo: dict[UUID, Decimal] = field(default_factory=dict)
    borrowed: int = 0
    repaid: int = 0
    interest_saved: Decimal = Decimal(0)

    def copy(self):
        return _Plan(self.targets.copy(), self.cash_now, self.debt, self.orders.copy(), self.sold_repo.copy(),
                     self.borrowed, self.repaid, self.interest_saved)


def _ceil(value): return int(Decimal(value).to_integral_value(rounding=ROUND_CEILING))
def _floor(value): return int(Decimal(value).to_integral_value(rounding=ROUND_FLOOR))
def _fee(value, pct): return _ceil(Decimal(value) * pct / 100)


def recommend_four_tier_allocation(request: AllocationOptimizerRequest) -> AllocationOptimizerResult:
    if not isinstance(request, AllocationOptimizerRequest):
        raise ValueError("optimizer requires validated canonical inputs and explicit reward assumptions")
    values = []
    def collect(value):
        if isinstance(value, Decimal): values.append(value)
        elif type(value) is int: values.append(Decimal(value))
        elif isinstance(value, dict):
            for child in value.values(): collect(child)
        elif isinstance(value, (tuple, list)):
            for child in value: collect(child)
    collect(request.model_dump())
    with localcontext() as ctx:
        ctx.prec = 80 + sum(len(v.as_tuple().digits) + abs(v.as_tuple().exponent) for v in values)
        return _search(request)


def _search(req):
    p, policy, rewards = req.liquidity.portfolio, req.liquidity.policy, req.rewards
    risk = calculate_four_tier_liquidity_risk(req.liquidity)
    reserve = risk.reserve
    if req.supplied_reserve and req.supplied_reserve.required_reserve_cents > reserve.required_reserve_cents:
        reserve = req.supplied_reserve
    mandatory = max(reserve.required_reserve_cents, policy.minimum_liquid_reserve_cents)
    if mandatory > reserve.required_reserve_cents:
        reserve = reserve.model_copy(update={"base_buffer_cents": reserve.base_buffer_cents + mandatory - reserve.required_reserve_cents,
                                              "required_reserve_cents": mandatory})
    assets = {a.tier: a for a in rewards.assets}
    current = [p.cash.balance_cents, p.valuation.tier1_value_cents, p.valuation.tier2_market_value_cents, p.valuation.tier3_market_value_cents]
    original_gross = sum(current)
    debt = sum(o.outstanding_principal_cents for o in p.overdrafts)
    initial = _Plan(current.copy(), current[0], debt)
    source = {k: getattr(p, k) for k in ("time_basis", "run_id", "source_type", "dataset_id", "source_observation_timestamp")}
    sale_dates = {s.position_id: s.available_at for s in req.liquidity.liquidation_settlements}
    default_sale_at = p.as_of + timedelta(hours=req.liquidity.default_liquidation_delay_hours)
    repo_maturity = p.as_of + timedelta(hours=15)
    repo_allowed = (policy.repo_sweep_window_open and p.as_of.time() == time(17) and rewards.holding_hours >= 15 + req.new_repo_settlement_delay_hours
                    and p.market_rates is not None)
    warnings = []
    if not repo_allowed: warnings.append("Repo entry ineligible: requires explicit open 17:00 window, quote, and >=15h reward horizon")
    if p.market_prices is None: warnings.append("Market purchases ineligible: no current timestamped source price quote")
    explicit_caps = {limit.tier for limit in policy.tier_limits}
    for tier in (2, 3):
        if tier not in explicit_caps: warnings.append(f"Tier {tier} new purchases ineligible: an explicit asset exposure cap is required")

    def order(plan, action, tier, amount, *, position=None, quantity=None, cost=0, proceeds=None, at=None, repo_fee=0, liquidation_fee=0, funding=0):
        identifier = uuid5(NAMESPACE_URL, f"reserve-juggler:{p.run_id}:{p.as_of.isoformat()}:{req.request_id}:{len(plan.orders)}:{action}:{position}:{amount}:{quantity}")
        costs = CostBreakdown(repo_break_fee_cents=repo_fee, liquidation_fee_cents=liquidation_fee,
            transaction_cost_cents=cost - repo_fee - liquidation_fee, funding_cost_cents=funding)
        # Funding estimates are liabilities, never an upfront fee or investment income.
        plan.orders.append(RecommendedOrder(**source, id=identifier, as_of=p.as_of, action=action, tier=tier,
            position_id=position, amount_cents=amount, quantity=quantity, estimated_cost_cents=costs.total_cents,
            expected_costs=costs, expected_proceeds_cents=proceeds,
            earliest_execution_at=p.as_of, expected_settlement_at=at or p.as_of,
            expected_maturity_at=repo_maturity if action == "INVEST_REPO" else None,
            reason=f"Candidate {action}: gross_cents={amount}; immediate_cost_cents={cost}; net_proceeds_cents={proceeds}; recommendation only"))

    holdings = sorted((*p.repo_positions, *p.bond_positions, *p.equity_positions), key=lambda x: (x.tier, str(x.id)))
    def sell(plan, position, amount):
        at = sale_dates.get(position.id, default_sale_at)
        assumption = assets[position.tier]
        if position.tier == 1:
            early = at < position.scheduled_maturity_at
            if early and (not policy.allow_early_repo_redemption or position.early_redemption_allowed is not True): return False
            if position.liquidity.classification == "UNAVAILABLE": return False
            # Do not issue a second redemption at/after an already scheduled receipt.
            known = next((s for s in req.liquidity.repo_settlements if s.position_id == position.id and not s.already_in_cash), None)
            if known and at >= known.available_at: return False
            gross = min(position.principal_cents, max(0, amount))
            if not gross: return False
            share = Decimal(gross) / position.principal_cents
            removed = _ceil(position.market_value_cents * share)
            earned = _floor((min(0, position.accrued_interest_cents or 0) if early else position.accrued_interest_cents or 0) * share)
            break_fee = _fee(gross, position.early_redemption_haircut_pct) if early else 0
            haircut_fee = 0
            fee = break_fee + _fee(gross, assumption.trade_fee_pct) + assumption.fixed_trade_fee_cents
            proceeds = gross + earned - fee
            quantity = None
            action = "REDEEM_REPO"
        else:
            if position.liquidity.classification != "LIQUIDATABLE": return False
            if position.tier == 2 and not policy.allow_bond_liquidation: return False
            if position.tier == 3 and not policy.allow_emergency_equity_liquidation: return False
            value = position.current_market_value_cents
            if not value: return False
            gross = min(value, max(0, amount))
            quantum = Decimal(1).scaleb(-assumption.quantity_decimal_places)
            quantity = position.quantity if gross == value else (position.quantity * gross / value).quantize(quantum, rounding=ROUND_FLOOR)
            if quantity <= 0: return False
            gross = _floor(Decimal(value) * quantity / position.quantity)
            removed = gross
            haircut_fee = _fee(gross, position.liquidation_haircut_pct)
            fee = haircut_fee + _fee(gross, assumption.trade_fee_pct) + assumption.fixed_trade_fee_cents
            proceeds, break_fee = gross - fee, 0
            action = "SELL_BONDS" if position.tier == 2 else "SELL_EQUITIES"
        if proceeds <= 0: return False
        plan.targets[position.tier] -= removed
        plan.targets[0] += proceeds
        if at == p.as_of: plan.cash_now += proceeds
        if position.tier == 1: plan.sold_repo[position.id] = share
        order(plan, action, position.tier, gross, position=position.id, quantity=quantity,
              cost=fee, proceeds=proceeds, at=at, repo_fee=break_fee, liquidation_fee=haircut_fee)
        return True

    seeds = [initial]
    for holding in holdings:
        full = initial.copy()
        if sell(full, holding, holding.principal_cents if holding.tier == 1 else holding.current_market_value_cents): seeds.append(full)
    full = initial.copy()
    for holding in holdings:
        sell(full, holding, holding.principal_cents if holding.tier == 1 else holding.current_market_value_cents)
    if full.orders: seeds.append(full)
    # Repair liquidity with minimal gross sales first; binary search uses exact fee/quantity rules.
    repair = initial.copy()
    for holding in sorted(holdings, key=lambda h: (h.early_redemption_haircut_pct if h.tier == 1 else h.liquidation_haircut_pct, str(h.id))):
        need = max(0, mandatory - repair.targets[0])
        if not need: break
        maximum = holding.principal_cents if holding.tier == 1 else holding.current_market_value_cents
        trial = repair.copy()
        if not sell(trial, holding, maximum): continue
        if trial.targets[0] >= mandatory:
            lo, hi = 1, maximum
            while lo < hi:
                mid = (lo + hi) // 2
                probe = repair.copy()
                if sell(probe, holding, mid) and probe.targets[0] >= mandatory: hi = mid
                else: lo = mid + 1
            sell(repair, holding, lo)
        else: repair = trial
    if repair.orders: seeds.append(repair)
    # A separate minimal-sale repair addresses current concentration breaches.
    exposure_repair = initial.copy()
    given_limits = {limit.tier: limit for limit in policy.tier_limits}
    for holding in holdings:
        cap = given_limits[holding.tier].max_allocation_bps if holding.tier in given_limits else policy.max_allocation_bps
        if exposure_repair.targets[holding.tier] * 10000 <= sum(exposure_repair.targets) * cap: continue
        maximum = holding.principal_cents if holding.tier == 1 else holding.current_market_value_cents
        probe = exposure_repair.copy()
        if not sell(probe, holding, maximum): continue
        if probe.targets[holding.tier] * 10000 > sum(probe.targets) * cap:
            exposure_repair = probe
            continue
        lo, hi = 1, maximum
        while lo < hi:
            mid = (lo + hi) // 2
            trial = exposure_repair.copy()
            if sell(trial, holding, mid) and trial.targets[holding.tier] * 10000 <= sum(trial.targets) * cap: hi = mid
            else: lo = mid + 1
        sell(exposure_repair, holding, lo)
    if exposure_repair.orders: seeds.append(exposure_repair)
    # Principal repayment and emergency borrowing are financing alternatives, never yield assets.
    for seed in tuple(seeds):
        pay = seed.copy()
        for loan in sorted(p.overdrafts, key=lambda o: (-o.apr_pct, str(o.id))):
            amount = min(loan.outstanding_principal_cents, max(0, pay.cash_now - mandatory))
            if amount:
                pay.cash_now -= amount; pay.targets[0] -= amount; pay.debt -= amount; pay.repaid += amount
                pay.interest_saved += Decimal(amount) * loan.apr_pct / 100 * rewards.holding_hours / 8760
                order(pay, "REPAY_OVERDRAFT", 0, amount, position=loan.id, cost=0)
        if pay.repaid: seeds.append(pay)
        need = max(0, mandatory - seed.cash_now)
        capacity = min(req.liquidity.available_overdraft_credit_cents, max(0, policy.max_overdraft_cents - seed.debt)) if policy.allow_overdraft else 0
        if need and need <= capacity:
            borrow = seed.copy()
            borrow.targets[0] += need; borrow.cash_now += need; borrow.debt += need; borrow.borrowed += need
            order(borrow, "BORROW_OVERDRAFT", 0, need, cost=0, proceeds=need)
            seeds.append(borrow)

    from .portfolio import TierAllocationLimit
    limits = {l.tier: l for l in policy.tier_limits}
    for tier in range(4):
        limits.setdefault(tier, TierAllocationLimit(tier=tier, max_allocation_bps=10000 if tier == 0 else policy.max_allocation_bps))
    effective_policy = type(policy).model_validate(policy.model_dump() | {"tier_limits": tuple(limits.values())})
    stress_pct = {i: assets[i].stress_loss_pct for i in (1, 2, 3)}
    if p.market_rates:
        stress_pct[3] = max(stress_pct[3], rewards.equity_volatility_multiplier * p.market_rates.equity_volatility_pct * (Decimal(rewards.holding_hours) / 8760).sqrt())
    for supplied_stress in (req.liquidity.market_stress, *(s.market_stress for s in req.liquidity.scenarios)):
        if p.market_prices:
            bond_stress = supplied_stress.bond_drawdown_pct if supplied_stress.bond_method == "price_drawdown" else max(Decimal(0), p.market_prices.bond_modified_duration_years * supplied_stress.bond_yield_change_pct)
            stress_pct[2] = max(stress_pct[2], min(Decimal(100), bond_stress))
        equity_stress = supplied_stress.equity_drawdown_pct
        if p.market_rates:
            equity_stress += supplied_stress.equity_volatility_multiplier * p.market_rates.equity_volatility_pct * (Decimal(req.liquidity.planning_horizon_hours) / 8760).sqrt()
        stress_pct[3] = max(stress_pct[3], min(Decimal(100), equity_stress))
    for sale in risk.liquidations:
        if sale.observed_value_cents:
            stress_pct[sale.tier] = max(stress_pct[sale.tier], Decimal(sale.modeled_market_loss_cents) * 100 / sale.observed_value_cents)
    for scenario in req.liquidity.scenarios:
        # Scenario risk cannot be made invisible by optimistic reward assumptions.
        from .liquidity_risk import _liquidations
        for sale in _liquidations(req.liquidity, scenario.market_stress):
            if sale.observed_value_cents:
                stress_pct[sale.tier] = max(stress_pct[sale.tier], Decimal(sale.modeled_market_loss_cents) * 100 / sale.observed_value_cents)
    stress_pct = {tier: min(Decimal(100), value) for tier, value in stress_pct.items()}
    apr = req.liquidity.modeled_overdraft_apr_pct
    if apr is None and p.market_rates: apr = p.market_rates.overdraft_apr_pct

    def buy(plan, tier, budget):
        assumption = assets[tier]
        if budget <= assumption.fixed_trade_fee_cents or tier == 1 and not repo_allowed: return
        if plan.borrowed: return  # Never borrow to buy investments.
        if tier != 1 and p.market_prices is None: return
        if tier in (2, 3) and tier not in explicit_caps: return
        if tier == 3 and p.market_rates is None: return
        spend = min(budget, max(0, plan.cash_now - mandatory))
        principal = max(0, _floor(Decimal(spend - assumption.fixed_trade_fee_cents) * 100 / (100 + assumption.trade_fee_pct)))
        # Purchase fees shrink the gross-asset denominator: solve the cap after fees.
        lo, hi = 0, principal
        while lo < hi:
            mid = (lo + hi + 1) // 2
            fee_at_mid = _fee(mid, assumption.trade_fee_pct) + assumption.fixed_trade_fee_cents
            if (plan.targets[tier] + mid) * 10000 <= limits[tier].max_allocation_bps * (sum(plan.targets) - fee_at_mid): lo = mid
            else: hi = mid - 1
        principal = lo
        quantity = None
        if tier != 1:
            price = p.market_prices.bond_price_index if tier == 2 else p.market_prices.equity_index_price
            unit_usd = price * assumption.usd_per_index_point_per_unit
            quantum = Decimal(1).scaleb(-assumption.quantity_decimal_places)
            quantity = (Decimal(principal) / 100 / unit_usd).quantize(quantum, rounding=ROUND_FLOOR)
            if quantity <= 0: return
            principal = _ceil(quantity * unit_usd * 100)
        fee = _fee(principal, assumption.trade_fee_pct) + assumption.fixed_trade_fee_cents
        if principal < policy.min_transfer_cents or not principal or principal + fee > spend: return
        plan.cash_now -= principal + fee; plan.targets[0] -= principal + fee; plan.targets[tier] += principal
        order(plan, {1: "INVEST_REPO", 2: "BUY_BONDS", 3: "BUY_EQUITIES"}[tier], tier, principal, quantity=quantity, cost=fee)

    def peak_gap(plan, path):
        deltas = {row.at: row.forecast_inflow_cents - row.forecast_outflow_cents - row.committed_obligation_cents + row.repo_maturity_cents for row in path}
        end = path[-1].at
        for settlement in req.liquidity.repo_settlements:
            if not settlement.already_in_cash and settlement.position_id in plan.sold_repo and settlement.available_at <= end:
                removed = settlement.amount_cents - _floor(settlement.amount_cents * (1 - plan.sold_repo[settlement.position_id]))
                deltas[settlement.available_at] = deltas.get(settlement.available_at, 0) - removed
        for o in plan.orders:
            if o.action in ("SELL_BONDS", "SELL_EQUITIES", "REDEEM_REPO", "BORROW_OVERDRAFT"):
                at, delta = o.expected_settlement_at, o.expected_proceeds_cents
            else: at, delta = p.as_of, -o.amount_cents - o.estimated_cost_cents
            if at <= end: deltas[at] = deltas.get(at, 0) + delta
            if o.action == "INVEST_REPO":
                at = o.expected_maturity_at + timedelta(hours=req.new_repo_settlement_delay_hours)
                if at <= end: deltas[at] = deltas.get(at, 0) + o.amount_cents  # Principal only, no uncertain interest.
        cash = p.cash.balance_cents
        gap = 0
        for _, delta in sorted(deltas.items()):
            cash += delta; gap = max(gap, -cash)
        return gap

    # Reuse the timed obligation/maturity paths, not aggregate ending balances.
    from .liquidity_risk import _events
    scenario_paths = [(s.probability, _events(req.liquidity, s.forecast)[1]) for s in req.liquidity.scenarios]
    def assess(plan):
        total = sum(plan.targets)
        if min(plan.targets) < 0 or plan.targets[0] < mandatory: return "target cash below mandatory reserve"
        if any(o.expected_settlement_at > risk.planning_end_at for o in plan.orders): return "settlement falls beyond the covered liquidity horizon"
        if plan.debt > policy.max_overdraft_cents: return "overdraft target exceeds policy"
        for tier, limit in limits.items():
            if not limit.min_allocation_bps * total <= plan.targets[tier] * 10000 <= limit.max_allocation_bps * total:
                return f"Tier {tier} exposure bound violated"
        if peak_gap(plan, risk.path_before_liquidation): return "nominal interim payout funding deficit"
        if sum((weight for weight, path in scenario_paths if peak_gap(plan, path)), Decimal(0)) > 1 - req.liquidity.confidence:
            return "scenario funding-failure weight exceeds confidence budget"
        if plan.borrowed and apr is None: return "new borrowing has no supplied financing quote"
        risk_loss = sum(_fee(plan.targets[i], stress_pct[i]) for i in (1, 2, 3))
        if policy.max_estimated_loss_cents is not None and risk_loss > policy.max_estimated_loss_cents:
            return "stress loss exceeds risk policy"
        return None

    def economics(plan):
        interest = price_return = forced_cost = Decimal(0)
        returns = [InstrumentReturnEstimate(instrument=InstrumentId.TIER0_CASH, horizon_hours=rewards.holding_hours,
            expected_income_cents=0, expected_price_change_cents=0, expected_costs=CostBreakdown(),
            estimated_stress_loss_cents=0, estimate_basis="Operational cash has zero investment yield")]
        for tier in (1, 2, 3):
            amount = plan.targets[tier]
            assumption = assets[tier]
            if tier == 1:
                income = Decimal(0)
                for repo in p.repo_positions:
                    span = repo.scheduled_maturity_at - p.as_of
                    micros = (span.days * 86400 + span.seconds) * 1000000 + span.microseconds
                    remaining_hours = max(Decimal(0), Decimal(micros) / 3600000000)
                    principal = repo.principal_cents * (1 - plan.sold_repo.get(repo.id, Decimal(0)))
                    quote = p.market_rates.repo_apy_pct if p.market_rates else repo.applicable_apy_pct
                    income += principal * quote / 100 * min(Decimal(rewards.holding_hours), remaining_hours) / 8760
                income += sum(Decimal(o.amount_cents) * p.market_rates.repo_apy_pct / 100 * 15 / 8760 for o in plan.orders if o.action == "INVEST_REPO")
                gain = Decimal(0)
            else:
                income = Decimal(amount) * assumption.expected_income_pct / 100
                gain = Decimal(amount) * assumption.expected_price_return_pct / 100
            positions = p.repo_positions if tier == 1 else p.bond_positions if tier == 2 else p.equity_positions
            exit_pct = max(assumption.liquidation_haircut_pct, max((o.early_redemption_haircut_pct if tier == 1 else o.liquidation_haircut_pct for o in positions), default=Decimal(0)))
            exit_cost = Decimal(amount) * assumption.forced_liquidation_probability * exit_pct / 100
            interest += income; price_return += gain; forced_cost += exit_cost
            returns.append(InstrumentReturnEstimate(instrument=InstrumentId({1: "TIER1_REPO", 2: "TIER2_BOND", 3: "TIER3_EQUITY"}[tier]),
                horizon_hours=rewards.holding_hours, expected_income_cents=_floor(income), expected_price_change_cents=_floor(gain),
                expected_costs=CostBreakdown(repo_break_fee_cents=_ceil(exit_cost) if tier == 1 else 0,
                    liquidation_fee_cents=_ceil(exit_cost) if tier != 1 else 0), estimated_stress_loss_cents=_fee(amount, stress_pct[tier]),
                estimate_basis=f"Supplied {rewards.assumption_reference}; expected only; repo quote held constant; observed marks not reconstructed"))
        wealth_loss = max(0, original_gross + plan.borrowed - plan.repaid - sum(plan.targets))
        prior_financing = sum(Decimal(o.outstanding_principal_cents) * o.apr_pct / 100 * rewards.holding_hours / 8760 for o in p.overdrafts)
        financing = prior_financing + Decimal(plan.borrowed) * (apr or 0) / 100 * rewards.holding_hours / 8760 - plan.interest_saved
        if plan.debt:
            returns.append(InstrumentReturnEstimate(instrument=InstrumentId.OVERDRAFT, horizon_hours=rewards.holding_hours,
                expected_income_cents=0, expected_price_change_cents=0, expected_costs=CostBreakdown(funding_cost_cents=_ceil(financing)),
                estimated_stress_loss_cents=0, estimate_basis="Outstanding borrowing is a liability; expected carrying cost is not investment income"))
        stress_loss = sum(_fee(plan.targets[i], stress_pct[i]) for i in (1, 2, 3))
        score = interest + price_return - forced_cost - financing - wealth_loss - rewards.risk_aversion * stress_loss
        return score, interest, price_return, forced_cost, financing, wealth_loss, stress_loss, tuple(returns)

    assessments = []
    best = None
    feasible = 0
    seen = set()
    truncated = False
    for seed_index, seed in enumerate(seeds):
        surplus = max(0, seed.cash_now - mandatory)
        allocations = [(0, 0, 0)]
        allocations += [tuple(surplus * b // 10000 for b in weights) for weights in product(sorted(req.allocation_grid_bps), repeat=3) if sum(weights) <= 10000]
        rooms = tuple(max(0, min(surplus, sum(seed.targets) * limits[t].max_allocation_bps // 10000 - seed.targets[t])) if t in limits else surplus for t in (1, 2, 3))
        allocations += [tuple(rooms[i] if choices[i] else 0 for i in range(3)) for choices in product((False, True), repeat=3)]
        allocations.append(tuple(max(0, _ceil(Decimal(sum(seed.targets)) * limits[i].min_allocation_bps / 10000) - seed.targets[i]) for i in (1, 2, 3)))
        for allocation in allocations:
            plan = seed.copy()
            for tier, amount in enumerate(allocation, 1): buy(plan, tier, amount)
            key = (tuple(plan.targets), plan.debt, tuple((o.action, o.position_id, o.amount_cents, o.quantity) for o in plan.orders))
            if key in seen: continue
            if len(assessments) >= req.max_candidates:
                truncated = True; break
            seen.add(key)
            reason = assess(plan)
            details = economics(plan) if reason is None else None
            score = details[0] if details else None
            assessments.append(CandidateAssessment(candidate=f"seed-{seed_index}:allocation-{allocation}", feasible=reason is None,
                objective_cents=score, reason=reason or "reserve, timed funding, exposure, debt and stress constraints satisfied"))
            if reason is None:
                feasible += 1
                rank = (score, -len(plan.orders), plan.targets[0], -plan.targets[3], -plan.targets[2], -plan.targets[1])
                if best is None or rank > best[0]: best = (rank, plan, details)
        if truncated: break
    if best is None:
        chosen, details = initial, (None, *economics(initial)[1:])
        summary, action, legacy = "WARNING", "LIQUIDITY_WARNING", "LIQUIDITY_WARNING"
    else:
        _, chosen, details = best
        kinds = {o.action for o in chosen.orders}
        purchases = bool(kinds & {"INVEST_REPO", "BUY_BONDS", "BUY_EQUITIES"})
        sales = bool(kinds & {"REDEEM_REPO", "SELL_BONDS", "SELL_EQUITIES"})
        summary = "HOLD" if not kinds else "REBALANCE" if purchases and sales or kinds & {"BORROW_OVERDRAFT", "REPAY_OVERDRAFT"} else "INVEST" if purchases else "LIQUIDATE"
        action = "HOLD" if not kinds else "ALLOCATE"
        legacy = "HOLD" if not kinds else "SWEEP" if kinds == {"INVEST_REPO"} and len(chosen.orders) == 1 else "WITHDRAW" if kinds == {"REDEEM_REPO"} and len(chosen.orders) == 1 else None
    score, income, gain, forced, finance, loss, stress, returns = details
    if best is None:
        warnings.append("No feasible generated plan: " + "; ".join(sorted({a.reason for a in assessments})[:5]))
    actual_costs = CostBreakdown(**{field: sum(getattr(o.expected_costs, field) for o in chosen.orders) + (_ceil(finance) if field == "funding_cost_cents" else 0) for field in CostBreakdown.model_fields})
    explanations = (
        f"model={rewards.model_version}; policy={rewards.policy_version}; assumptions={rewards.assumption_reference}; expected, not realized",
        f"mandatory_cash_cents={mandatory}; target_cash_cents={chosen.targets[0]}; candidate_count={len(assessments)}; feasible_count={feasible}",
        f"objective = income({income}) + price_change({gain}) - expected_exit_cost({forced}) - financing_after_savings({finance}; avoided={chosen.interest_saved}) - immediate_wealth_loss({loss}) - risk_aversion({rewards.risk_aversion}) * stress_loss({stress}) = {score}",
        "Target budget is trade-only pro-forma gross assets, before exogenous banking flows/maturities; outstanding debt is separate.",
        "New investment uses only cash available at decision time above reserve; future sales and maturities cannot finance immediate purchases.",
        "Observed canonical market values are preserved; explicit quantity/index convention applies only to new purchases; YTM is not a coupon.",
        "Nominal and supplied-scenario timed cash paths include fees, permitted sale arrival, removed old repo receipts and new repo principal maturity once.",
        "Finite rule-assisted candidate search is not a proof of global optimality; no future realized prices, trade execution or ledger mutation.",
        *warnings,
    )
    decision = FourTierDecisionResult(**source, as_of=p.as_of, action=action, reserve=reserve,
        orders=tuple(chosen.orders) if best else (), reason=f"{summary}: objective_cents={score}; cash_cents={chosen.targets[0]}; reserve_cents={mandatory}; stress_loss_cents={stress}; "
            + ("no generated plan satisfies the constraints" if best is None else "highest scoring feasible generated plan"),
        request_id=req.request_id, feasible=best is not None, allocation_budget_cents=sum(chosen.targets),
        targets=AllocationTargets(**dict(zip(("tier0_target_cents", "tier1_allocation_cents", "tier2_allocation_cents", "tier3_allocation_cents"), chosen.targets))),
        target_overdraft_principal_cents=chosen.debt, expected_costs=actual_costs,
        estimated_market_risk_loss_cents=stress, instrument_returns=returns, policy=effective_policy, explanations=explanations)
    return AllocationOptimizerResult(summary_action=summary, decision=decision, risk=risk, model_version=rewards.model_version,
        policy_version=rewards.policy_version, assumption_reference=rewards.assumption_reference, reward_assumptions=rewards,
        objective_cents=score,
        estimated_income_cents=_floor(income), estimated_price_change_cents=_floor(gain), expected_forced_liquidation_cost_cents=_ceil(forced),
        modeled_financing_cost_cents=_ceil(finance), estimated_financing_savings_cents=_floor(chosen.interest_saved),
        immediate_wealth_loss_cents=loss, cash_available_at_decision_after_orders_cents=chosen.cash_now,
        projected_nominal_funding_gap_cents=peak_gap(chosen, risk.path_before_liquidation),
        projected_scenario_failure_weight=sum((weight for weight, path in scenario_paths if peak_gap(chosen, path)), Decimal(0)) if scenario_paths else None,
        evaluated_candidates=len(assessments),
        feasible_candidates=feasible, search_truncated=truncated, assessments=tuple(assessments), legacy_action_hint=legacy)
