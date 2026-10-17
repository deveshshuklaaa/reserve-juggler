"""Contract-only four-tier acceptance: no ORM, database, clock or algorithms."""
from copy import deepcopy
from datetime import datetime, timedelta
from decimal import Decimal, localcontext
import json
from pathlib import Path
import subprocess
import sys
from uuid import UUID

from pydantic import TypeAdapter, ValidationError
import pytest

import treasury_intelligence as engine


FIXTURE = json.loads((Path(__file__).parent / "fixtures/four_tier_portfolio.json").read_text())


def source():
    return {key: FIXTURE[key] for key in engine.PortfolioSource.model_fields}


def reserve():
    return dict(time_basis="UNSPECIFIED", as_of=FIXTURE["as_of"], net_drain_cents=100,
                uncertainty_buffer_cents=20, base_buffer_cents=10, required_reserve_cents=130)


def order(**updates):
    return dict(source(), id="00000000-0000-0000-0000-000000000020", as_of=FIXTURE["as_of"],
                action="BUY_BONDS", tier=2, amount_cents=100, reason="supplied fixture, not executed", **updates)


def test_complete_hourly_snapshot_round_trip_determinism_and_tier_separation():
    value = engine.PortfolioState.model_validate(FIXTURE)
    assert engine.PortfolioState.model_validate_json(value.model_dump_json()) == value
    assert value.model_dump_json() == engine.PortfolioState.model_validate(FIXTURE).model_dump_json()
    assert engine.PortfolioTreasuryContext is engine.PortfolioState
    assert value.as_of.tzinfo is None
    assert value.native_interval_seconds == 3600
    assert value.repo_positions[0].scheduled_maturity_at - value.repo_positions[0].entered_at == timedelta(hours=15)
    assert value.repo_positions[0].applicable_apy_pct == Decimal("4.308")
    assert value.bond_positions[0].current_market_price_index != value.bond_positions[0].acquisition_price_index
    assert value.bond_positions[0].unrealized_pnl_cents == -10
    assert value.equity_positions[0].supplied_volatility_pct == Decimal("18.0")
    assert value.valuation.immediately_available_cents != value.valuation.total_portfolio_value_cents
    assert value.valuation.net_portfolio_value_cents == 820000
    assert value.overdrafts[0].outstanding_principal_cents == 10000
    assert [p.tier for p in (value.cash, *value.repo_positions, *value.bond_positions, *value.equity_positions)] == [0, 1, 2, 3]


@pytest.mark.parametrize("model,payload", [
    (engine.PortfolioSource, source()),
    (engine.CashPosition, FIXTURE["cash"]),
    (engine.RepoPosition, FIXTURE["repo_positions"][0]),
    (engine.BondPosition, FIXTURE["bond_positions"][0]),
    (engine.EquityPosition, FIXTURE["equity_positions"][0]),
    (engine.OverdraftLiability, FIXTURE["overdrafts"][0]),
    (engine.PortfolioValuation, FIXTURE["valuation"]),
    (engine.PortfolioState, FIXTURE),
    (engine.FourTierReserveResult, reserve()),
    (engine.RecommendedOrder, order()),
    (engine.FourTierDecisionResult, dict(source(), as_of=FIXTURE["as_of"], action="ALLOCATE",
                                        reserve=reserve(), orders=[order()], reason="fixture")),
    (engine.FourTierTreasuryPolicy, dict(base_buffer_cents=0, uncertainty_multiplier_bps=10000,
        tolerance_bps=0, min_transfer_cents=0, max_allocation_bps=10000, repo_sweep_window_open=True,
        tier_limits=[dict(tier=1, max_allocation_bps=5000)])),
])
def test_all_models_json_frozen_and_extra_forbidden(model, payload):
    value = model.model_validate(payload)
    assert model.model_validate_json(value.model_dump_json()) == value
    with pytest.raises(ValidationError):
        model.model_validate(dict(payload, unknown=True))
    with pytest.raises(ValidationError):
        setattr(value, next(iter(model.model_fields)), None)


