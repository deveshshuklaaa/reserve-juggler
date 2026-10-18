from datetime import datetime
import json

import pytest
from pydantic import ValidationError

from app.backtesting import BacktestRequest, ScenarioSpec
from app.backtesting.contracts import ComparisonResult, EngineState, HourReceipt, JS_MAX
from app.backtesting.protocol import EngineCapabilities
from .fakes import journal, state
from .test_service import evaluate


@pytest.mark.parametrize("field,value", [
    ("initial_capital_cents", True), ("initial_capital_cents", "100"), ("initial_capital_cents", 1.5),
    ("initial_capital_cents",-1), ("initial_capital_cents",JS_MAX+1), ("seed",False), ("seed",-1),
    ("days", True), ("days","7"), ("days",7.0), ("days",1),
    ("start","2026-01-01T00:00:00Z"), ("start","2026-01-01T00:15:00"),
    ("start",1767225600), ("start","2026-01-01T00:00:00+05:30"),
    ("unknown",1),
])
def test_request_strictness(request_spec, field, value):
    with pytest.raises(ValidationError):
        BacktestRequest(**(request_spec.model_dump() | {field:value}))


@pytest.mark.parametrize("value", [
    "[]", '{"x":0.1}', '{"x":NaN}', '{"x":Infinity}', '{"x":1,"x":2}',
    '{"nested":{"x":1,"x":2}}', '{"x":9007199254740992}', '{"nested":[0.5]}',
])
def test_configuration_is_exact_unambiguous_and_immutable(request_spec, value):
    with pytest.raises(ValidationError):
        BacktestRequest(**(request_spec.model_dump() | {"policy_json":value}))
    with pytest.raises(ValidationError):
        ScenarioSpec(parameters_json=value)


def test_configuration_canonicalized_and_models_frozen(request_spec):
    config = '{"z":{"b":"0.00250","a":null},"a":[3,true]}'
    spec = BacktestRequest(**(request_spec.model_dump() | {"policy_json":config}))
    assert spec.policy_json == '{"a":[3,true],"z":{"a":null,"b":"0.00250"}}'
    assert BacktestRequest.model_validate_json(spec.model_dump_json()) == spec
    with pytest.raises(ValidationError):
        spec.seed = 3
    with pytest.raises(ValidationError):
        ScenarioSpec(name="INVENTED")


@pytest.mark.parametrize("field,value", [
    ("checking_cents",-1), ("tier2_value_cents",1.0), ("net_asset_value_cents",123),
    ("borrowing_outstanding_cents",True), ("unpaid_borrowing_costs_cents",-1),
    ("accrued_interest_cents",JS_MAX+1),
])
def test_balance_sheet_validation_including_copied_model(field, value):
    invalid = state(100).model_copy(update={field:value})
    with pytest.raises(ValidationError):
        EngineState.model_validate(invalid)


def test_asset_sum_must_also_be_safe():
    with pytest.raises(ValidationError, match="Gross assets"):
        EngineState(checking_cents=JS_MAX, tier1_value_cents=1, tier2_value_cents=0, tier3_value_cents=0,
            borrowing_outstanding_cents=JS_MAX, unpaid_borrowing_costs_cents=0,
            accrued_interest_cents=0, unrealized_market_pnl_cents=0, net_asset_value_cents=1)


@pytest.fixture
def receipt():
    return journal(state(100), timestamp=datetime(2026,1,1), digest="f"*64,
                   event_ids=("interest",), realized_interest_cents=10)


@pytest.mark.parametrize("change", [
    {"source_digest":"not-a-hash"}, {"timestamp":"2026-01-01T00:30:00"},
    {"realized_interest_cents":True}, {"realized_interest_cents":"10"},
    {"realized_interest_cents":JS_MAX+1}, {"realized_interest_cents":9},
    {"event_ids":("x","x")}, {"event_ids":(" ",)}, {"event_ids":()},
    {"borrowing_costs_cents":-1}, {"contractual_penalties_cents":1},
    {"financing_cash_delta_cents":1}, {"paid_borrowing_costs_cents":1},
    {"realized_market_pnl_cents":1}, {"extra":"value"},
])
def test_receipts_reject_ambiguous_or_unreconciled_accounting(receipt, change):
    with pytest.raises(ValidationError):
        HourReceipt.model_validate(receipt.model_copy(update=change))


def test_nested_copied_state_is_not_trusted(receipt):
    invalid = receipt.model_copy(update={"opening":receipt.opening.model_copy(update={"checking_cents":True})})
    with pytest.raises(ValidationError):
        HourReceipt.model_validate(invalid)


def test_negative_interest_and_unpaid_positive_accrual_remain_separate():
    negative = journal(state(100), timestamp=datetime(2026,1,1), digest="f"*64,
                       event_ids=("negative-rate",), realized_interest_cents=-1)
    assert negative.closing.net_asset_value_cents == 99
    accrued = journal(state(100), timestamp=datetime(2026,1,1), digest="f"*64, event_ids=("accrue",),
                      stock_changes={"tier1_value_cents":3,"accrued_interest_cents":3})
    assert accrued.realized_interest_cents == 0
    assert accrued.closing.checking_cents == 100 and accrued.closing.net_asset_value_cents == 103
    # Principal value includes accrued interest; it must not be added again to NAV.
    assert accrued.closing.tier1_value_cents == 3 and accrued.closing.accrued_interest_cents == 3


@pytest.mark.parametrize("change", [
    {"execution_kind":"SHARED","integration_sha":None},
    {"execution_kind":"SHARED","integration_sha":"b3cc3d7"},
    {"execution_kind":"SHARED","integration_sha":"g"*40},
    {"execution_kind":"TEST_DOUBLE","integration_sha":"a"*40},
    {"strategies":("STATIC","STATIC")},
])
def test_engine_provenance_is_explicit(change):
    caps = EngineCapabilities(engine_version="unit", execution_kind="TEST_DOUBLE", integration_sha=None,
                              strategies=("STATIC",), scenarios=("NORMAL",))
    with pytest.raises(ValidationError):
        EngineCapabilities.model_validate(caps.model_copy(update=change))


def test_provider_shared_sha_syntax_only_not_a_claim_of_integration():
    caps = EngineCapabilities(engine_version="sample", execution_kind="SHARED", integration_sha="a"*40,
                              strategies=("STATIC",), scenarios=("NORMAL",))
    assert caps.integration_sha == "a"*40  # syntactic validation; publication must be verified separately


def test_output_rejects_tampered_summary_or_history(source, request_spec):
    result = evaluate(source, request_spec)
    item = result.results[0]
    for changes in ({"net_benefit_cents":1}, {"average_checking_cents":3},
                    {"history":item.history[:-1]}, {"penalties_cents":1}):
        invalid = result.model_copy(update={"results":(item.model_copy(update=changes), *result.results[1:])})
        with pytest.raises(ValidationError):
            ComparisonResult.model_validate(invalid)
    wire = json.loads(result.model_dump_json())
    assert all(item["model_evaluation"] is None for item in wire["results"])
