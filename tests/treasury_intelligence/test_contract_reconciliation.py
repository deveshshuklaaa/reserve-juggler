"""Ported teammate guarantees plus explicit resolution of both contract families."""
from copy import deepcopy
from decimal import Decimal, localcontext
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from uuid import UUID

from pydantic import ValidationError
import pytest

import treasury_intelligence as e
from treasury_intelligence import portfolio as canonical

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name):
    return json.loads((FIXTURES / f"{name}.json").read_text())


def request_example():
    state = fixture("four_tier_portfolio")
    history = fixture("organizer_history")
    last = history[-1]
    state["bond_positions"][0].update(current_market_price_index=last["tier2_bond_price_index"],
        supplied_yield_pct=last["tier2_bond_yield_pct"], modified_duration=last["tier2_bond_mod_duration"])
    state["equity_positions"][0].update(current_market_price_index=last["tier3_stock_index_price"],
        supplied_volatility_pct=last["tier3_stock_volatility_pct"])
    state["market_rates"] = dict(time_basis="UNSPECIFIED", observed_at=last["timestamp"],
        repo_apy_pct=last["tier1_repo_rate_apy"], bond_yield_pct=last["tier2_bond_yield_pct"],
        equity_volatility_pct=last["tier3_stock_volatility_pct"], overdraft_apr_pct=last["emergency_overdraft_penalty_apr_pct"])
    state["market_prices"] = dict(time_basis="UNSPECIFIED", observed_at=last["timestamp"],
        bond_price_index=last["tier2_bond_price_index"], bond_modified_duration_years=last["tier2_bond_mod_duration"],
        equity_index_price=last["tier3_stock_index_price"])
    policy = dict(base_buffer_cents=10, uncertainty_multiplier_bps=10000, tolerance_bps=0,
        min_transfer_cents=100, max_allocation_bps=10000, repo_sweep_window_open=True,
        allow_overdraft=True, max_overdraft_cents=10000, max_estimated_loss_cents=100,
        tier_limits=[dict(tier=i, min_allocation_bps=0, max_allocation_bps=10000) for i in range(4)])
    metadata = dict(time_basis="UNSPECIFIED", model_version="supplied-contract-example", generated_at=state["as_of"],
        training_data_through=history[-1]["timestamp"], granularity_hours=1,
        net_flow_target="source_net_flow_usd", uncertainty_status="provisional_uncalibrated")
    forecast = [dict(time_basis="UNSPECIFIED", start_at="2026-01-01T18:00:00", predicted_deposits_cents=100,
        predicted_withdrawals_cents=200, predicted_net_flow_cents=-101, supplied_uncertainty_buffer_cents=20),
        dict(time_basis="UNSPECIFIED", start_at="2026-01-01T19:00:00", predicted_deposits_cents=200,
        predicted_withdrawals_cents=100, predicted_net_flow_cents=100, supplied_uncertainty_buffer_cents=20)]
    return dict(request_id="contract-example", portfolio=state, history=history, policy=policy, metadata=metadata,
                forecast=forecast, history_available_at=state["as_of"])


def decision_example():
    req = request_example()
    state = req["portfolio"]
    source = {k: state[k] for k in e.PortfolioSource.model_fields}
    costs = dict(liquidation_fee_cents=0, repo_break_fee_cents=0, transaction_cost_cents=0, funding_cost_cents=0)
    order = dict(source, id=str(UUID(int=20)), as_of=state["as_of"], action="BUY_BONDS", tier=2,
                 amount_cents=100, estimated_cost_cents=0, expected_costs=costs, reason="Illustrative supplied order, not an optimizer result")
    targets = dict(tier0_target_cents=199900, tier1_allocation_cents=100010,
                   tier2_allocation_cents=20090, tier3_allocation_cents=510000)
    return dict(source, as_of=state["as_of"], request_id=req["request_id"], action="ALLOCATE", feasible=True,
        reserve=dict(time_basis="UNSPECIFIED", as_of=state["as_of"], net_drain_cents=100, uncertainty_buffer_cents=20,
                     base_buffer_cents=10, required_reserve_cents=130), orders=[order], reason="Constructed contract example",
        allocation_budget_cents=830000, targets=targets, target_overdraft_principal_cents=10000,
        expected_costs=costs, estimated_market_risk_loss_cents=50, policy=req["policy"], metadata=req["metadata"],
        instrument_returns=[dict(instrument="TIER3_EQUITY", horizon_hours=1, expected_income_cents=0,
            expected_price_change_cents=-5, expected_costs=costs, estimated_stress_loss_cents=10,
            estimate_basis="supplied illustrative assumption; not evaluated", realized=False)])