@pytest.mark.parametrize("model,path", [(engine.CashPosition, "cash"), (engine.RepoPosition, "repo_positions"),
                                       (engine.BondPosition, "bond_positions"), (engine.EquityPosition, "equity_positions")])
def test_discriminated_union_and_strict_tiers(model, path):
    payload = FIXTURE[path] if path == "cash" else FIXTURE[path][0]
    adapter = TypeAdapter(engine.TreasuryPosition)
    assert isinstance(adapter.validate_json(json.dumps(payload)), model)
    for bad in (True, str(payload["tier"]), float(payload["tier"]), 99):
        with pytest.raises(ValidationError):
            model.model_validate(dict(payload, tier=bad))


@pytest.mark.parametrize("field,bad", [
    ("principal_cents", -1), ("principal_cents", True), ("principal_cents", 1.0), ("principal_cents", "1"),
    ("applicable_apy_pct", 4.308), ("applicable_apy_pct", True), ("applicable_apy_pct", "NaN"),
    ("applicable_apy_pct", "Infinity"), ("applicable_apy_pct", "-Infinity"),
    ("early_redemption_haircut_pct", "100.01"), ("early_redemption_haircut_pct", "-0.1"),
    ("scheduled_maturity_at", "2026-01-01T16:00:00"), ("entered_at", 123),
    ("entered_at", "2026-01-01T17:00:00Z"), ("early_redemption_at", "2026-01-02T08:00:00"),
    ("id", "not-a-position-id"), ("time_basis", "UTC"), ("dataset_id", None),
])
def test_invalid_repo_quantities_times_and_provenance(field, bad):
    with pytest.raises(ValidationError):
        engine.RepoPosition.model_validate(dict(FIXTURE["repo_positions"][0], **{field: bad}))


@pytest.mark.parametrize("field,bad", [("quantity", "0"), ("quantity", 1.1), ("quantity", "NaN"),
    ("acquisition_price_index", "-1"), ("modified_duration", "0"),
    ("current_market_value_cents", -1), ("realized_pnl_cents", True)])
def test_invalid_market_inputs(field, bad):
    with pytest.raises(ValidationError):
        engine.BondPosition.model_validate(dict(FIXTURE["bond_positions"][0], **{field: bad}))


def test_exact_rates_not_quantized_even_under_low_decimal_context():
    rate = "4.308000000000000000000000000000000001"
    index = "99.9500000000000000000000000000000000001"
    with localcontext() as context:
        context.prec = 5
        repo = engine.RepoPosition.model_validate(dict(FIXTURE["repo_positions"][0], applicable_apy_pct=rate))
        bond = engine.BondPosition.model_validate(dict(FIXTURE["bond_positions"][0], current_market_price_index=index))
        assert engine.RepoPosition.model_validate_json(repo.model_dump_json()).applicable_apy_pct.as_tuple() == Decimal(rate).as_tuple()
        assert engine.BondPosition.model_validate_json(bond.model_dump_json()).current_market_price_index.as_tuple() == Decimal(index).as_tuple()
    # Negative supplied yields and signed P&L are representable, not guaranteed returns.
    assert engine.RepoPosition.model_validate(dict(FIXTURE["repo_positions"][0], applicable_apy_pct="-0.01")).applicable_apy_pct < 0


def test_equity_cannot_be_disguised_as_interest_bearing_vault():
    for field in ("annual_yield_bps", "applicable_apy_pct", "accrued_interest_cents"):
        with pytest.raises(ValidationError):
            engine.EquityPosition.model_validate(dict(FIXTURE["equity_positions"][0], **{field: 100}))
    with pytest.raises(ValidationError):
        engine.VaultPosition.model_validate(FIXTURE["bond_positions"][0])


