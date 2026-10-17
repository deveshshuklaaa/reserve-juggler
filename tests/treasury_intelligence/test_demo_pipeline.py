from datetime import datetime, timezone
import pytest

import treasury_intelligence as e
from treasury_intelligence.demo import (
    DEMO_AS_OF,
    build_deterministic_history,
    create_demo_policy,
    run_all_demo_scenarios,
    run_demo,
    run_scenario_1_normal_operation,
    run_scenario_2_valid_safe_sweep,
    run_scenario_3_high_withdrawal_stress,
    run_scenario_4_locked_vault_insufficient_liquidity,
    run_scenario_5_successful_hold,
)
from treasury_intelligence.pipeline import TreasuryPipelineResult, run_treasury_pipeline


def test_pipeline_normal_operation():
    history = build_deterministic_history()
    result = run_scenario_1_normal_operation(history)

    assert isinstance(result, TreasuryPipelineResult)
    assert result.decision.action == "HOLD"
    assert result.uncertainty_status == "provisional_uncalibrated"
    assert "provisional" in result.uncertainty_note.lower()
    assert result.reserve.required_reserve_cents > 0
    assert result.reserve.required_reserve_cents == (
        result.reserve.net_drain_cents
        + result.reserve.uncertainty_buffer_cents
        + result.reserve.base_buffer_cents
    )


def test_pipeline_valid_safe_sweep():
    history = build_deterministic_history()
    result = run_scenario_2_valid_safe_sweep(history)

    assert result.decision.action == "SWEEP"
    assert result.decision.amount_cents > 0
    assert result.decision.vault_id == "treasury_repo_liquid"
    assert "candidate_cents=" in result.decision.reason
    assert "expected_net_benefit_cents=" in result.decision.reason
    assert result.decision.recommendation_only is True


def test_pipeline_high_withdrawal_stress():
    history = build_deterministic_history()
    result = run_scenario_3_high_withdrawal_stress(history)

    assert result.decision.action == "WITHDRAW"
    assert result.decision.amount_cents > 0
    assert result.decision.vault_id == "treasury_repo_liquid"
    assert "deficit_cents=" in result.decision.reason
    assert "immediate liquidity takes precedence over yield" in result.decision.reason


def test_pipeline_locked_vault_insufficient_liquidity():
    history = build_deterministic_history()
    result = run_scenario_4_locked_vault_insufficient_liquidity(history)

    assert result.decision.action == "LIQUIDITY_WARNING"
    assert result.decision.amount_cents == 0
    assert result.decision.vault_id is None
    assert "no single immediately redeemable vault covers deficit" in result.decision.reason


def test_pipeline_successful_hold():
    history = build_deterministic_history()
    result = run_scenario_5_successful_hold(history)

    assert result.decision.action == "HOLD"
    assert result.decision.amount_cents == 0
    assert result.decision.vault_id is None
    assert "within tolerance_bps=" in result.decision.reason


def test_pipeline_json_serialization_roundtrip():
    history = build_deterministic_history()
    results = run_all_demo_scenarios()
    assert len(results) == 5

    for res in results:
        json_str = res.model_dump_json(indent=2)
        deserialized = TreasuryPipelineResult.model_validate_json(json_str)

        assert deserialized == res
        assert deserialized.scenario_name == res.scenario_name
        assert deserialized.decision.action == res.decision.action
        assert deserialized.uncertainty_status == "provisional_uncalibrated"


def test_pipeline_deterministic_reproducibility():
    history1 = build_deterministic_history()
    history2 = build_deterministic_history()

    res1 = run_scenario_2_valid_safe_sweep(history1)
    res2 = run_scenario_2_valid_safe_sweep(history2)

    assert res1 == res2
    assert res1.model_dump_json() == res2.model_dump_json()


def test_pipeline_cli_demo_execution(capsys):
    # Running run_demo prints output and exits cleanly without error
    run_demo()
    captured = capsys.readouterr()
    assert "RESERVE JUGGLER" in captured.out
    assert "SCENARIO 1: NORMAL OPERATION" in captured.out
    assert "SCENARIO 2: VALID SAFE SWEEP" in captured.out
    assert "SCENARIO 3: HIGH-WITHDRAWAL STRESS" in captured.out
    assert "SCENARIO 4: LOCKED VAULT INSUFFICIENT LIQUIDITY" in captured.out
    assert "SCENARIO 5: SUCCESSFUL HOLD" in captured.out
    assert "JSON SERIALIZATION DEMONSTRATION" in captured.out
    assert "[OK] Verification" in captured.out