def test_one_canonical_family_and_no_shadow_overdraft():
    assert not (Path(e.__file__).parent / "four_tier.py").exists()
    assert importlib.util.find_spec("treasury_intelligence.four_tier") is None
    for name in ("PortfolioState", "OverdraftLiability", "RecommendedOrder", "FourTierDecisionResult",
                 "FourTierRecommendationRequest", "OrganizerHourlyObservation"):
        assert getattr(e, name) is getattr(canonical, name)
    assert e.PortfolioTreasuryContext is e.PortfolioState
    assert not hasattr(e, "FourTierPortfolioState")
    assert not hasattr(e, "PortfolioRecommendation")


def test_source_schema_exactly_sixteen_fields_and_original_source_values():
    row = fixture("organizer_hourly_observation")
    assert set(e.OrganizerHourlyObservation.model_fields) == set(row)
    assert len(row) == 16
    value = e.OrganizerHourlyObservation.model_validate(row)
    assert json.loads(value.model_dump_json()) == row
    assert value.timestamp.tzinfo is None
    # Real row 17's supplied net flow differs by a cent from the displayed components.
    hourly = e.OrganizerHourlyObservation.model_validate(fixture("organizer_history")[-1])
    assert hourly.net_flow_usd == Decimal("-1510252.76")
    assert hourly.net_flow_usd != hourly.deposits_usd - hourly.withdrawals_usd
    row.update(repo_sweep_window_open="True", repo_sweep_mature="False")
    assert e.OrganizerHourlyObservation.model_validate(row).repo_sweep_window_open is True


@pytest.mark.parametrize("name,model,build", [
    ("four_tier_request", e.FourTierRecommendationRequest, request_example),
    ("four_tier_response", e.FourTierDecisionResult, decision_example),
])
def test_final_example_files_use_only_the_canonical_schema(name, model, build):
    data = fixture(name)
    parsed = model.model_validate(data)
    assert json.loads(parsed.model_dump_json()) == data
    assert parsed == model.model_validate(build())


@pytest.mark.parametrize("field,bad", [("timestamp", "2026-01-01T00:00:00Z"), ("timestamp", 0),
    ("timestamp", "2026-01-01T00:15:00"), ("timestamp", "2026-01-01T00:00:01"),
    ("tier2_bond_mod_duration", "0"), ("repo_sweep_mature", 1), ("tier1_repo_rate_apy", 4.292),
    ("tier1_repo_rate_apy", "Infinity"), ("net_flow_usd", "NaN")])
def test_source_invalid_cases(field, bad):
    with pytest.raises(ValidationError):
        e.OrganizerHourlyObservation.model_validate(dict(fixture("organizer_hourly_observation"), **{field: bad}))


def test_precision_preserved_and_no_mark_to_market_or_rounding_formula_assumed():
    data = fixture("four_tier_portfolio")["bond_positions"][0]
    data.update(quantity="0.123456789012345678901234567890123456789", acquisition_cost_cents=20000,
                current_market_price_index="99.95000000000000000000000000000000001", current_market_value_cents=19990)
    with localcontext() as context:
        context.prec = 3
        value = e.BondPosition.model_validate(data)
        restored = e.BondPosition.model_validate_json(value.model_dump_json())
    assert restored.quantity.as_tuple() == Decimal(data["quantity"]).as_tuple()
    assert restored.current_market_price_index.as_tuple() == Decimal(data["current_market_price_index"]).as_tuple()
    assert restored.current_market_value_cents == 19990
    assert restored.acquisition_cost_cents == 20000
    assert "ROUND_HALF_UP" not in Path(canonical.__file__).read_text()
    assert not hasattr(restored, "index_units")


@pytest.mark.parametrize("field,bad", [("entered_at", "2026-01-01T16:00:00"),
    ("scheduled_maturity_at", "2026-01-02T17:00:00"), ("early_redemption_allowed", 1)])
def test_official_historical_repo_session_and_permissions(field, bad):
    with pytest.raises(ValidationError):
        e.RepoPosition.model_validate(dict(fixture("four_tier_portfolio")["repo_positions"][0], **{field: bad}))


def test_expected_repo_interest_never_becomes_accrued_or_realized_cash():
    data = fixture("four_tier_portfolio")["repo_positions"][0]
    data.update(expected_interest_cents=123, accrued_interest_cents=None, realized_interest_cents=None)
    value = e.RepoPosition.model_validate(data)
    assert value.expected_interest_cents == 123
    assert value.accrued_interest_cents is value.realized_interest_cents is None


