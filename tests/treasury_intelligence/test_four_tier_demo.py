"""Tests for Official Four-Tier Treasury Engine Demonstration (RJ-M1-13).

Verifies:
1. End-to-end execution of the 4-tier quantitative pipeline from organizer hourly data.
2. Scenario 1: Allowed overnight repo sweep (17:00 window, surplus cash, 15h maturity).
3. Scenario 2: Repo unavailable (outside 17:00, repo investment strictly rejected).
4. Scenario 3: Stressed liquidity shortage (funding deficit, LIQUIDITY_WARNING).
5. Scenario 4: Market decline revaluation (mark-to-market drop, haircut liquidation loss).
6. Complete JSON serialization roundtrip and deterministic reproducibility.
"""
from datetime import time, timedelta
from decimal import Decimal
import json
from pathlib import Path

import pytest

import treasury_intelligence as ti
from treasury_intelligence import (
    FourTierDemoScenarioResult,
    FourTierDemoSuiteResult,
    load_demo_observations,
    resolve_organizer_dataset_path,
    run_four_tier_demo,
    run_scenario_liquidity_shortage,
    run_scenario_market_decline,
    run_scenario_repo_sweep,
    run_scenario_repo_unavailable,
)


@pytest.fixture(scope="module")
def observations():
    """Load native hourly observations for testing."""
    return load_demo_observations(limit=100)


def test_resolve_organizer_dataset_path():
    path = resolve_organizer_dataset_path()
    assert path.is_file()
    assert path.suffix.lower() in (".csv", ".json")


def test_load_demo_observations(observations):
    assert len(observations) >= 59
    first = observations[0]
    assert first.deposits_usd >= 0
    assert first.withdrawals_usd >= 0
    assert first.timestamp.tzinfo is None  # Must remain naive


def test_scenario_1_allowed_repo_sweep(observations):
    res = run_scenario_repo_sweep(observations, obs_index=41, seed=42)
    assert isinstance(res, FourTierDemoScenarioResult)
    assert res.summary_action == "INVEST"
    assert res.canonical_action == "ALLOCATE"
    assert res.feasible is True

    # Reserve and target validation
    assert res.tier0_cash_target_cents >= res.required_reserve_cents
    assert res.tier1_repo_target_cents > 0
    assert res.tier0_cash_target_cents + res.tier1_repo_target_cents == res.portfolio_valuation_cents

    # Recommended order checks
    assert len(res.recommended_orders) == 1
    order = res.recommended_orders[0]
    assert order.action == "INVEST_REPO"
    assert order.amount_cents == res.tier1_repo_target_cents
    assert order.earliest_execution_at.time() == time(17)
    assert order.expected_maturity_at == order.earliest_execution_at + timedelta(hours=15)
    assert order.recommendation_only is True
    assert order.execution_status == "NOT_EXECUTED"

    # Economics checks
    assert res.estimated_income_cents > 0
    assert res.calculation_breakdown["quoted_repo_rate_apy"] == "4.272"


def test_scenario_2_repo_unavailable_outside_17h(observations):
    res = run_scenario_repo_unavailable(observations, obs_index=58, seed=42)
    assert isinstance(res, FourTierDemoScenarioResult)
    assert res.summary_action == "HOLD"
    assert res.decision_timestamp.time() == time(10)

    # Repo must not be allocated
    assert res.tier1_repo_target_cents == 0
    repo_orders = [o for o in res.recommended_orders if o.action == "INVEST_REPO"]
    assert len(repo_orders) == 0

    assert res.calculation_breakdown["repo_sweep_window_open"] is False
    assert "repo" in res.human_readable_summary.lower()


def test_scenario_3_stressed_liquidity_shortage(observations):
    res = run_scenario_liquidity_shortage(observations, obs_index=41, seed=42)
    assert isinstance(res, FourTierDemoScenarioResult)
    assert res.summary_action == "WARNING"
    assert res.canonical_action == "LIQUIDITY_WARNING"
    assert res.feasible is False
    assert len(res.recommended_orders) == 0

    # Deficit checks
    gap = res.calculation_breakdown["funding_gap_usd"]
    assert gap > 0
    assert res.calculation_breakdown["required_reserve_usd"] > res.calculation_breakdown["starting_cash_usd"]


def test_scenario_4_market_decline_revaluation(observations):
    res = run_scenario_market_decline(observations, obs_index=41)
    assert isinstance(res, FourTierDemoScenarioResult)
    assert res.market_decline_analysis is not None

    analysis = res.market_decline_analysis
    assert analysis["bond_market_loss_usd"] > 0
    assert analysis["equity_market_loss_usd"] > 0
    assert analysis["total_portfolio_loss_usd"] > 0

    # Net portfolio value reflects the loss
    assert res.net_portfolio_value_cents < 69_934_960_00
    assert analysis["haircut_liquidation_loss_usd"] > 0


def test_full_demo_suite_execution():
    suite = run_four_tier_demo(limit=70, seed=42)
    assert isinstance(suite, FourTierDemoSuiteResult)
    assert suite.all_passed is True
    assert len(suite.scenarios) == 4
    assert "DEMO SUITE COMPLETE" in suite.summary_report


def test_demo_json_serialization_roundtrip():
    suite = run_four_tier_demo(limit=70, seed=42)
    json_str = suite.model_dump_json(indent=2)
    deserialized = FourTierDemoSuiteResult.model_validate_json(json_str)
    assert deserialized == suite

    # Check each scenario roundtrip individually
    for s in suite.scenarios:
        s_json = s.model_dump_json()
        assert FourTierDemoScenarioResult.model_validate_json(s_json) == s


def test_demo_deterministic_reproducibility(observations):
    res_a = run_scenario_repo_sweep(observations, obs_index=41, seed=42)
    res_b = run_scenario_repo_sweep(observations, obs_index=41, seed=42)
    assert res_a == res_b
    assert res_a.tier1_repo_target_cents == res_b.tier1_repo_target_cents
    assert res_a.estimated_income_cents == res_b.estimated_income_cents


def test_demo_bond_quote_is_not_horizon_cash_income(observations):
    from treasury_intelligence.four_tier_demo import create_demo_reward_model
    rewards = create_demo_reward_model(observations[41], holding_hours=15, risk_aversion=Decimal(1))
    assert next(a for a in rewards.assets if a.tier == 2).expected_income_pct == 0


def test_demo_builder_includes_unpaid_financing_liability(observations):
    from treasury_intelligence.portfolio import OverdraftLiability
    from treasury_intelligence.four_tier_demo import build_demo_portfolio_state
    raw = json.loads((Path(__file__).parent / 'fixtures' / 'canonical_liquidity_portfolio.json').read_text())['overdrafts'][0]
    raw.update(source_observation_timestamp=observations[41].timestamp.isoformat(),
               paid_financing_cost_cents=10, outstanding_financing_cost_cents=10)
    state = build_demo_portfolio_state(observations[41], cash_cents=50_000,
                                     overdrafts=(OverdraftLiability.model_validate(raw),))
    assert state.valuation.liabilities_cents == 10_010
    assert state.valuation.net_portfolio_value_cents == 39_990
