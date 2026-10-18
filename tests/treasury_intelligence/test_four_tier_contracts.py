"""Contract-only tests: no trading, historical resampling, or optimizer results."""
import importlib
import inspect
import json
import subprocess
import sys
from decimal import Decimal, localcontext
from datetime import timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

import treasury_intelligence as e
from treasury_intelligence import api

ROOT = Path(__file__).parent / "fixtures"


def fixture(name):
    return json.loads((ROOT / f"{name}.json").read_text())


@pytest.mark.parametrize("name,model", [
    ("four_tier_request", e.FourTierRecommendationRequest),
    ("four_tier_response", e.PortfolioRecommendation),
    ("organizer_hourly_observation", e.OrganizerHourlyObservation),
])
def test_fixture_round_trip_schema_and_immutability(name, model):
    data = fixture(name)
    parsed = model.model_validate(data)
    assert json.loads(parsed.model_dump_json()) == data
    assert model.model_validate_json(parsed.model_dump_json()) == parsed
    assert model.model_json_schema()["additionalProperties"] is False
    field = next(iter(model.model_fields))
    with pytest.raises(ValidationError):
        setattr(parsed, field, getattr(parsed, field))
    with pytest.raises(ValidationError):
        model.model_validate(dict(data, unknown=1))


def test_exact_sixteen_source_fields_and_independent_net_flow():
    data = fixture("organizer_hourly_observation")
    observation = e.OrganizerHourlyObservation.model_validate(data)
    assert len(e.OrganizerHourlyObservation.model_fields) == len(data) == 16
    assert observation.net_flow_usd == Decimal("-192795.91")
    # A differing source net flow must be retained, not silently recalculated.
    independent = e.OrganizerHourlyObservation.model_validate(dict(data, net_flow_usd="-192795.910001"))
    assert independent.net_flow_usd != independent.deposits_usd - independent.withdrawals_usd
    assert observation.timestamp.tzinfo is None
    assert observation.tier1_repo_rate_apy == Decimal("4.292")
    assert observation.tier1_early_redemption_haircut_pct == Decimal("0.5")


def test_preserves_decimal_precision_and_scale_in_json():
    data = fixture("organizer_hourly_observation")
    value = "4.292000000000000000000000000123456789"
    data["tier1_repo_rate_apy"] = value
    data["tier2_bond_price_index"] = "100.00000000000000000000000000000000001"
    with localcontext() as ctx:
        ctx.prec = 3
        observation = e.OrganizerHourlyObservation.model_validate(data)
        serialized = json.loads(observation.model_dump_json())
    assert serialized["tier1_repo_rate_apy"] == value
    assert serialized["tier2_bond_price_index"] == data["tier2_bond_price_index"]


@pytest.mark.parametrize("invalid", [4.292, True, "NaN", "Infinity", "-Infinity"])
def test_source_rates_reject_lossy_or_nonfinite_inputs(invalid):
    data = fixture("organizer_hourly_observation")
    data["tier1_repo_rate_apy"] = invalid
    with pytest.raises(ValidationError):
        e.OrganizerHourlyObservation.model_validate(data)


@pytest.mark.parametrize("timestamp", ["2026-01-01T00:00:00Z", "2026-01-01T00:00:00+05:30", 0,
                                      "2026-01-01T00:15:00", "2026-01-01T00:00:01"])
def test_source_timestamp_semantics(timestamp):
    data = fixture("organizer_hourly_observation")
    data["timestamp"] = timestamp
    with pytest.raises(ValidationError):
        e.OrganizerHourlyObservation.model_validate(data)


def test_csv_booleans_without_accepting_numbers():
    data = fixture("organizer_hourly_observation")
    data.update(repo_sweep_window_open="True", repo_sweep_mature="False")
    parsed = e.OrganizerHourlyObservation.model_validate(data)
    assert parsed.repo_sweep_window_open is True and parsed.repo_sweep_mature is False
    data["repo_sweep_mature"] = 1
    with pytest.raises(ValidationError):
        e.OrganizerHourlyObservation.model_validate(data)