def test_financing_paid_cost_not_deducted_twice_and_unpaid_cost_is_liability():
    data = fixture("four_tier_portfolio")
    value = e.PortfolioState.model_validate(data)
    assert value.valuation.liabilities_cents == 10000  # cost 20 was explicitly paid already
    data["overdrafts"][0].update(paid_financing_cost_cents=0, outstanding_financing_cost_cents=20)
    data["valuation"].update(liabilities_cents=10020, net_portfolio_value_cents=819980)
    assert e.PortfolioState.model_validate(data).valuation.liabilities_cents == 10020
    data["valuation"].update(liabilities_cents=10000, net_portfolio_value_cents=820000)
    with pytest.raises(ValidationError):
        e.PortfolioState.model_validate(data)


@pytest.mark.parametrize("change", ["missing", "split", "negative", "double_count", "currency"])
def test_complete_balance_sheet_rejects_ambiguous_financing(change):
    data = fixture("four_tier_portfolio")
    loan = data["overdrafts"][0]
    if change == "missing": loan["outstanding_financing_cost_cents"] = None
    elif change == "split": loan["paid_financing_cost_cents"] = 19
    elif change == "negative": loan["outstanding_financing_cost_cents"] = -1
    elif change == "double_count": data["valuation"].update(liabilities_cents=10020, net_portfolio_value_cents=819980)
    else: data["currency"] = "EUR"
    with pytest.raises(ValidationError):
        e.PortfolioState.model_validate(data)


@pytest.mark.parametrize("model,build", [(e.FourTierRecommendationRequest, request_example), (e.FourTierDecisionResult, decision_example)])
def test_canonical_envelopes_json_frozen_schema_and_extra_fields(model, build):
    data = build()
    value = model.model_validate(data)
    assert model.model_validate_json(value.model_dump_json()) == value
    assert model.model_json_schema()["additionalProperties"] is False
    assert model.model_validate(data).model_dump_json() == value.model_dump_json()
    with pytest.raises(ValidationError):
        model.model_validate(dict(data, unknown_field=1))
    with pytest.raises(ValidationError):
        value.request_id = "mutated"


@pytest.mark.parametrize("change", ["history_future", "gap", "reverse", "forecast_quarter_hour", "forecast_gap",
    "target_recomputed", "evaluation_claim", "training_future", "clock", "quote_price", "quote_time", "quote_future",
    "missing_quote", "source_quote", "unavailable_history"])
def test_source_market_and_forecast_provenance(change):
    data = request_example()
    if change == "history_future": data["history"][-1]["timestamp"] = "2026-01-01T18:00:00"
    elif change == "gap": data["history"][0]["timestamp"] = "2026-01-01T14:00:00"
    elif change == "reverse": data["history"].reverse()
    elif change == "forecast_quarter_hour": data["forecast"][0]["start_at"] = "2026-01-01T18:15:00"
    elif change == "forecast_gap": data["forecast"][1]["start_at"] = "2026-01-01T20:00:00"
    elif change == "target_recomputed": data["metadata"]["net_flow_target"] = "deposits_minus_withdrawals"
    elif change == "evaluation_claim": data["metadata"]["uncertainty_status"] = "evaluated"
    elif change == "training_future": data["metadata"]["training_data_through"] = "2026-01-01T18:00:00"
    elif change == "clock": data["metadata"]["time_basis"] = "UTC"
    elif change == "quote_price": data["portfolio"]["market_prices"]["bond_price_index"] = "1"
    elif change == "quote_time": data["portfolio"]["market_prices"]["observed_at"] = "2026-01-01T16:00:00"
    elif change == "quote_future": data["portfolio"]["market_rates"]["observed_at"] = "2026-01-01T18:00:00"
    elif change == "missing_quote": data["portfolio"]["market_prices"] = None
    elif change == "source_quote": data["portfolio"]["market_rates"]["repo_apy_pct"] = "1"
    else: data["history_available_at"] = "2026-01-01T18:00:00"
    with pytest.raises(ValidationError):
        e.FourTierRecommendationRequest.model_validate(data)


@pytest.mark.parametrize("change", ["budget", "net_worth_budget", "cash_reserve", "bounds", "debt", "risk",
    "warning_feasible", "allocate_infeasible", "executed", "cost_total", "market_loss_fee", "repay_no_id", "realized_estimate", "missing_policy"])
def test_reconciled_plan_and_cost_invariants(change):
    data = decision_example()
    if change == "budget": data["allocation_budget_cents"] += 1
    elif change == "net_worth_budget": data["allocation_budget_cents"] = 820000
    elif change == "cash_reserve": data["reserve"].update(base_buffer_cents=900000, required_reserve_cents=900120)
    elif change == "bounds": data["policy"]["tier_limits"][2]["max_allocation_bps"] = 1
    elif change == "debt": data["target_overdraft_principal_cents"] = 10001
    elif change == "risk": data["estimated_market_risk_loss_cents"] = 101
    elif change == "warning_feasible": data.update(action="LIQUIDITY_WARNING", orders=[])
    elif change == "allocate_infeasible": data["feasible"] = False
    elif change == "executed": data["orders"][0]["execution_status"] = "EXECUTED"
    elif change == "cost_total": data["orders"][0]["estimated_cost_cents"] = 1
    elif change == "market_loss_fee": data["expected_costs"]["market_loss_cents"] = 1
    elif change == "repay_no_id": data["orders"][0].update(action="REPAY_OVERDRAFT", tier=0)
    elif change == "realized_estimate": data["instrument_returns"][0]["realized"] = True
    else: data["policy"] = None
    with pytest.raises(ValidationError):
        e.FourTierDecisionResult.model_validate(data)