@pytest.mark.parametrize("change", ["cash_yield", "cash_liquidity", "locked_cash", "bonds_as_cash",
    "run", "dataset", "duplicate_id", "future_observation", "future_market", "quarter_hour",
    "total", "net", "missing_liability", "principal_identity", "valuation_time", "valuation_tier",
    "liquidity_total", "missing_market_value", "closed_position"])
def test_snapshot_rejects_incoherent_financial_state(change):
    data = deepcopy(FIXTURE)
    if change == "cash_yield": data["cash"]["apy_pct"] = "0.1"
    elif change == "cash_liquidity": data["cash"]["liquidity"]["available_cents"] = 1
    elif change == "locked_cash": data["repo_positions"][0]["liquidity"]["available_cents"] = 1
    elif change == "bonds_as_cash": data["bond_positions"][0]["liquidity"].update(classification="IMMEDIATE", available_cents=1)
    elif change == "run": data["bond_positions"][0]["run_id"] = str(UUID(int=99))
    elif change == "dataset": data["repo_positions"][0]["dataset_id"] = "another-dataset"
    elif change == "duplicate_id": data["equity_positions"][0]["id"] = data["cash"]["id"]
    elif change == "future_observation": data["source_observation_timestamp"] = "2026-01-01T18:00:00"
    elif change == "future_market": data["equity_positions"][0]["market_observation_timestamp"] = "2026-01-01T18:00:00"
    elif change == "quarter_hour": data["native_interval_seconds"] = 900
    elif change == "total": data["valuation"]["total_portfolio_value_cents"] += 1
    elif change == "net": data["valuation"]["net_portfolio_value_cents"] += 1
    elif change == "missing_liability": data["valuation"].update(liabilities_cents=0, net_portfolio_value_cents=830000)
    elif change == "principal_identity": data["overdrafts"][0]["repaid_principal_cents"] = 1
    elif change == "valuation_time": data["valuation"]["valued_at"] = "2026-01-01T16:00:00"
    elif change == "valuation_tier": data["valuation"].update(tier1_value_cents=100011, tier2_market_value_cents=19989)
    elif change == "liquidity_total": data["valuation"]["liquidatable_value_cents"] -= 1
    elif change == "missing_market_value": data["bond_positions"][0]["current_market_value_cents"] = None
    elif change == "closed_position": data["bond_positions"][0]["status"] = "CLOSED"
    with pytest.raises(ValidationError):
        engine.PortfolioState.model_validate(data)


def test_synthetic_utc_and_historical_naive_are_explicit_not_converted():
    data = dict(FIXTURE["repo_positions"][0], time_basis="UTC", source_type="SYNTHETIC",
                dataset_id=None, source_observation_timestamp=None,
                entered_at="2026-01-01T17:00:00Z", scheduled_maturity_at="2026-01-02T08:00:00Z")
    assert engine.RepoPosition.model_validate(data).entered_at.utcoffset() == timedelta(0)
    for bad in ("2026-01-01T17:00:00", "2026-01-01T17:00:00+05:30"):
        with pytest.raises(ValidationError):
            engine.RepoPosition.model_validate(dict(data, entered_at=bad))
    with pytest.raises(ValidationError):
        engine.FourTierReserveResult.model_validate(dict(reserve(), time_basis="UTC"))


@pytest.mark.parametrize("action,tier", [("INVEST_REPO", 1), ("REDEEM_REPO", 1), ("BUY_BONDS", 2),
    ("SELL_BONDS", 2), ("BUY_EQUITIES", 3), ("SELL_EQUITIES", 3), ("BORROW_OVERDRAFT", 0), ("REPAY_OVERDRAFT", 0)])
