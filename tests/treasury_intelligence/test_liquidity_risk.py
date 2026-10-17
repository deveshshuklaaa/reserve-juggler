from datetime import datetime, timedelta, timezone
from decimal import Decimal, localcontext
import json
from pathlib import Path
from uuid import UUID

import pytest

import treasury_intelligence as e
from treasury_intelligence import portfolio as p

D = Decimal
NOW = datetime(2026, 1, 1, 17)
MILLION = 100_000_000
FIXTURE = Path(__file__).parent / "fixtures/canonical_liquidity_portfolio.json"


def state(cash=0, repo=0, bond=0, equity=0, debt=0, early=False):
    raw = json.loads(FIXTURE.read_text())
    raw["cash"].update(balance_cents=cash, liquidity=dict(classification="IMMEDIATE", available_cents=cash,
        locked_cents=0, liquidatable_value_cents=cash))
    for key, value in (("repo_positions", repo), ("bond_positions", bond), ("equity_positions", equity)):
        if not value:
            raw[key] = []
            continue
        record = raw[key][0]
        record["liquidity"] = dict(classification="LOCKED" if key == "repo_positions" else "LIQUIDATABLE",
            available_cents=0, locked_cents=value if key == "repo_positions" else 0,
            liquidatable_value_cents=value if key != "repo_positions" or early else 0)
        if key == "repo_positions":
            record.update(principal_cents=value, market_value_cents=value, accrued_interest_cents=0,
                early_redemption_allowed=early)
        else:
            record["current_market_value_cents"] = value
    if debt:
        raw["overdrafts"][0].update(borrowed_cents=debt, outstanding_principal_cents=debt,
            financing_cost_cents=20, paid_financing_cost_cents=5, outstanding_financing_cost_cents=15)
    else:
        raw["overdrafts"] = []
    raw["valuation"].update(tier0_cash_cents=cash, tier1_principal_cents=repo, tier1_value_cents=repo,
        tier2_market_value_cents=bond, tier3_market_value_cents=equity,
        total_portfolio_value_cents=cash + repo + bond + equity, immediately_available_cents=cash,
        liquidatable_value_cents=cash + bond + equity + (repo if early else 0), restricted_value_cents=repo,
        liabilities_cents=debt + (15 if debt else 0),
        net_portfolio_value_cents=cash + repo + bond + equity - debt - (15 if debt else 0))
    return p.PortfolioState.model_validate(raw)


def policy(**overrides):
    return p.FourTierTreasuryPolicy(**(dict(base_buffer_cents=0, uncertainty_multiplier_bps=10000,
        tolerance_bps=0, min_transfer_cents=0, max_allocation_bps=10000,
        repo_sweep_window_open=False) | overrides))


def path(*flows):
    return tuple(p.HourlyForecastPoint(time_basis="UNSPECIFIED", start_at=NOW + timedelta(hours=i),
        predicted_deposits_cents=deposit, predicted_withdrawals_cents=withdrawal,
        predicted_net_flow_cents=deposit - withdrawal, supplied_uncertainty_buffer_cents=999999)
        for i, (deposit, withdrawal) in enumerate(flows))


def request(*, portfolio=None, forecast=None, settings=None, allowance=0, **kwargs):
    forecast = path((0, 0)) if forecast is None else forecast
    return e.FourTierLiquidityRiskRequest(portfolio=state() if portfolio is None else portfolio,
        policy=policy() if settings is None else settings, forecast=forecast,
        planning_horizon_hours=len(forecast), uncertainty_mode="calibrated_allowance",
        calibrated_allowance=e.CalibratedForecastAllowance(time_basis="UNSPECIFIED", amount_cents=allowance,
            confidence="0.95", calibration_reference="test-supplied-calibration", calibrated_through=NOW), **kwargs)


def calculate(req):
    before = req.model_dump_json()
    result = e.calculate_four_tier_liquidity_risk(req)
    assert req.model_dump_json() == before
    assert e.FourTierLiquidityRiskResult.model_validate_json(result.model_dump_json()) == result
    assert isinstance(result.reserve, p.FourTierReserveResult)
    assert result.actual_payout_failure is None and result.execution_status == "NOT_EXECUTED"
    return result


def test_eight_million_withdrawal_before_eight_million_deposit():
    result = calculate(request(forecast=path((0, 8 * MILLION), (8 * MILLION, 0))))
    assert result.nominal_peak_requirement_cents == 8 * MILLION
    assert result.reserve.required_reserve_cents == 8 * MILLION
    assert result.path_before_liquidation[0].projected_cash_cents == -8 * MILLION
    assert result.path_before_liquidation[-1].projected_cash_cents == 0


