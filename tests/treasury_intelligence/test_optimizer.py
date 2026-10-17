from datetime import datetime, timedelta
from decimal import Decimal, localcontext
import json
from pathlib import Path

import pytest

import treasury_intelligence as e
from treasury_intelligence import portfolio as p

NOW = datetime(2026, 1, 1, 17)
D = Decimal
FIXTURE = Path(__file__).parent / "fixtures/canonical_liquidity_portfolio.json"


def portfolio(cash=1000000, repo=0, bond=0, equity=0, debt=0, early=False, hour=17):
    raw = json.loads(FIXTURE.read_text())
    raw["cash"].update(balance_cents=cash, liquidity=dict(classification="IMMEDIATE", available_cents=cash, locked_cents=0, liquidatable_value_cents=cash))
    for key, value in (("repo_positions", repo), ("bond_positions", bond), ("equity_positions", equity)):
        if not value: raw[key] = []; continue
        item = raw[key][0]
        item["liquidity"] = dict(classification="LOCKED" if key == "repo_positions" else "LIQUIDATABLE",
            available_cents=0, locked_cents=value if key == "repo_positions" else 0,
            liquidatable_value_cents=value if key != "repo_positions" or early else 0)
        if key == "repo_positions":
            item.update(principal_cents=value, market_value_cents=value, accrued_interest_cents=0, early_redemption_allowed=early)
        else: item["current_market_value_cents"] = value
    if debt:
        raw["overdrafts"][0].update(borrowed_cents=debt, outstanding_principal_cents=debt,
            financing_cost_cents=0, paid_financing_cost_cents=0, outstanding_financing_cost_cents=0)
    else: raw["overdrafts"] = []
    raw["valuation"].update(tier0_cash_cents=cash, tier1_principal_cents=repo, tier1_value_cents=repo,
        tier2_market_value_cents=bond, tier3_market_value_cents=equity, total_portfolio_value_cents=cash + repo + bond + equity,
        immediately_available_cents=cash, liquidatable_value_cents=cash + bond + equity + (repo if early else 0),
        restricted_value_cents=repo, liabilities_cents=debt, net_portfolio_value_cents=cash + repo + bond + equity - debt)
    rates = dict(time_basis="UNSPECIFIED", observed_at=NOW, repo_apy_pct="5", bond_yield_pct="4.8", equity_volatility_pct="18", overdraft_apr_pct="12")
    prices = dict(time_basis="UNSPECIFIED", observed_at=NOW, bond_price_index="100", bond_modified_duration_years="1.92", equity_index_price="5000")
    if raw["bond_positions"]:
        b = raw["bond_positions"][0]
        b.update(current_market_price_index="100", market_observation_timestamp=NOW, supplied_yield_pct="4.8", modified_duration="1.92")
    if raw["equity_positions"]:
        q = raw["equity_positions"][0]
        q.update(current_market_price_index="5000", market_observation_timestamp=NOW, supplied_volatility_pct="18")
    raw.update(market_rates=rates, market_prices=prices)
    if hour != 17:
        at = NOW.replace(hour=hour)
        raw["as_of"] = at
        raw["valuation"]["valued_at"] = at
        # A later snapshot may still use earlier known source observations/marks.
    return p.PortfolioState.model_validate(raw)


def asset(tier, **updates):
    return e.AssetRewardAssumption(**(dict(tier=tier, stress_loss_pct="0", forced_liquidation_probability="0",
        liquidation_haircut_pct={1: "0.5", 2: "2", 3: "15"}[tier],
        usd_per_index_point_per_unit=None if tier == 1 else "1") | updates))


def request(*, state=None, reserve=100000, settings=None, assets=None, risk_aversion="1", **updates):
    state = portfolio() if state is None else state
    policy = p.FourTierTreasuryPolicy(**(dict(base_buffer_cents=reserve, uncertainty_multiplier_bps=10000,
        tolerance_bps=0, min_transfer_cents=1, max_allocation_bps=10000, repo_sweep_window_open=True) | (settings or {})))
    forecast = tuple(p.HourlyForecastPoint(time_basis="UNSPECIFIED", start_at=state.as_of + timedelta(hours=i),
        predicted_deposits_cents=0, predicted_withdrawals_cents=0, predicted_net_flow_cents=0,
        supplied_uncertainty_buffer_cents=0) for i in range(15))
    liquidity = e.FourTierLiquidityRiskRequest(portfolio=state, policy=policy, forecast=forecast,
        planning_horizon_hours=15, uncertainty_mode="calibrated_allowance",
        calibrated_allowance=e.CalibratedForecastAllowance(time_basis="UNSPECIFIED", calibrated_through=state.as_of,
            confidence="0.95", amount_cents=0, calibration_reference="test-only-supplied-allowance"),
        default_liquidation_delay_hours=0)
    rewards = e.AllocationRewardModel(time_basis="UNSPECIFIED", model_version="candidate-search-v1", policy_version="test-policy-v1",
        assumption_reference="test-supplied-sensitivity-not-measured-metrics", assumptions_available_at=state.as_of,
        holding_hours=15, risk_aversion=risk_aversion, assets=tuple(assets or (asset(1), asset(2), asset(3))))
    return e.AllocationOptimizerRequest(**(dict(request_id="optimizer-example", liquidity=liquidity, rewards=rewards) | updates))