def test_all_instrument_actions_are_recommendations_only(action, tier):
    data = order()
    data.update(action=action, tier=tier, position_id=UUID(int=10))
    if action == "INVEST_REPO":
        data.update(earliest_execution_at="2026-01-01T17:00:00", expected_settlement_at="2026-01-01T17:00:00",
                    expected_maturity_at="2026-01-02T08:00:00")
    value = engine.RecommendedOrder.model_validate(data)
    assert value.recommendation_only is True
    assert engine.RecommendedOrder.model_validate_json(value.model_dump_json()) == value


@pytest.mark.parametrize("change", ["executed", "bool_true", "wrong_tier", "zero", "missing_position",
                                  "hold_orders", "empty_allocate", "duplicate_order", "wrong_source", "wrong_reserve"])
def test_invalid_recommendation_plans(change):
    data = dict(source(), as_of=FIXTURE["as_of"], action="ALLOCATE", reserve=reserve(), orders=[order()], reason="fixture")
    if change == "executed": data["recommendation_only"] = False
    elif change == "bool_true": data["orders"][0]["recommendation_only"] = 1
    elif change == "wrong_tier": data["orders"][0]["tier"] = 3
    elif change == "zero": data["orders"][0]["amount_cents"] = 0
    elif change == "missing_position": data["orders"][0]["action"] = "SELL_BONDS"
    elif change == "hold_orders": data["action"] = "HOLD"
    elif change == "empty_allocate": data["orders"] = []
    elif change == "duplicate_order": data["orders"] *= 2
    elif change == "wrong_source": data["orders"][0]["run_id"] = str(UUID(int=99))
    elif change == "wrong_reserve": data["reserve"]["required_reserve_cents"] = 0
    with pytest.raises(ValidationError):
        engine.FourTierDecisionResult.model_validate(data)


def test_negative_net_value_and_losses_are_not_clipped():
    data = dict(FIXTURE["valuation"], liabilities_cents=900000, net_portfolio_value_cents=-70000)
    assert engine.PortfolioValuation.model_validate(data).net_portfolio_value_cents == -70000


@pytest.mark.parametrize("change", ["duplicate", "bad_cap", "bool_tier", "bool_permission"])
def test_four_tier_policy_controls_are_strict(change):
    data = dict(base_buffer_cents=0, uncertainty_multiplier_bps=10000, tolerance_bps=0,
                min_transfer_cents=0, max_allocation_bps=10000, repo_sweep_window_open=False,
                tier_limits=[dict(tier=1, max_allocation_bps=5000)])
    if change == "duplicate": data["tier_limits"] *= 2
    elif change == "bad_cap": data["tier_limits"][0]["max_allocation_bps"] = 10001
    elif change == "bool_tier": data["tier_limits"][0]["tier"] = True
    else: data["allow_early_repo_redemption"] = "true"
    with pytest.raises(ValidationError):
        engine.FourTierTreasuryPolicy.model_validate(data)


def test_plans_reject_future_source_and_support_warning_without_fake_orders():
    data = dict(source(), as_of=FIXTURE["as_of"], action="LIQUIDITY_WARNING", reserve=reserve(), reason="shortfall")
    assert engine.FourTierDecisionResult.model_validate(data).orders == ()
    data["source_observation_timestamp"] = "2026-01-01T18:00:00"
    with pytest.raises(ValidationError):
        engine.FourTierDecisionResult.model_validate(data)


def test_public_json_schemas_support_instrument_discrimination():
    for model in (engine.PortfolioState, engine.FourTierDecisionResult, engine.FourTierTreasuryPolicy):
        assert model.model_json_schema()["type"] == "object"
    schema = TypeAdapter(engine.TreasuryPosition).json_schema()
    assert set(schema["discriminator"]["mapping"]) == {"0", "1", "2", "3"}


def test_standalone_imports_have_no_database_or_web_dependencies():
    code = "import sys; import treasury_intelligence; assert not {'sqlalchemy', 'fastapi', 'app.database'} & set(sys.modules)"
    subprocess.run([sys.executable, "-B", "-c", code], check=True, capture_output=True, text=True)