def test_all_four_positions_and_overdraft_liability_are_separate():
    request = e.FourTierRecommendationRequest.model_validate(fixture("four_tier_request"))
    portfolio = request.portfolio
    assert [portfolio.cash.instrument, portfolio.repos[0].instrument, portfolio.bonds[0].instrument,
            portfolio.equities[0].instrument] == [i.value for i in e.InstrumentId if i != e.InstrumentId.OVERDRAFT]
    assert portfolio.overdraft.instrument == "OVERDRAFT"
    assert portfolio.overdraft.principal_cents == 0
    assert portfolio.repos[0].matures_at - portfolio.repos[0].entered_at == timedelta(hours=15)
    assert portfolio.bonds[0].liquidation_haircut_pct == Decimal("2")
    assert portfolio.equities[0].emergency_sale_slippage_pct == Decimal("15")


@pytest.mark.parametrize("value", [-1, True, 1.1, "100"])
def test_cash_ledger_requires_integer_cents(value):
    with pytest.raises(ValidationError):
        e.Tier0CashPosition(available_cents=value)


@pytest.mark.parametrize("field,value", [("entered_at", "2026-01-01T16:00:00"),
    ("matures_at", "2026-01-02T17:00:00"), ("early_break_fee_pct", "100.01"),
    ("early_break_allowed", 1)])
def test_repo_validation(field, value):
    data = fixture("four_tier_request")["portfolio"]["repos"][0]
    data[field] = value
    with pytest.raises(ValidationError):
        e.Tier1RepoPosition.model_validate(data)


@pytest.mark.parametrize("key,model", [("bonds", e.Tier2BondPosition), ("equities", e.Tier3EquityPosition)])
def test_mark_to_market_uses_observed_index_without_second_duration_charge(key, model):
    data = fixture("four_tier_request")["portfolio"][key][0]
    parsed = model.model_validate(data)
    expected = (parsed.index_units * parsed.observed_price_index * 100).quantize(Decimal("1"), rounding="ROUND_HALF_UP")
    assert parsed.market_value_cents == int(expected)
    data["market_value_cents"] += 1
    with pytest.raises(ValidationError):
        model.model_validate(data)


def test_snapshot_rejects_stale_mismatched_marks_future_rates_and_duplicate_positions():
    for mutate in (
        lambda p: p["bonds"][0].update(observed_price_index="1"),
        lambda p: p["market_rates"].update(observed_at="2026-01-01T18:00:00"),
        lambda p: p["bonds"][0].update(marked_at="2026-01-01T16:00:00"),
        lambda p: p["equities"][0].update(position_id="bond-1"),
        lambda p: p["overdraft"].update(principal_cents=50000001),
    ):
        data = fixture("four_tier_request")["portfolio"]
        mutate(data)
        with pytest.raises(ValidationError):
            e.FourTierPortfolioState.model_validate(data)


@pytest.mark.parametrize("mutation", ["future_history", "gap", "reverse", "metadata", "forecast_quarter_hour"])
def test_request_rejects_future_or_nonhourly_data(mutation):
    data = fixture("four_tier_request")
    if mutation == "future_history":
        data["history"][-1]["timestamp"] = "2026-01-01T18:00:00"
    elif mutation == "gap":
        data["history"][0]["timestamp"] = "2026-01-01T15:00:00"
    elif mutation == "reverse":
        data["history"].reverse()
    elif mutation == "metadata":
        data["metadata"]["training_data_through"] = "2026-01-01T18:00:00"
    else:
        data["forecast"][0]["start_at"] = "2026-01-01T18:15:00"
    with pytest.raises(ValidationError):
        e.FourTierRecommendationRequest.model_validate(data)


def test_cannot_claim_evaluation_without_reference_or_realized_estimates():
    data = fixture("four_tier_request")["metadata"]
    data["uncertainty_status"] = "evaluated"
    with pytest.raises(ValidationError):
        e.ForecastRiskMetadata.model_validate(data)
    estimate = fixture("four_tier_response")["instrument_returns"][0]
    estimate["realized"] = True
    with pytest.raises(ValidationError):
        e.InstrumentReturnEstimate.model_validate(estimate)


@pytest.mark.parametrize("mutation", ["execution", "boolean", "reserve", "budget", "constraints", "hold_trades", "duplicate_trade", "overdraft_target"])
def test_recommendation_invariants(mutation):
    data = fixture("four_tier_response")
    if mutation == "execution":
        data["execution_status"] = "EXECUTED"
    elif mutation == "boolean":
        data["recommendation_only"] = 1
    elif mutation == "reserve":
        data["required_liquid_reserve_cents"] = 90000001
    elif mutation == "budget":
        data["allocation_budget_cents"] += 1
    elif mutation == "constraints":
        data["exposure_constraints"][1]["maximum_fraction"] = "0.01"
    elif mutation == "hold_trades":
        data["action"] = "HOLD"
    elif mutation == "duplicate_trade":
        data["trades"] *= 2
    else:
        data["targets"][0]["instrument"] = "OVERDRAFT"
    with pytest.raises(ValidationError):
        e.PortfolioRecommendation.model_validate(data)