def optimize(req):
    original = req.model_dump_json()
    result = e.recommend_four_tier_allocation(req)
    assert req.model_dump_json() == original
    assert e.AllocationOptimizerResult.model_validate_json(result.model_dump_json()) == result
    assert p.FourTierDecisionResult.model_validate_json(result.decision.model_dump_json()) == result.decision
    assert result.recommendation_only is True and result.execution_status == "NOT_EXECUTED"
    assert all(o.execution_status == "NOT_EXECUTED" for o in result.decision.orders)
    assert sum(result.decision.targets.amounts) == result.decision.allocation_budget_cents
    return result


def test_valid_17_hour_repo_allocation_and_cash_reserve():
    result = optimize(request())
    assert result.summary_action == "INVEST"
    assert result.legacy_action_hint == "SWEEP"
    targets = result.decision.targets
    assert targets.tier0_target_cents == 100000 and targets.tier1_allocation_cents == 900000
    order = result.decision.orders[0]
    assert order.action == "INVEST_REPO" and order.amount_cents == 900000
    assert order.expected_maturity_at == NOW + timedelta(hours=15)
    assert result.estimated_income_cents == 77
    assert result.decision.estimated_market_risk_loss_cents == 0


@pytest.mark.parametrize("state,settings", [(portfolio(hour=18), {}), (portfolio(), {"repo_sweep_window_open": False})])
def test_repo_closed_or_wrong_hour_rejected(state, settings):
    result = optimize(request(state=state, settings=settings))
    assert result.summary_action == "HOLD"
    assert not result.decision.orders


def test_no_cash_reserve_can_be_invested():
    result = optimize(request(state=portfolio(cash=100000)))
    assert result.summary_action == "HOLD"
    assert result.decision.targets.tier0_target_cents == 100000


def test_locked_nonredeemable_repo_never_funds_a_trade():
    result = optimize(request(state=portfolio(cash=0, repo=1000000), settings={"allow_early_repo_redemption": True}))
    assert result.summary_action == "WARNING"
    assert not result.decision.orders
    assert result.legacy_action_hint == "LIQUIDITY_WARNING"


def test_permitted_repo_break_cost_and_minimal_repair():
    result = optimize(request(state=portfolio(cash=0, repo=1000000, early=True),
        settings={"allow_early_repo_redemption": True}, assets=(asset(1), asset(2), asset(3))))
    assert result.summary_action == "LIQUIDATE"
    sale = result.decision.orders[0]
    assert sale.action == "REDEEM_REPO"
    assert sale.amount_cents - sale.estimated_cost_cents >= 100000
    assert sale.estimated_cost_cents == (sale.amount_cents * 5 + 999) // 1000
    assert result.immediate_wealth_loss_cents == sale.estimated_cost_cents
    assert result.decision.targets.tier0_target_cents >= result.decision.reserve.required_reserve_cents


def test_bond_and_equity_exposure_caps_and_positive_quantities():
    limits = tuple(p.TierAllocationLimit(tier=i, max_allocation_bps={0: 10000, 1: 0, 2: 3000, 3: 1000}[i]) for i in range(4))
    result = optimize(request(settings={"tier_limits": limits}, risk_aversion="0",
        assets=(asset(1), asset(2, expected_price_return_pct="2"), asset(3, expected_price_return_pct="3"))))
    assert result.decision.targets.tier2_allocation_cents == 300000
    assert result.decision.targets.tier3_allocation_cents == 100000
    assert all(o.quantity > 0 for o in result.decision.orders if o.tier in (2, 3))
    assert all(o.action != "INVEST_REPO" for o in result.decision.orders)
    assert result.legacy_action_hint is None