def test_intrabucket_withdrawal_precedes_deposit():
    result = calculate(request(forecast=path((8 * MILLION, 8 * MILLION))))
    assert result.reserve.required_reserve_cents == 8 * MILLION


def test_supplied_uncertainty_once_and_operational_buffer():
    result = calculate(request(forecast=path((0, 12_500_000_00)), allowance=MILLION,
        settings=policy(base_buffer_cents=MILLION // 2)))
    assert result.reserve.required_reserve_cents == 14 * MILLION
    assert result.reserve.uncertainty_buffer_cents == MILLION  # Point's provisional buffer is ignored.


@pytest.mark.parametrize("delay,expected", [(0, 0), (1, 8 * MILLION)])
def test_repo_maturity_and_settlement_delay(delay, expected):
    portfolio = state(repo=8 * MILLION)
    flows = [(0, 0)] * 17
    flows[15] = (0, 8 * MILLION)  # 08:00 the next day.
    settlement = e.RepoCashSettlement(time_basis="UNSPECIFIED", position_id=portfolio.repo_positions[0].id,
        available_at=NOW + timedelta(hours=15 + delay), amount_cents=8 * MILLION)
    result = calculate(request(portfolio=portfolio, forecast=path(*flows), repo_settlements=(settlement,)))
    assert result.nominal_peak_requirement_cents == expected
    assert result.available_cash_cents == 0


def test_locked_repo_is_not_immediate_or_an_automatic_maturity_credit():
    result = calculate(request(portfolio=state(repo=10 * MILLION), forecast=path((0, 8 * MILLION))))
    assert result.available_cash_cents == 0 and result.restricted_liquidity_cents == 10 * MILLION
    assert result.funding_shortfall_before_liquidation_cents == result.funding_shortfall_after_liquidation_cents == 8 * MILLION


def test_maturity_does_not_erase_an_earlier_peak():
    portfolio = state(repo=8 * MILLION)
    schedule = e.RepoCashSettlement(time_basis="UNSPECIFIED", position_id=portfolio.repo_positions[0].id,
        available_at=NOW + timedelta(hours=15), amount_cents=8 * MILLION)
    result = calculate(request(portfolio=portfolio, forecast=path((0, 8 * MILLION), *([(0, 0)] * 15)),
        repo_settlements=(schedule,)))
    assert result.reserve.required_reserve_cents == 8 * MILLION


def test_bond_equity_stress_and_liquidation_penalties():
    result = calculate(request(portfolio=state(bond=10000, equity=20000),
        settings=policy(allow_bond_liquidation=True, allow_emergency_equity_liquidation=True),
        market_stress=e.MarketStress(bond_drawdown_pct="10", equity_drawdown_pct="20")))
    bond, equity = result.liquidations
    assert (bond.stressed_value_cents, bond.liquidation_cost_cents, bond.net_proceeds_cents) == (9000, 180, 8820)
    assert (equity.stressed_value_cents, equity.liquidation_cost_cents, equity.net_proceeds_cents) == (16000, 2400, 13600)
    assert result.permitted_stress_liquidation_cents == 22420
    assert result.modeled_market_loss_cents == 5000


@pytest.mark.parametrize("delay,shortfall", [(0, 0), (1, 10000)])
def test_early_sale_settlement_delay_preserves_interim_pressure(delay, shortfall):
    result = calculate(request(portfolio=state(bond=20000), forecast=path((0, 10000), (0, 0)),
        settings=policy(allow_bond_liquidation=True), default_liquidation_delay_hours=delay))
    assert result.funding_shortfall_after_liquidation_cents == shortfall


def test_unpermitted_liquidation_remains_inaccessible():
    result = calculate(request(portfolio=state(bond=1000000, equity=1000000),
        forecast=path((0, 10000)), default_liquidation_delay_hours=0))
    assert result.permitted_stress_liquidation_cents == 0
    assert result.funding_shortfall_after_liquidation_cents == 10000


def test_market_drawdown_and_volatility_reduce_proceeds():
    common = dict(portfolio=state(equity=100000), settings=policy(allow_emergency_equity_liquidation=True))
    base = calculate(request(**common))
    stressed = calculate(request(**common, market_stress=e.MarketStress(equity_drawdown_pct="10", equity_volatility_multiplier="2")))
    assert stressed.permitted_stress_liquidation_cents < base.permitted_stress_liquidation_cents


def test_duration_stress_is_separate_from_supplied_observed_market_value():
    result = calculate(request(portfolio=state(bond=100000), settings=policy(allow_bond_liquidation=True),
        market_stress=e.MarketStress(bond_method="yield_shock", bond_yield_change_pct="1")))
    sale = result.liquidations[0]
    assert sale.observed_value_cents == 100000  # Never an index-times-quantity reconstruction.
    assert sale.stressed_value_cents == 98080  # 1.92 modified duration, +1 percentage-point yield.
    with pytest.raises(ValueError):
        e.MarketStress(bond_method="yield_shock", bond_drawdown_pct="2")


def test_early_break_removes_the_same_repo_maturity_credit():
    portfolio = state(repo=100000, early=True)
    schedule = e.RepoCashSettlement(time_basis="UNSPECIFIED", position_id=portfolio.repo_positions[0].id,
        available_at=NOW + timedelta(hours=15), amount_cents=100000)
    result = calculate(request(portfolio=portfolio, forecast=path(*([(0, 0)] * 16)), repo_settlements=(schedule,),
        settings=policy(allow_early_repo_redemption=True), default_liquidation_delay_hours=0))
    assert result.liquidations[0].liquidation_cost_cents == 500
    assert sum(x.repo_maturity_cents for x in result.path_after_liquidation) == 0
    assert sum(x.liquidation_inflow_cents for x in result.path_after_liquidation) == 99500
    assert result.path_after_liquidation[-1].projected_cash_cents == 99500


def test_booked_maturity_not_counted_again_and_duplicate_rejected():
    schedule = e.RepoCashSettlement(time_basis="UNSPECIFIED", position_id=UUID(int=123),
        available_at=NOW, amount_cents=10000, already_in_cash=True)
    result = calculate(request(portfolio=state(cash=10000), forecast=path((0, 10000)), repo_settlements=(schedule,)))
    assert result.reserve.required_reserve_cents == 10000
    assert sum(x.repo_maturity_cents for x in result.path_before_liquidation) == 0
    with pytest.raises(ValueError):
        request(repo_settlements=(schedule, schedule))
    portfolio = state(repo=10000)
    with pytest.raises(ValueError):
        request(portfolio=portfolio, repo_settlements=(schedule.model_copy(update={"position_id": portfolio.repo_positions[0].id}),))


@pytest.mark.parametrize("change", ["before_maturity", "unknown", "amount", "past"])
def test_invalid_maturity_attestation(change):
    portfolio = state(repo=10000)
    data = dict(time_basis="UNSPECIFIED", position_id=portfolio.repo_positions[0].id,
        available_at=NOW + timedelta(hours=15), amount_cents=10000)
    if change == "before_maturity": data["available_at"] = NOW + timedelta(hours=14)
    elif change == "unknown": data["position_id"] = UUID(int=999)
    elif change == "amount": data["amount_cents"] = 10001
    else: data["available_at"] = NOW - timedelta(hours=1)
    with pytest.raises(ValueError):
        request(portfolio=portfolio, repo_settlements=(e.RepoCashSettlement(**data),))


def test_explicit_committed_obligations_and_double_count_flag():
    obligation = e.CommittedObligation(time_basis="UNSPECIFIED", obligation_id="payroll", due_at=NOW, amount_cents=1000)
    result = calculate(request(obligations=(obligation,)))
    assert result.nominal_peak_requirement_cents == 1000
    included = obligation.model_copy(update={"already_in_forecast": True})
    assert calculate(request(forecast=path((0, 1000)), obligations=(included,))).nominal_peak_requirement_cents == 1000


def test_adverse_outflows_monotonically_increase_reserve():
    requirements = [calculate(request(forecast=path((500, amount), (0, 1000)))).reserve.required_reserve_cents
                    for amount in (0, 100, 1000, 10000)]
    assert requirements == sorted(requirements)


def test_overdraft_debt_is_not_an_asset_and_funding_has_cost():
    base = calculate(request(portfolio=state(debt=100000), forecast=path((0, 10000))))
    assert base.available_cash_cents == 0 and base.existing_liabilities_cents == 100015
    assert base.funding_shortfall_before_liquidation_cents == 10000
    funded = calculate(request(portfolio=state(debt=100000), forecast=path((0, 10000)),
        settings=policy(allow_overdraft=True, max_overdraft_cents=200000),
        available_overdraft_credit_cents=50000, modeled_overdraft_apr_pct="12"))
    assert funded.modeled_overdraft_draw_cents == 10000
    assert funded.modeled_overdraft_financing_cost_cents == 1
    assert funded.funding_gap_after_modeled_overdraft_cents == 0
    assert funded.reserve == base.reserve  # Borrowing never reduces the reserve requirement.
    assert funded.actual_payout_failure is None


def test_reserve_breach_is_not_actual_or_projected_payout_failure():
    result = calculate(request(portfolio=state(cash=100), settings=policy(base_buffer_cents=200)))
    assert result.reserve_breach
    assert not result.projected_funding_failure_before_liquidation
    assert result.actual_payout_failure is None
    assert result.expected_unfunded_cash_cents is None
    assert result.scenario_metrics_basis == "not_estimated"


def test_scenario_quantile_no_double_uncertainty_and_expected_shortfall():
    scenarios = (e.LiquidityScenario(scenario_id="normal", probability="0.8", forecast=path((0, 100))),
                 e.LiquidityScenario(scenario_id="stress", probability="0.2", forecast=path((0, 300))))
    req = e.FourTierLiquidityRiskRequest(portfolio=state(cash=150), policy=policy(base_buffer_cents=10),
        forecast=path((0, 50)), planning_horizon_hours=1, uncertainty_mode="scenario_quantile", confidence="0.8",
        scenarios=scenarios)
    result = calculate(req)
    assert result.nominal_peak_requirement_cents == 50
    assert result.reserve.net_drain_cents == 100
    assert result.reserve.uncertainty_buffer_cents == 0
    assert result.reserve.required_reserve_cents == 110
    assert result.expected_unfunded_cash_cents == 30
    assert result.tail_expected_shortfall_cents == 150
    assert result.scenario_reserve_breach_probability == result.scenario_funding_failure_probability_before == D("0.2")
    assert result.confidence == D("0.8")
    with pytest.raises(ValueError):
        e.FourTierLiquidityRiskRequest.model_validate(req.model_dump() | {"calibrated_allowance": request().calibrated_allowance})


def test_scenario_stress_changes_after_liquidation_failure_risk():
    scenarios = (e.LiquidityScenario(scenario_id="normal", probability="0.5", forecast=path((0, 8000))),
                 e.LiquidityScenario(scenario_id="market-crash", probability="0.5", forecast=path((0, 8000)),
                    market_stress=e.MarketStress(equity_drawdown_pct="50")))
    req = e.FourTierLiquidityRiskRequest(portfolio=state(equity=10000),
        policy=policy(allow_emergency_equity_liquidation=True, max_estimated_loss_cents=1000),
        forecast=path((0, 8000)), planning_horizon_hours=1, uncertainty_mode="scenario_quantile",
        scenarios=scenarios, default_liquidation_delay_hours=0)
    result = calculate(req)
    assert result.scenario_funding_failure_probability_before == 1
    assert result.scenario_funding_failure_probability_after == D("0.5")
    assert result.worst_scenario_market_loss_cents == 5000
    assert result.policy_violations


def test_partial_tail_mass_is_used_in_expected_shortfall():
    scenarios = (e.LiquidityScenario(scenario_id="low", probability="0.8", forecast=path((0, 0))),
                 e.LiquidityScenario(scenario_id="medium", probability="0.15", forecast=path((0, 100))),
                 e.LiquidityScenario(scenario_id="worst", probability="0.05", forecast=path((0, 300))))
    result = calculate(e.FourTierLiquidityRiskRequest(portfolio=state(), policy=policy(), forecast=path((0, 0)),
        planning_horizon_hours=1, uncertainty_mode="scenario_quantile", confidence="0.9", scenarios=scenarios))
    assert result.expected_unfunded_cash_cents == 30
    assert result.tail_expected_shortfall_cents == 200  # Top 10%: 5% * 300 + 5% * 100.


def test_policy_minimum_buffer_equity_exposure_and_risk_limits():
    result = calculate(request(portfolio=state(equity=100000),
        settings=policy(minimum_liquid_reserve_cents=5000, max_estimated_loss_cents=10,
            tier_limits=(p.TierAllocationLimit(tier=3, max_allocation_bps=5000),)),
        market_stress=e.MarketStress(equity_drawdown_pct="10")))
    assert result.minimum_reserve_topup_cents == result.reserve.required_reserve_cents == 5000
    assert len(result.policy_violations) == 2


def test_zero_balance_and_cent_rounded_stress_cost():
    empty = calculate(request())
    assert empty.reserve.required_reserve_cents == empty.available_cash_cents == 0
    tiny = calculate(request(portfolio=state(bond=1), settings=policy(allow_bond_liquidation=True)))
    assert tiny.liquidations[0].liquidation_cost_cents == 1
    assert tiny.liquidations[0].net_proceeds_cents == 0


def test_calibration_and_time_validation():
    req = request()
    for changed in (
        {"calibrated_allowance": None}, {"planning_horizon_hours": 2}, {"confidence": "0"},
        {"calibrated_allowance": req.calibrated_allowance.model_dump() | {"calibrated_through": NOW + timedelta(hours=1)}},
    ):
        with pytest.raises(ValueError):
            e.FourTierLiquidityRiskRequest.model_validate(req.model_dump() | changed)
    with pytest.raises(ValueError, match="first hour"):
        request(forecast=(path((0, 0))[0].model_copy(update={"start_at": NOW + timedelta(hours=1)}),))


def test_explicit_liquidation_schedule_and_horizon_truncation():
    portfolio = state(bond=20000)
    settlement = e.LiquidationSettlement(time_basis="UNSPECIFIED", position_id=portfolio.bond_positions[0].id,
        available_at=NOW + timedelta(hours=2))
    req = request(portfolio=portfolio, forecast=path((0, 0), (0, 10000), (0, 99999999)),
        settings=policy(allow_bond_liquidation=True), liquidation_settlements=(settlement,))
    req = e.FourTierLiquidityRiskRequest.model_validate(req.model_dump() | {"planning_horizon_hours": 2})
    result = calculate(req)
    assert result.reserve.net_drain_cents == 10000
    assert result.funding_shortfall_after_liquidation_cents == 10000  # Sale arrives after 18:00 debit.
    assert result.planning_end_at == NOW + timedelta(hours=2)


def test_explicit_utc_synthetic_clock_is_supported_without_conversion():
    raw = state(cash=100).model_dump(mode="json")
    def convert(item):
        if isinstance(item, dict):
            for key, value in item.items():
                if key == "time_basis": item[key] = "UTC"
                elif key == "source_type": item[key] = "SYNTHETIC"
                elif key in ("dataset_id", "source_observation_timestamp"): item[key] = None
                elif isinstance(value, str) and key in ("as_of", "valued_at", "entered_at", "acquired_at", "borrowed_at"):
                    item[key] = value + "Z"
                else: convert(value)
        elif isinstance(item, list):
            for value in item: convert(value)
    convert(raw)
    portfolio = p.PortfolioState.model_validate(raw)
    at = NOW.replace(tzinfo=timezone.utc)
    req = e.FourTierLiquidityRiskRequest(portfolio=portfolio, policy=policy(),
        forecast=(p.HourlyForecastPoint(time_basis="UTC", start_at=at, predicted_deposits_cents=0,
            predicted_withdrawals_cents=50, predicted_net_flow_cents=-50, supplied_uncertainty_buffer_cents=0),),
        planning_horizon_hours=1, uncertainty_mode="calibrated_allowance",
        calibrated_allowance=e.CalibratedForecastAllowance(time_basis="UTC", calibrated_through=at,
            confidence="0.95", amount_cents=0, calibration_reference="synthetic-test"))
    result = calculate(req)
    assert result.time_basis == result.reserve.time_basis == "UTC"
    assert result.reserve.required_reserve_cents == 50


def test_precise_probability_validation_and_context_independence():
    scenarios = (e.LiquidityScenario(scenario_id="a", probability="0.25", forecast=path((0, 1))),
                 e.LiquidityScenario(scenario_id="b", probability="0.75", forecast=path((0, 3))))
    req = e.FourTierLiquidityRiskRequest(portfolio=state(), policy=policy(), forecast=path((0, 0)),
        planning_horizon_hours=1, uncertainty_mode="scenario_quantile", confidence="1", scenarios=scenarios)
    expected = calculate(req)
    with localcontext() as ctx:
        ctx.prec = 2
        assert calculate(req) == expected
    assert expected.reserve.required_reserve_cents == expected.tail_expected_shortfall_cents == 3
    with pytest.raises(ValueError):
        e.FourTierLiquidityRiskRequest.model_validate(req.model_dump() | {"scenarios": [scenarios[0].model_dump()]})


def test_legacy_shapes_are_not_silently_adapted_and_native_source_net_is_not_overwritten():
    old = json.loads((FIXTURE.parent / "four_tier_request.json").read_text())
    with pytest.raises(ValueError):
        request(portfolio=old["portfolio"])
    flows = (p.HourlyForecastPoint(time_basis="UNSPECIFIED", start_at=NOW, predicted_deposits_cents=100,
        predicted_withdrawals_cents=200, predicted_net_flow_cents=-999, supplied_uncertainty_buffer_cents=999),)
    req = request(forecast=flows)
    assert calculate(req).nominal_peak_requirement_cents == 200  # Deposits arrive later, at hour end.
    assert req.forecast[0].predicted_net_flow_cents == -999
