"""Tests for Multi-Asset Monte Carlo risk simulation (TASK RJ-M1-12)."""
from datetime import datetime, timedelta
from decimal import Decimal
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

import treasury_intelligence as e
from treasury_intelligence import portfolio as p
from treasury_intelligence.monte_carlo_risk import (
    MONTE_CARLO_RISK_MODEL_VERSION,
    MultiAssetMonteCarloRiskResult,
    generate_multi_asset_scenarios,
    simulate_multi_asset_monte_carlo_risk,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"
CANONICAL_PORTFOLIO_PATH = FIXTURES_DIR / "canonical_liquidity_portfolio.json"
ORGANIZER_SERIES_PATH = FIXTURES_DIR / "organizer_hourly_series.json"

NOW = datetime(2026, 1, 3, 17)  # Saturday 17:00 (allows 65 hours of prior history)


@pytest.fixture
def hourly_series_168() -> tuple[p.OrganizerHourlyObservation, ...]:
    """168 contiguous real hourly observations from the organizer dataset fixture."""
    data = json.loads(ORGANIZER_SERIES_PATH.read_text(encoding="utf-8"))
    return tuple(p.OrganizerHourlyObservation.model_validate(r) for r in data)


def make_portfolio(
    as_of: datetime = NOW,
    cash: int = 50_000_000,
    repo: int = 20_000_000,
    bond: int = 20_000_000,
    equity: int = 10_000_000,
    debt: int = 0,
    allow_early_break: bool = False,
) -> p.PortfolioState:
    """Create a validated four-tier portfolio state at as_of."""
    raw = json.loads(CANONICAL_PORTFOLIO_PATH.read_text(encoding="utf-8"))
    raw["as_of"] = as_of.isoformat()
    raw["source_observation_timestamp"] = as_of.isoformat()

    # Cash position
    raw["cash"].update(
        balance_cents=cash,
        liquidity=dict(classification="IMMEDIATE", available_cents=cash, locked_cents=0, liquidatable_value_cents=cash),
    )

    # Repo positions
    if repo > 0:
        raw["repo_positions"][0].update(
            principal_cents=repo,
            market_value_cents=repo,
            accrued_interest_cents=0,
            entered_at=as_of.isoformat(),
            scheduled_maturity_at=(as_of + timedelta(hours=15)).isoformat(),
            early_redemption_allowed=allow_early_break,
            liquidity=dict(
                classification="LOCKED",
                available_cents=0,
                locked_cents=repo,
                liquidatable_value_cents=repo if allow_early_break else 0,
            ),
        )
    else:
        raw["repo_positions"] = []

    # Bond positions
    if bond > 0:
        raw["bond_positions"][0].update(
            current_market_value_cents=bond,
            liquidity=dict(classification="LIQUIDATABLE", available_cents=0, locked_cents=0, liquidatable_value_cents=bond),
        )
    else:
        raw["bond_positions"] = []

    # Equity positions
    if equity > 0:
        raw["equity_positions"][0].update(
            current_market_value_cents=equity,
            liquidity=dict(classification="LIQUIDATABLE", available_cents=0, locked_cents=0, liquidatable_value_cents=equity),
        )
    else:
        raw["equity_positions"] = []

    # Overdraft
    if debt > 0:
        raw["overdrafts"][0].update(
            borrowed_cents=debt,
            outstanding_principal_cents=debt,
            financing_cost_cents=100,
            paid_financing_cost_cents=0,
            outstanding_financing_cost_cents=100,
        )
        liab = debt + 100
    else:
        raw["overdrafts"] = []
        liab = 0

    total = cash + repo + bond + equity
    raw["valuation"].update(
        valued_at=as_of.isoformat(),
        tier0_cash_cents=cash,
        tier1_principal_cents=repo,
        tier1_value_cents=repo,
        tier2_market_value_cents=bond,
        tier3_market_value_cents=equity,
        total_portfolio_value_cents=total,
        immediately_available_cents=cash,
        liquidatable_value_cents=cash + bond + equity + (repo if allow_early_break else 0),
        restricted_value_cents=repo,
        liabilities_cents=liab,
        net_portfolio_value_cents=total - liab,
    )
    if raw.get("market_rates"):
        raw["market_rates"]["observed_at"] = as_of.isoformat()
    if raw.get("market_prices"):
        raw["market_prices"]["observed_at"] = as_of.isoformat()

    return p.PortfolioState.model_validate(raw)


def make_policy(**overrides) -> p.FourTierTreasuryPolicy:
    """Create a standard four-tier policy for tests."""
    defaults = dict(
        base_buffer_cents=1_000_000,
        uncertainty_multiplier_bps=10000,
        tolerance_bps=0,
        min_transfer_cents=0,
        max_allocation_bps=10000,
        repo_sweep_window_open=True,
        allow_early_repo_redemption=True,
        allow_bond_liquidation=True,
        allow_emergency_equity_liquidation=True,
        allow_overdraft=True,
        max_overdraft_cents=50_000_000,
    )
    return p.FourTierTreasuryPolicy(**(defaults | overrides))


def make_forecast(as_of: datetime, horizon_hours: int = 24) -> tuple[p.HourlyForecastPoint, ...]:
    """Create a nominal 24-hour forecast with moderate cash flows."""
    return tuple(
        p.HourlyForecastPoint(
            time_basis="UNSPECIFIED",
            start_at=as_of + timedelta(hours=h),
            predicted_deposits_cents=5_000_000,
            predicted_withdrawals_cents=6_000_000,
            predicted_net_flow_cents=-1_000_000,
            supplied_uncertainty_buffer_cents=0,
        )
        for h in range(horizon_hours)
    )


# ---------------------------------------------------------------------------
# 1. Reproducibility Tests
# ---------------------------------------------------------------------------

def test_monte_carlo_simulation_reproducibility(hourly_series_168):
    portfolio = make_portfolio()
    policy = make_policy()
    forecast = make_forecast(portfolio.as_of)

    # Run twice with the exact same seed
    res1 = simulate_multi_asset_monte_carlo_risk(
        portfolio, hourly_series_168, forecast, policy,
        planning_horizon_hours=24, scenario_count=100, seed=42,
    )
    res2 = simulate_multi_asset_monte_carlo_risk(
        portfolio, hourly_series_168, forecast, policy,
        planning_horizon_hours=24, scenario_count=100, seed=42,
    )

    assert res1.seed == 42
    assert res1.scenario_count == 100
    assert res1.required_reserve.required_reserve_cents == res2.required_reserve.required_reserve_cents
    assert res1.shortfall_distribution.p95_shortfall_before_liquidation_cents == res2.shortfall_distribution.p95_shortfall_before_liquidation_cents
    assert res1.market_risk.total_market_loss_p95_cents == res2.market_risk.total_market_loss_p95_cents
    assert res1.portfolio_downside.p95_downside_loss_cents == res2.portfolio_downside.p95_downside_loss_cents
    assert res1.p95_summary.peak_requirement_cents == res2.p95_summary.peak_requirement_cents

    # Run with different seed -> different sampled scenarios
    res3 = simulate_multi_asset_monte_carlo_risk(
        portfolio, hourly_series_168, forecast, policy,
        planning_horizon_hours=24, scenario_count=100, seed=999,
    )
    assert res3.seed == 999
    # Paths will differ
    assert res1.scenarios[0].forecast[0].predicted_deposits_cents != res3.scenarios[0].forecast[0].predicted_deposits_cents or \
           res1.scenarios[1].forecast[0].predicted_deposits_cents != res3.scenarios[1].forecast[0].predicted_deposits_cents


# ---------------------------------------------------------------------------
# 2. Valid Position Values and Non-Negativity
# ---------------------------------------------------------------------------

def test_valid_position_values_and_non_negativity(hourly_series_168):
    portfolio = make_portfolio()
    policy = make_policy()
    forecast = make_forecast(portfolio.as_of)

    res = simulate_multi_asset_monte_carlo_risk(
        portfolio, hourly_series_168, forecast, policy,
        planning_horizon_hours=24, scenario_count=100, seed=42,
    )

    # In each scenario, all simulated cash flows are non-negative
    for sc in res.scenarios:
        for pt in sc.forecast:
            assert pt.predicted_deposits_cents >= 0
            assert pt.predicted_withdrawals_cents >= 0
            assert pt.predicted_net_flow_cents == pt.predicted_deposits_cents - pt.predicted_withdrawals_cents
        assert sc.market_stress.bond_drawdown_pct >= 0
        assert sc.market_stress.equity_drawdown_pct >= 0

    # Summary metrics are non-negative
    assert res.market_risk.tier2_bond_mean_loss_cents >= 0
    assert res.market_risk.tier3_equity_mean_loss_cents >= 0
    assert res.shortfall_distribution.mean_shortfall_before_liquidation_cents >= 0
    assert res.portfolio_downside.p95_downside_loss_cents >= 0


# ---------------------------------------------------------------------------
# 3. Stress Quantile Ordering
# ---------------------------------------------------------------------------

def test_stress_quantile_ordering(hourly_series_168):
    portfolio = make_portfolio()
    policy = make_policy()
    forecast = make_forecast(portfolio.as_of)

    res = simulate_multi_asset_monte_carlo_risk(
        portfolio, hourly_series_168, forecast, policy,
        planning_horizon_hours=24, scenario_count=200, seed=42,
    )

    # For loss and shortfall metrics: P90 <= P95 <= P99
    sd = res.shortfall_distribution
    assert sd.p90_shortfall_before_liquidation_cents <= sd.p95_shortfall_before_liquidation_cents <= sd.p99_shortfall_before_liquidation_cents
    assert sd.p95_shortfall_before_liquidation_cents <= sd.max_shortfall_before_liquidation_cents

    mr = res.market_risk
    assert mr.tier2_bond_loss_p90_cents <= mr.tier2_bond_loss_p95_cents <= mr.tier2_bond_loss_p99_cents
    assert mr.tier3_equity_loss_p90_cents <= mr.tier3_equity_loss_p95_cents <= mr.tier3_equity_loss_p99_cents

    pd = res.portfolio_downside
    assert pd.p90_downside_loss_cents <= pd.p95_downside_loss_cents <= pd.p99_downside_loss_cents
    assert pd.p95_downside_loss_cents <= pd.max_downside_loss_cents

    # For portfolio value: stress reduces value, so P99 <= P95 <= P90
    assert pd.worst_case_portfolio_value_cents <= pd.p99_portfolio_value_cents <= pd.p95_portfolio_value_cents <= pd.p90_portfolio_value_cents


# ---------------------------------------------------------------------------
# 4. No Lookahead Filtering
# ---------------------------------------------------------------------------

def test_no_lookahead_filtering(hourly_series_168):
    portfolio = make_portfolio(as_of=datetime(2026, 1, 2, 17))  # Friday 17:00 (index 41)
    policy = make_policy()
    forecast = make_forecast(portfolio.as_of)

    # Scenarios should only sample blocks strictly <= as_of
    scenarios = generate_multi_asset_scenarios(
        hourly_series_168, forecast,
        as_of=portfolio.as_of, planning_horizon_hours=15, scenario_count=50, seed=42,
    )
    assert len(scenarios) == 50
    # Every scenario has 15 points
    assert len(scenarios[0].forecast) == 15

    # If history has fewer than 24 + horizon observations prior to as_of, must reject
    with pytest.raises(ValueError, match="insufficient history"):
        generate_multi_asset_scenarios(
            hourly_series_168[:30], forecast,
            as_of=hourly_series_168[25].timestamp, planning_horizon_hours=24, scenario_count=10,
        )


# ---------------------------------------------------------------------------
# 5. No Double-Counting of Uncertainty
# ---------------------------------------------------------------------------

def test_no_double_counting_of_uncertainty(hourly_series_168):
    portfolio = make_portfolio()
    policy = make_policy()
    forecast = make_forecast(portfolio.as_of)

    res = simulate_multi_asset_monte_carlo_risk(
        portfolio, hourly_series_168, forecast, policy,
        planning_horizon_hours=24, scenario_count=100, seed=42,
    )

    # Points in scenarios do not carry artificial provisional uncertainty buffers
    for sc in res.scenarios:
        for pt in sc.forecast:
            assert pt.supplied_uncertainty_buffer_cents == 0

    # In scenario quantile mode, uncertainty buffer is 0 (uncertainty is in the scenario quantile itself)
    assert res.required_reserve.uncertainty_buffer_cents == 0
    assert res.required_reserve.net_drain_cents > 0


# ---------------------------------------------------------------------------
# 6. Correct Repo Cash Availability
# ---------------------------------------------------------------------------

def test_correct_repo_cash_availability(hourly_series_168):
    # Snapshot at 17:00: Repo entered at 17:00 matures at 08:00 next day (+15h)
    as_of = datetime(2026, 1, 3, 17)
    # Opening cash = 0, Repo = $10M
    portfolio = make_portfolio(as_of=as_of, cash=0, repo=10_000_000, allow_early_break=False)
    policy = make_policy(allow_early_repo_redemption=False)

    # Heavy outflow in first 3 hours (before 08:00 repo maturity)
    heavy_flows = [
        p.HourlyForecastPoint(
            time_basis="UNSPECIFIED",
            start_at=as_of + timedelta(hours=h),
            predicted_deposits_cents=0,
            predicted_withdrawals_cents=5_000_000 if h < 5 else 0,
            predicted_net_flow_cents=-5_000_000 if h < 5 else 0,
            supplied_uncertainty_buffer_cents=0,
        )
        for h in range(24)
    ]

    settlement = e.RepoCashSettlement(
        time_basis="UNSPECIFIED",
        position_id=portfolio.repo_positions[0].id,
        available_at=as_of + timedelta(hours=15),  # 08:00 next day
        amount_cents=10_000_000,
        already_in_cash=False,
    )

    res = simulate_multi_asset_monte_carlo_risk(
        portfolio, hourly_series_168, heavy_flows, policy,
        planning_horizon_hours=24, scenario_count=50, seed=42,
        repo_settlements=(settlement,),
    )

    # Repo maturity at +15h does NOT prevent funding shortfall during the first 5 hours
    assert res.shortfall_distribution.p95_shortfall_before_liquidation_cents > 0
    assert res.required_reserve.required_reserve_cents >= 10_000_000


# ---------------------------------------------------------------------------
# 7. Higher Market Losses Reduce Portfolio Value
# ---------------------------------------------------------------------------

def test_higher_market_losses_reduce_portfolio_value(hourly_series_168):
    # Portfolio with large bond and equity positions ($50M bond, $50M equity)
    portfolio = make_portfolio(cash=10_000_000, bond=50_000_000, equity=50_000_000)
    policy = make_policy()
    forecast = make_forecast(portfolio.as_of)

    res = simulate_multi_asset_monte_carlo_risk(
        portfolio, hourly_series_168, forecast, policy,
        planning_horizon_hours=24, scenario_count=100, seed=42,
    )

    # As market stress increases from P90 to P99, portfolio value strictly decreases
    p90 = res.p90_summary
    p95 = res.p95_summary
    p99 = res.p99_summary

    assert p90.total_market_loss_cents <= p95.total_market_loss_cents <= p99.total_market_loss_cents
    assert p99.portfolio_value_cents <= p95.portfolio_value_cents <= p90.portfolio_value_cents
    assert p90.portfolio_downside_cents <= p95.portfolio_downside_cents <= p99.portfolio_downside_cents


# ---------------------------------------------------------------------------
# 8. Consistent JSON Serialization
# ---------------------------------------------------------------------------

def test_consistent_json_serialization(hourly_series_168):
    portfolio = make_portfolio()
    policy = make_policy()
    forecast = make_forecast(portfolio.as_of)

    res = simulate_multi_asset_monte_carlo_risk(
        portfolio, hourly_series_168, forecast, policy,
        planning_horizon_hours=24, scenario_count=50, seed=42,
    )

    json_str = res.model_dump_json()
    assert isinstance(json_str, str)
    data = json.loads(json_str)

    # Verify key metadata and output fields
    assert data["model_version"] == MONTE_CARLO_RISK_MODEL_VERSION
    assert data["scenario_count"] == 50
    assert data["seed"] == 42
    assert "required_reserve" in data
    assert "shortfall_distribution" in data
    assert "market_risk" in data
    assert "portfolio_downside" in data
    assert "p90_summary" in data
    assert "p95_summary" in data
    assert "p99_summary" in data

    # Round-trip deserialization
    deserialized = MultiAssetMonteCarloRiskResult.model_validate_json(json_str)
    assert deserialized.seed == res.seed
    assert deserialized.required_reserve.required_reserve_cents == res.required_reserve.required_reserve_cents
    assert deserialized.p95_summary.peak_requirement_cents == res.p95_summary.peak_requirement_cents


# ---------------------------------------------------------------------------
# 9. Scenario Probabilities Sum Exactly to One
# ---------------------------------------------------------------------------

def test_scenario_probabilities_sum_to_one(hourly_series_168):
    forecast = make_forecast(NOW)
    scenarios = generate_multi_asset_scenarios(
        hourly_series_168, forecast,
        as_of=NOW, planning_horizon_hours=24, scenario_count=500, seed=42,
    )
    assert len(scenarios) == 500
    prob_sum = sum(s.probability for s in scenarios)
    assert prob_sum == Decimal("1")
    assert scenarios[0].probability == Decimal("0.002")


def test_default_500_scenarios_and_runtime(hourly_series_168):
    portfolio = make_portfolio()
    policy = make_policy()
    forecast = make_forecast(portfolio.as_of)

    # Calling with default scenario_count (500)
    res = simulate_multi_asset_monte_carlo_risk(
        portfolio, hourly_series_168, forecast, policy,
    )
    assert res.scenario_count == 500
    assert len(res.scenarios) == 500
    assert res.model_version == MONTE_CARLO_RISK_MODEL_VERSION
    assert res.selected_percentile == Decimal("0.95")
    assert res.recommendation_only is True
    assert res.execution_status == "NOT_EXECUTED"


def test_forced_liquidation_and_overdraft_costs(hourly_series_168):
    # Zero cash, large position holdings, high outflow forecast
    portfolio = make_portfolio(cash=0, repo=10_000_000, bond=10_000_000, equity=10_000_000, allow_early_break=True)
    policy = make_policy(allow_early_repo_redemption=True, allow_bond_liquidation=True, allow_emergency_equity_liquidation=True)

    stress_forecast = [
        p.HourlyForecastPoint(
            time_basis="UNSPECIFIED",
            start_at=NOW + timedelta(hours=h),
            predicted_deposits_cents=0,
            predicted_withdrawals_cents=2_000_000,
            predicted_net_flow_cents=-2_000_000,
            supplied_uncertainty_buffer_cents=0,
        )
        for h in range(24)
    ]

    res = simulate_multi_asset_monte_carlo_risk(
        portfolio, hourly_series_168, stress_forecast, policy,
        planning_horizon_hours=24, scenario_count=50, seed=42,
        available_overdraft_credit_cents=20_000_000,
    )

    # In high stress, forced liquidation proceeds and overdraft are engaged
    assert res.shortfall_distribution.p95_shortfall_before_liquidation_cents > 0
    # Liquidation costs are accounted for
    assert res.p95_summary.liquidation_costs_cents >= 0
    # Overdraft financing cost is non-negative
    assert res.p95_summary.overdraft_cost_cents >= 0


@pytest.mark.parametrize('scenario_count', [3, 7])
def test_non_power_of_ten_scenario_weights_are_exact(hourly_series_168, scenario_count):
    from decimal import localcontext
    scenarios = generate_multi_asset_scenarios(hourly_series_168, make_forecast(NOW),
        as_of=NOW, scenario_count=scenario_count)
    with localcontext() as ctx:
        ctx.prec = 100
        assert sum(s.probability for s in scenarios) == Decimal(1)


def test_monte_carlo_rejects_missing_historical_hours(hourly_series_168):
    with pytest.raises(ValueError, match='contiguous'):
        generate_multi_asset_scenarios(hourly_series_168[:30] + hourly_series_168[31:],
            make_forecast(NOW), as_of=NOW)


def test_stress_nav_conserves_assets_and_uses_ending_flows(hourly_series_168, monkeypatch):
    import treasury_intelligence.monte_carlo_risk as mc
    from treasury_intelligence.liquidity_risk import LiquidityScenario, MarketStress
    portfolio = make_portfolio(cash=50_000_000, repo=0, bond=20_000_000, equity=10_000_000)
    # A large temporary withdrawal is fully replenished by the final deposit.
    path = tuple(p.HourlyForecastPoint(time_basis='UNSPECIFIED', start_at=NOW + timedelta(hours=h),
        predicted_deposits_cents=40_000_000 if h == 23 else 0,
        predicted_withdrawals_cents=40_000_000 if h == 0 else 0,
        predicted_net_flow_cents=40_000_000 if h == 23 else -40_000_000 if h == 0 else 0,
        supplied_uncertainty_buffer_cents=0)
        for h in range(24))
    scenario = LiquidityScenario(scenario_id='conservation', probability=Decimal(1), forecast=path,
        market_stress=MarketStress(bond_drawdown_pct=Decimal(2), equity_drawdown_pct=Decimal(10)))
    monkeypatch.setattr(mc, 'generate_multi_asset_scenarios', lambda *a, **k: (scenario,))
    result = mc.simulate_multi_asset_monte_carlo_risk(portfolio, hourly_series_168, path,
        make_policy(allow_overdraft=False, max_overdraft_cents=0), scenario_count=1)
    # Selling every permitted asset converts value to cash exactly once.
    loss = 400_000 + 1_000_000
    fees = 392_000 + 1_350_000
    assert result.portfolio_downside.expected_net_portfolio_value_cents == 80_000_000 - loss - fees
    assert result.portfolio_downside.max_downside_loss_cents == loss + fees


def test_matured_repo_claim_removed_once_from_stress_nav(hourly_series_168, monkeypatch):
    import treasury_intelligence.monte_carlo_risk as mc
    from treasury_intelligence.liquidity_risk import LiquidityScenario, RepoCashSettlement
    portfolio = make_portfolio(cash=50_000_000, repo=20_000_000, bond=0, equity=0)
    path = tuple(p.HourlyForecastPoint(time_basis='UNSPECIFIED', start_at=NOW + timedelta(hours=h),
        predicted_deposits_cents=0, predicted_withdrawals_cents=0, predicted_net_flow_cents=0,
        supplied_uncertainty_buffer_cents=0)
        for h in range(24))
    scenario = LiquidityScenario(scenario_id='maturity', probability=Decimal(1), forecast=path)
    monkeypatch.setattr(mc, 'generate_multi_asset_scenarios', lambda *a, **k: (scenario,))
    repo = portfolio.repo_positions[0]
    result = mc.simulate_multi_asset_monte_carlo_risk(portfolio, hourly_series_168, path,
        make_policy(allow_early_repo_redemption=False), scenario_count=1,
        repo_settlements=(RepoCashSettlement(time_basis='UNSPECIFIED', position_id=repo.id,
            available_at=repo.scheduled_maturity_at, amount_cents=repo.principal_cents),))
    assert result.portfolio_downside.expected_net_portfolio_value_cents == 70_000_000


def test_one_hour_market_scenario_includes_first_price_innovation(hourly_series_168):
    history = tuple(o.model_copy(update={
        'tier2_bond_price_index': Decimal(100 - i),
        'tier3_stock_index_price': Decimal(100 - i)})
        for i, o in enumerate(hourly_series_168[:30]))
    scenarios = generate_multi_asset_scenarios(history, make_forecast(history[-1].timestamp, 1),
        as_of=history[-1].timestamp, planning_horizon_hours=1, scenario_count=3)
    assert all(s.market_stress.bond_drawdown_pct > 0 and s.market_stress.equity_drawdown_pct > 0
               for s in scenarios)


def test_existing_overdraft_financing_reduces_nav_once(hourly_series_168, monkeypatch):
    import treasury_intelligence.monte_carlo_risk as mc
    from treasury_intelligence.liquidity_risk import LiquidityScenario
    portfolio = make_portfolio(cash=50_000_000, repo=0, bond=0, equity=0, debt=10_000_000)
    path = tuple(p.HourlyForecastPoint(time_basis='UNSPECIFIED', start_at=NOW + timedelta(hours=h),
        predicted_deposits_cents=0, predicted_withdrawals_cents=0, predicted_net_flow_cents=0,
        supplied_uncertainty_buffer_cents=0) for h in range(24))
    scenario = LiquidityScenario(scenario_id='debt', probability=Decimal(1), forecast=path)
    monkeypatch.setattr(mc, 'generate_multi_asset_scenarios', lambda *a, **k: (scenario,))
    result = mc.simulate_multi_asset_monte_carlo_risk(portfolio, hourly_series_168, path,
        make_policy(), scenario_count=1)
    from decimal import ROUND_CEILING
    cost = int((Decimal(10_000_000) * portfolio.overdrafts[0].apr_pct / 100 / 365)
               .to_integral_value(rounding=ROUND_CEILING))
    assert result.p95_summary.overdraft_draw_cents == 0
    assert result.p95_summary.overdraft_cost_cents == cost
    assert result.portfolio_downside.expected_net_portfolio_value_cents == portfolio.valuation.net_portfolio_value_cents - cost