@pytest.mark.parametrize("instrument,action,units,position", [
    ("TIER1_REPO", "REDEEM_REPO", None, "repo-1"),
    ("TIER2_BOND", "BUY", "1.00000000000000001", None),
    ("TIER3_EQUITY", "SELL", "0.000000001", "equity-1"),
    ("OVERDRAFT", "BORROW", None, None), ("OVERDRAFT", "REPAY", None, None),
])
def test_executable_shape_recommendations_without_execution(instrument, action, units, position):
    trade = fixture("four_tier_response")["trades"][0]
    trade.update(instrument=instrument, action=action, index_units=units,
                 position_id=position, expected_maturity_at=None)
    parsed = e.TradeRecommendation.model_validate(trade)
    assert parsed.execution_status == "NOT_EXECUTED"
    assert e.TradeRecommendation.model_validate_json(parsed.model_dump_json()) == parsed


@pytest.mark.parametrize("field,value", [("instrument", "TIER0_CASH"), ("action", "SELL"),
    ("expected_maturity_at", "2026-01-02T17:00:00"), ("execution_status", "EXECUTED"),
    ("expected_settlement_at", "2026-01-01T16:00:00")])
def test_invalid_trade_shapes(field, value):
    trade = fixture("four_tier_response")["trades"][0]
    trade[field] = value
    with pytest.raises(ValidationError):
        e.TradeRecommendation.model_validate(trade)


def test_policy_exposure_bounds_and_liability_limits():
    data = fixture("four_tier_request")["policy"]
    data["overdraft_allowed"] = False
    with pytest.raises(ValidationError):
        e.FourTierRiskPolicy.model_validate(data)
    data = fixture("four_tier_request")["policy"]
    data["exposure_constraints"] = data["exposure_constraints"][:3]
    with pytest.raises(ValidationError):
        e.FourTierRiskPolicy.model_validate(data)
    with pytest.raises(ValidationError):
        e.ExposureConstraint(instrument="TIER0_CASH", minimum_fraction="0.8", maximum_fraction="0.2")


def test_old_contracts_and_function_signatures_are_unchanged():
    examples = fixture("contracts")
    for name, value in examples.items():
        model = getattr(e, name)
        assert json.loads(model.model_validate(value).model_dump_json()) == value
    assert list(inspect.signature(e.forecast_cashflows).parameters) == [
        "history", "as_of", "horizon_minutes", "bucket_minutes", "model_version"]
    assert list(inspect.signature(e.calculate_required_reserve).parameters) == ["forecast", "policy"]
    assert list(inspect.signature(e.recommend_treasury_action).parameters) == ["context", "forecast", "policy"]
    assert list(inspect.signature(e.run_treasury_pipeline).parameters) == [
        "scenario_name", "history", "context", "policy", "horizon_minutes", "bucket_minutes", "model_version", "forecast"]
    with pytest.raises(ValidationError):
        e.TreasuryContext(as_of="2026-01-01T00:00:00", currency="USD", checking_balance_cents=0)


def test_public_imports_and_contract_only_portfolio_interface():
    module = importlib.import_module("treasury_intelligence.four_tier")
    for name in ("OrganizerHourlyObservation", "FourTierPortfolioState", "PortfolioRecommendation", "TradeRecommendation"):
        assert getattr(module, name) is getattr(e, name)
    assert api.recommend_portfolio_allocation is e.recommend_portfolio_allocation
    request = e.FourTierRecommendationRequest.model_validate(fixture("four_tier_request"))
    before = request.model_dump_json()
    with pytest.raises(NotImplementedError, match="contracts only"):
        e.recommend_portfolio_allocation(request)
    assert request.model_dump_json() == before


def test_new_contract_imports_need_no_ml_database_or_web_framework():
    script = """
import importlib.abc
import sys
class BlockExternalImplementations(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'sqlalchemy', 'fastapi', 'sklearn', 'torch', 'tensorflow'}:
            raise ImportError('forbidden implementation dependency: ' + fullname)
sys.meta_path.insert(0, BlockExternalImplementations())
from treasury_intelligence import FourTierRecommendationRequest, PortfolioRecommendation
from treasury_intelligence.api import recommend_portfolio_allocation
"""
    completed = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