def test_fee_breakdown_and_signed_price_change_remain_separate():
    value = e.InstrumentReturnEstimate.model_validate(decision_example()["instrument_returns"][0])
    assert value.expected_price_change_cents == -5 and value.expected_costs.total_cents == 0
    costs = e.CostBreakdown(liquidation_fee_cents=1, repo_break_fee_cents=2, transaction_cost_cents=3, funding_cost_cents=4)
    assert costs.total_cents == 10


@pytest.mark.parametrize("change", ["pair", "past", "settlement", "entry_hour", "maturity", "wrong_action", "missing_schedule"])
def test_order_execution_and_settlement_schedule(change):
    data = decision_example()["orders"][0]
    data.update(action="INVEST_REPO", tier=1, earliest_execution_at="2026-01-01T17:00:00",
                expected_settlement_at="2026-01-01T17:00:00", expected_maturity_at="2026-01-02T08:00:00")
    if change == "pair": data["expected_settlement_at"] = None
    elif change == "past": data["earliest_execution_at"] = "2026-01-01T16:00:00"
    elif change == "settlement": data["expected_settlement_at"] = "2026-01-01T16:00:00"
    elif change == "entry_hour": data.update(earliest_execution_at="2026-01-01T18:00:00", expected_settlement_at="2026-01-01T18:00:00")
    elif change == "maturity": data["expected_maturity_at"] = "2026-01-02T17:00:00"
    elif change == "wrong_action": data.update(action="BUY_BONDS", tier=2)
    else: data.update(earliest_execution_at=None, expected_settlement_at=None, expected_maturity_at=None)
    with pytest.raises(ValidationError):
        e.RecommendedOrder.model_validate(data)


@pytest.mark.parametrize("change", ["ordered", "full_allocation", "fractional_bps", "overdraft_disabled"])
def test_policy_uses_one_integer_bps_convention(change):
    data = request_example()["policy"]
    if change == "ordered": data["tier_limits"][0].update(min_allocation_bps=9000, max_allocation_bps=8000)
    elif change == "full_allocation":
        for limit in data["tier_limits"]: limit["max_allocation_bps"] = 1
    elif change == "fractional_bps": data["tier_limits"][0]["max_allocation_bps"] = "1234.567"
    else: data["allow_overdraft"] = False
    with pytest.raises(ValidationError):
        e.FourTierTreasuryPolicy.model_validate(data)


def test_public_boundary_is_contract_only_and_has_no_external_implementation_imports():
    from treasury_intelligence import api
    assert api.recommend_portfolio_allocation is canonical.recommend_portfolio_allocation
    req = e.FourTierRecommendationRequest.model_validate(request_example())
    before = req.model_dump_json()
    with pytest.raises(NotImplementedError, match="contracts only"):
        e.recommend_portfolio_allocation(req)
    assert req.model_dump_json() == before
    code = """
import importlib.abc, sys
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'sqlalchemy', 'fastapi', 'sklearn', 'torch', 'tensorflow'}:
            raise ImportError(fullname)
sys.meta_path.insert(0, Block())
from treasury_intelligence import PortfolioState, FourTierDecisionResult, FourTierRecommendationRequest
"""
    subprocess.run([sys.executable, "-B", "-c", code], check=True, capture_output=True, text=True)


@pytest.mark.parametrize("change", ["fractional_source", "float_tenor", "past_maturity", "boolean_granularity"])
def test_unambiguous_native_time_and_instrument_labels(change):
    with pytest.raises(ValidationError):
        if change == "fractional_source":
            data = fixture("four_tier_portfolio")["cash"]
            data["source_observation_timestamp"] = "2026-01-01T17:15:00"
            e.CashPosition.model_validate(data)
        elif change in ("float_tenor", "past_maturity"):
            data = fixture("four_tier_portfolio")["bond_positions"][0]
            if change == "float_tenor": data["tenor_years"] = 2.0
            else: data["contractual_maturity_at"] = "2025-01-01T00:00:00"
            e.BondPosition.model_validate(data)
        else:
            data = request_example()["metadata"]
            data["granularity_hours"] = True
            e.ForecastRiskMetadata.model_validate(data)