def test_exposure_cap_accounts_for_purchase_fees_reducing_asset_budget():
    limits = (p.TierAllocationLimit(tier=1, max_allocation_bps=0), p.TierAllocationLimit(tier=2, max_allocation_bps=3000),
              p.TierAllocationLimit(tier=3, max_allocation_bps=0))
    result = optimize(request(settings={"tier_limits": limits}, risk_aversion="0",
        assets=(asset(1), asset(2, expected_price_return_pct="5", trade_fee_pct="1"), asset(3))))
    targets = result.decision.targets
    assert targets.tier2_allocation_cents > 0
    assert targets.tier2_allocation_cents * 10000 <= result.decision.allocation_budget_cents * 3000
    assert result.decision.expected_costs.transaction_cost_cents > 0


def test_minimal_sale_rebalances_existing_concentration():
    result = optimize(request(state=portfolio(cash=100000, bond=900000), risk_aversion="0",
        settings={"allow_bond_liquidation": True, "repo_sweep_window_open": False,
            "tier_limits": (p.TierAllocationLimit(tier=2, max_allocation_bps=5000),)},
        assets=(asset(1), asset(2, expected_price_return_pct="5"), asset(3))))
    sale = next(o for o in result.decision.orders if o.action == "SELL_BONDS")
    assert 0 < sale.amount_cents < 900000
    assert result.decision.targets.tier2_allocation_cents * 10000 <= result.decision.allocation_budget_cents * 5000


def test_supplied_stronger_reserve_and_generic_cap_are_preserved():
    req = request(settings={"max_allocation_bps": 2000})
    stronger = p.FourTierReserveResult(time_basis="UNSPECIFIED", as_of=NOW, net_drain_cents=0,
        uncertainty_buffer_cents=0, base_buffer_cents=400000, required_reserve_cents=400000)
    result = optimize(e.AllocationOptimizerRequest.model_validate(req.model_dump() | {"supplied_reserve": stronger}))
    assert result.decision.targets.tier0_target_cents >= 400000
    assert result.decision.targets.tier1_allocation_cents <= 200000


def test_negative_expected_market_returns_hold_not_high_yield_chase():
    result = optimize(request(settings={"repo_sweep_window_open": False},
        assets=(asset(1), asset(2, expected_price_return_pct="-2"), asset(3, expected_price_return_pct="-5"))))
    assert result.summary_action == "HOLD"


def test_negative_floating_repo_quote_does_not_create_guaranteed_income():
    state = portfolio().model_dump()
    state["market_rates"]["repo_apy_pct"] = D("-1")
    result = optimize(request(state=p.PortfolioState.model_validate(state)))
    assert result.summary_action == "HOLD"


def test_declared_bond_yield_never_automatically_becomes_a_coupon():
    state = portfolio().model_dump()
    state["market_rates"]["bond_yield_pct"] = D("99")
    result = optimize(request(state=p.PortfolioState.model_validate(state), settings={"repo_sweep_window_open": False}))
    assert result.summary_action == "HOLD"
    bond_return = next(r for r in result.decision.instrument_returns if r.instrument == p.InstrumentId.TIER2_BOND)
    assert bond_return.expected_income_cents == 0


def test_high_equity_return_rejected_by_risk_cap():
    result = optimize(request(settings={"repo_sweep_window_open": False, "max_estimated_loss_cents": 0,
        "tier_limits": (p.TierAllocationLimit(tier=3, max_allocation_bps=10000),)},
        assets=(asset(1), asset(2), asset(3, expected_price_return_pct="100", stress_loss_pct="50"))))
    assert result.summary_action == "HOLD"
    assert any("stress loss" in a.reason for a in result.assessments)


def test_stress_penalty_prevents_unjustified_high_return_chasing():
    result = optimize(request(settings={"tier_limits": (p.TierAllocationLimit(tier=3, max_allocation_bps=10000),)},
        assets=(asset(1), asset(2), asset(3, expected_price_return_pct="1", stress_loss_pct="50"))))
    assert result.decision.targets.tier3_allocation_cents == 0
    assert result.decision.targets.tier1_allocation_cents > 0


def test_fixed_trade_cost_can_make_investment_uneconomic():
    result = optimize(request(assets=(asset(1, fixed_trade_fee_cents=1000), asset(2), asset(3))))
    assert result.summary_action == "HOLD"


def test_forced_liquidation_cost_is_an_explicit_expected_cost():
    result = optimize(request(settings={"repo_sweep_window_open": False,
        "tier_limits": (p.TierAllocationLimit(tier=3, max_allocation_bps=10000),)}, risk_aversion="0",
        assets=(asset(1), asset(2), asset(3, expected_price_return_pct="5", forced_liquidation_probability="1"))))
    assert result.summary_action == "HOLD"  # 5% expected gain cannot pay 15% certain modeled fire-sale cost.


