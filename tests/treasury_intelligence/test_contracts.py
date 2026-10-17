import inspect
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

import treasury_intelligence as engine

EXAMPLES = json.loads((Path(__file__).parent / "fixtures/contracts.json").read_text())


@pytest.mark.parametrize("name", EXAMPLES)
def test_json_round_trip_and_immutable_contract(name):
    model = getattr(engine, name)
    value = model.model_validate_json(json.dumps(EXAMPLES[name]))
    assert model.model_validate_json(value.model_dump_json()) == value
    assert json.loads(value.model_dump_json()) == EXAMPLES[name]
    field = next(iter(model.model_fields))
    with pytest.raises(ValidationError):
        setattr(value, field, getattr(value, field))
    with pytest.raises(ValidationError):
        model.model_validate(dict(EXAMPLES[name], unknown_field=1))


@pytest.mark.parametrize("name,field,value", [
    ("CashFlowBucket", "inflow_cents", -1),
    ("CashFlowBucket", "inflow_cents", 1.5),
    ("CashFlowBucket", "inflow_cents", True),
    ("CashFlowBucket", "inflow_cents", "100"),
    ("CashFlowBucket", "start_at", "2026-10-17T12:00:00"),
    ("CashFlowBucket", "start_at", "2026-10-17T12:00:00+05:30"),
    ("CashFlowBucket", "start_at", 1792238400),
    ("CashFlowBucket", "end_at", "2026-10-17T11:00:00Z"),
    ("VaultPosition", "withdrawable_cents", 30000001),
    ("VaultPosition", "annual_yield_bps", 10001),
    ("TreasuryPolicy", "uncertainty_multiplier_bps", -1),
    ("TreasuryContext", "currency", "usd"),
    ("ReserveResult", "required_reserve_cents", 1),
    ("DecisionResult", "recommendation_only", False),
    ("DecisionResult", "recommendation_only", 1),
    ("DecisionResult", "action", "EXECUTE"),
    ("DecisionResult", "amount_cents", 0),
    ("DecisionResult", "vault_id", None),
    ("DecisionResult", "action", "HOLD"),
    ("DecisionResult", "action", "LIQUIDITY_WARNING"),
    ("DecisionResult", "as_of", "2026-10-17T13:00:00Z"),
    ("EvaluationResult", "sample_count", 0),
    ("EvaluationResult", "coverage_bps", 10001),
    ("RiskScenarioResult", "seed", -1),
    ("OptimizationResult", "allocation_bps", 10001),
    ("OptimizationResult", "recommendation_only", False),
    ("OptimizationResult", "feasible", "true"),
])
def test_invalid_inputs(name, field, value):
    with pytest.raises(ValidationError):
        getattr(engine, name).model_validate(dict(EXAMPLES[name], **{field: value}))


def test_nested_constraints():
    forecast = EXAMPLES["ForecastResult"]
    for points in ([], forecast["points"] * 2):
        with pytest.raises(ValidationError):
            engine.ForecastResult.model_validate(dict(forecast, points=points))
    context = EXAMPLES["TreasuryContext"]
    with pytest.raises(ValidationError):
        engine.TreasuryContext.model_validate(dict(context, vaults=context["vaults"] * 2))
    with pytest.raises(ValidationError):
        engine.ForecastResult.model_validate(dict(forecast, generated_at="2026-10-17T14:00:00Z"))


@pytest.mark.parametrize("name,field", [
    (name, field) for name, example in EXAMPLES.items()
    for field in example if field.endswith("_cents") or field.endswith("_bps")
])
def test_all_financial_fields_reject_negative_values(name, field):
    with pytest.raises(ValidationError):
        getattr(engine, name).model_validate(dict(EXAMPLES[name], **{field: -1}))


@pytest.mark.parametrize("action", ["HOLD", "LIQUIDITY_WARNING", "WITHDRAW"])
def test_other_valid_recommendations(action):
    example = dict(EXAMPLES["DecisionResult"], action=action)
    if action != "WITHDRAW":
        example.update(amount_cents=0, vault_id=None)
    assert engine.DecisionResult.model_validate(example).action == action


def test_fixture_financial_consistency():
    context = engine.TreasuryContext.model_validate(EXAMPLES["TreasuryContext"])
    decision = engine.DecisionResult.model_validate(EXAMPLES["DecisionResult"])
    assert context.checking_balance_cents - decision.amount_cents == decision.reserve.required_reserve_cents
    point = engine.ForecastPoint.model_validate(EXAMPLES["ForecastPoint"])
    assert point.outflow_cents - point.inflow_cents == decision.reserve.net_drain_cents


@pytest.mark.parametrize("name", [
    "forecast_cashflows", "recommend_treasury_action", "evaluate_forecasting_models",
    "generate_risk_scenarios", "evaluate_allocation_candidates",
])
def test_public_functions_are_contract_only(name):
    function = getattr(engine, name)
    signature = inspect.signature(function)
    arguments = {n: None for n, p in signature.parameters.items() if p.default is inspect.Parameter.empty}
    with pytest.raises(NotImplementedError, match="contracts only"):
        function(**arguments)