def test_new_position_respects_scenario_market_stress_even_without_existing_equity():
    req = request(settings={"repo_sweep_window_open": False, "max_estimated_loss_cents": 100,
        "tier_limits": (p.TierAllocationLimit(tier=3, max_allocation_bps=10000),)},
        assets=(asset(1), asset(2), asset(3, expected_price_return_pct="100")))
    data = req.model_dump()
    data["liquidity"]["market_stress"]["equity_drawdown_pct"] = "50"
    result = optimize(e.AllocationOptimizerRequest.model_validate(data))
    assert result.decision.targets.tier3_allocation_cents == 0


@pytest.mark.parametrize("tier,fee", [(2, "2"), (3, "15")])
def test_market_liquidation_includes_source_haircut(tier, fee):
    state = portfolio(cash=0, bond=1000000 if tier == 2 else 0, equity=1000000 if tier == 3 else 0)
    result = optimize(request(state=state, settings={"repo_sweep_window_open": False,
        "allow_bond_liquidation": True, "allow_emergency_equity_liquidation": True}, risk_aversion="0"))
    assert result.summary_action == "LIQUIDATE"
    sale = result.decision.orders[0]
    expected = int((D(sale.amount_cents) * D(fee) / 100).to_integral_value(rounding="ROUND_CEILING"))
    assert sale.estimated_cost_cents == expected
    assert sale.expected_proceeds_cents == sale.amount_cents - expected
    assert result.decision.allocation_budget_cents == 1000000 - expected


def test_expected_market_loss_can_justify_liquidation_without_invented_realized_pnl():
    result = optimize(request(state=portfolio(cash=100000, equity=900000), risk_aversion="0",
        settings={"allow_emergency_equity_liquidation": True, "repo_sweep_window_open": False},
        assets=(asset(1), asset(2), asset(3, expected_price_return_pct="-30"))))
    assert any(o.action == "SELL_EQUITIES" for o in result.decision.orders)
    assert result.decision.targets.tier3_allocation_cents == 0
    assert result.immediate_wealth_loss_cents == 135000  # 15% slippage, not a second price-index loss.


def test_all_four_tiers_can_be_recommended_in_one_constrained_plan():
    limits = tuple(p.TierAllocationLimit(tier=i, max_allocation_bps={0: 10000, 1: 4000, 2: 3000, 3: 1000}[i]) for i in range(4))
    result = optimize(request(settings={"tier_limits": limits}, risk_aversion="0.1",
        assets=(asset(1), asset(2, expected_price_return_pct="0.5", stress_loss_pct="1"),
                asset(3, expected_price_return_pct="1", stress_loss_pct="5"))))
    assert all(value > 0 for value in result.decision.targets.amounts)
    assert {o.tier for o in result.decision.orders} == {1, 2, 3}


def test_delayed_sale_does_not_fund_immediate_payout():
    req = request(state=portfolio(cash=0, bond=1000000), settings={"allow_bond_liquidation": True})
    data = req.model_dump()
    data["liquidity"]["default_liquidation_delay_hours"] = 1
    data["liquidity"]["forecast"][0]["predicted_withdrawals_cents"] = 10000
    result = optimize(e.AllocationOptimizerRequest.model_validate(data))
    assert result.summary_action == "WARNING"
    assert any("interim" in a.reason for a in result.assessments)


def test_future_repo_maturity_does_not_finance_a_current_investment():
    state = portfolio(cash=100000, repo=900000)
    req = request(state=state)
    settlement = e.RepoCashSettlement(time_basis="UNSPECIFIED", position_id=state.repo_positions[0].id,
        available_at=NOW + timedelta(hours=15), amount_cents=900000)
    data = req.model_dump()
    data["liquidity"]["repo_settlements"] = (settlement,)
    result = optimize(e.AllocationOptimizerRequest.model_validate(data))
    assert result.summary_action == "HOLD"


def test_new_repo_settlement_outside_coverage_is_ineligible():
    result = optimize(request(new_repo_settlement_delay_hours=1))
    assert not any(o.action == "INVEST_REPO" for o in result.decision.orders)


def test_debt_repayment_is_compared_to_investing():
    result = optimize(request(state=portfolio(cash=1000000, debt=500000),
        settings={"allow_overdraft": True, "max_overdraft_cents": 1000000}))
    assert any(o.action == "REPAY_OVERDRAFT" for o in result.decision.orders)
    assert result.decision.target_overdraft_principal_cents == 0
    assert result.decision.allocation_budget_cents == 500000


def test_emergency_borrowing_is_a_liability_not_investment_capital():
    req = request(state=portfolio(cash=0), settings={"allow_overdraft": True, "max_overdraft_cents": 1000000})
    data = req.model_dump()
    data["liquidity"].update(available_overdraft_credit_cents=200000, modeled_overdraft_apr_pct="12")
    result = optimize(e.AllocationOptimizerRequest.model_validate(data))
    assert result.summary_action == "REBALANCE"
    assert {o.action for o in result.decision.orders} == {"BORROW_OVERDRAFT"}
    assert result.decision.targets.tier0_target_cents == result.decision.target_overdraft_principal_cents == 100000
    assert result.modeled_financing_cost_cents > 0
    assert result.decision.targets.tier1_allocation_cents == 0


def test_warning_does_not_report_existing_financing_cost_as_zero():
    result = optimize(request(state=portfolio(cash=0, debt=100000),
        settings={"allow_overdraft": True, "max_overdraft_cents": 100000}))
    assert result.summary_action == "WARNING" and result.objective_cents is None
    assert result.modeled_financing_cost_cents == 21
    assert result.decision.expected_costs.funding_cost_cents == 21


def test_quantity_convention_is_required_and_no_future_assumptions():
    with pytest.raises(ValueError): asset(2, usd_per_index_point_per_unit=None)
    req = request()
    data = req.model_dump()
    data["rewards"]["assumptions_available_at"] = NOW + timedelta(hours=1)
    with pytest.raises(ValueError): e.AllocationOptimizerRequest.model_validate(data)
    with pytest.raises(ValueError): asset(3, expected_price_return_pct=0.1)


def test_large_unit_quantum_never_emits_zero_or_negative_purchase_quantity():
    result = optimize(request(state=portfolio(cash=100100), settings={"repo_sweep_window_open": False,
        "tier_limits": (p.TierAllocationLimit(tier=2, max_allocation_bps=10000), p.TierAllocationLimit(tier=3, max_allocation_bps=10000))}, risk_aversion="0",
        assets=(asset(1), asset(2, expected_price_return_pct="100", quantity_decimal_places=0),
                asset(3, expected_price_return_pct="100", quantity_decimal_places=0))))
    assert result.summary_action == "HOLD"


def test_market_investment_requires_explicit_exposure_caps_even_with_high_reward():
    result = optimize(request(settings={"repo_sweep_window_open": False}, risk_aversion="0",
        assets=(asset(1), asset(2, expected_price_return_pct="100"), asset(3, expected_price_return_pct="100"))))
    assert result.summary_action == "HOLD"


def test_early_repo_redemption_cannot_keep_the_same_maturity_credit():
    state = portfolio(cash=0, repo=100000, early=True)
    req = request(state=state, reserve=0, settings={"allow_early_repo_redemption": True})
    data = req.model_dump()
    data["liquidity"]["repo_settlements"] = (e.RepoCashSettlement(time_basis="UNSPECIFIED",
        position_id=state.repo_positions[0].id, available_at=NOW + timedelta(hours=15), amount_cents=100000),)
    data["liquidity"]["obligations"] = (e.CommittedObligation(time_basis="UNSPECIFIED",
        obligation_id="due-at-maturity", due_at=NOW + timedelta(hours=15), amount_cents=100000),)
    result = optimize(e.AllocationOptimizerRequest.model_validate(data))
    assert result.summary_action == "HOLD"
    assert result.decision.reserve.required_reserve_cents == 0
    assert not result.decision.orders


def test_determinism_canonical_adapter_and_legacy_contract_preservation():
    req = request()
    first = optimize(req)
    assert optimize(req).model_dump_json() == first.model_dump_json()
    assert p.recommend_portfolio_allocation(req) == first.decision
    assert e.recommend_portfolio_allocation(req) == first.decision
    assert first.model_version == "candidate-search-v1"
    assert first.policy_version == "test-policy-v1"
    assert "objective =" in first.decision.explanations[2]


def test_precision_independence_and_candidate_budget():
    req = request(max_candidates=1)
    with localcontext() as ctx:
        ctx.prec = 2
        result = optimize(req)
    assert result.evaluated_candidates == 1 and result.search_truncated
    assert result.summary_action == "HOLD"


def test_executed_status_cannot_be_forged():
    result = optimize(request())
    data = result.model_dump()
    data["decision"]["orders"][0]["execution_status"] = "EXECUTED"
    with pytest.raises(ValueError): e.AllocationOptimizerResult.model_validate(data)
