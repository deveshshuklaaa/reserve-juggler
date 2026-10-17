from datetime import datetime, timedelta, timezone

import pytest

import treasury_intelligence as e

NOW = datetime(2026, 10, 17, 12, tzinfo=timezone.utc)


def vault(name="liquid", **overrides):
    return e.VaultPosition(**(dict(vault_id=name, balance_cents=1_000_000,
        withdrawable_cents=1_000_000, annual_yield_bps=500,
        withdrawal_delay_minutes=0) | overrides))


def terms(name="liquid", **overrides):
    return e.VaultTerms(**(dict(vault_id=name, sweep_eligible=True) | overrides))


def policy(**overrides):
    return e.TreasuryDecisionPolicy(**(dict(base_buffer_cents=100_000,
        uncertainty_multiplier_bps=10000, tolerance_bps=500,
        min_transfer_cents=10000, max_allocation_bps=10000,
        sweep_window_open=True, holding_minutes=1440, vault_terms=(terms(),)) | overrides))


def forecast(outflow=0):
    return e.ForecastResult(generated_at=NOW, model_version="test", points=(
        e.ForecastPoint(start_at=NOW, end_at=NOW + timedelta(days=1),
                        inflow_cents=0, outflow_cents=outflow, uncertainty_cents=0),))


def decide(balance=1_000_000, positions=None, settings=None, flow=None):
    context = e.TreasuryContext(as_of=NOW, currency="USD", checking_balance_cents=balance,
                                vaults=(vault(),) if positions is None else positions)
    original = context.model_dump_json()
    result = e.recommend_treasury_action(context, forecast() if flow is None else flow,
                                         policy() if settings is None else settings)
    assert context.model_dump_json() == original
    assert result.recommendation_only is True
    assert e.DecisionResult.model_validate_json(result.model_dump_json()) == result
    return result


def test_valid_sweep_and_calculated_explanation():
    result = decide()
    assert (result.action, result.amount_cents, result.vault_id) == ("SWEEP", 900000, "liquid")
    assert "required_reserve_cents=100000" in result.reason
    assert "candidate_cents=900000" in result.reason
    assert "checking_after_cents=100000" in result.reason
    expected = e.simple_annualized_vault_yield(900000, 500, holding_minutes=1440)
    assert f"expected_yield_cents={expected}" in result.reason
    assert f"expected_net_benefit_cents={expected}" in result.reason


@pytest.mark.parametrize("balance", [100000, 104000, 109999])
def test_hold_without_meaningful_surplus(balance):
    assert decide(balance=balance).action == "HOLD"


def test_minimum_boundary():
    assert decide(balance=110000).action == "SWEEP"


def test_withdraw_permitted():
    result = decide(balance=50000)
    assert (result.action, result.amount_cents) == ("WITHDRAW", 50000)
    assert "net_proceeds_cents=50000" in result.reason
    assert "checking_after_cents=100000" in result.reason


def test_locked_nonredeemable_is_warning_even_with_withdrawable_amount():
    result = decide(balance=50000, settings=policy(vault_terms=(terms(
        maturity_at=NOW + timedelta(days=5), early_redemption_allowed=False),)))
    assert result.action == "LIQUIDITY_WARNING"
    assert result.amount_cents == 0 and result.vault_id is None
    assert "accessible_net_cents=0" in result.reason


def test_early_redemption_penalty_grossed_up():
    term = terms(maturity_at=NOW + timedelta(days=5), early_redemption_allowed=True,
        early_redemption_penalty_bps=100, early_redemption_fixed_fee_cents=100,
        transaction_cost_cents=50)
    result = decide(balance=50000, settings=policy(vault_terms=(term,)))
    cost = e.early_redemption_penalty(result.amount_cents, 100, early_redemption=True, fixed_fee_cents=100)
    assert result.action == "WITHDRAW"
    assert result.amount_cents - cost - 50 == 50000
    assert f"penalty_cents={cost}" in result.reason
    smaller = result.amount_cents - 1
    assert smaller - e.early_redemption_penalty(smaller, 100, early_redemption=True, fixed_fee_cents=100) - 50 < 50000


def test_matured_vault_has_no_early_penalty():
    result = decide(balance=50000, settings=policy(vault_terms=(terms(
        maturity_at=NOW, early_redemption_penalty_bps=1000),)))
    assert result.action == "WITHDRAW" and result.amount_cents == 50000
    assert "penalty_cents=0" in result.reason


def test_maturity_does_not_unlock_unavailable_balance():
    assert decide(balance=50000, positions=(vault(withdrawable_cents=0),),
        settings=policy(vault_terms=(terms(maturity_at=NOW),))).action == "LIQUIDITY_WARNING"


def test_delayed_withdrawal_cannot_meet_immediate_deficit():
    assert decide(balance=50000, positions=(vault(withdrawal_delay_minutes=1),)).action == "LIQUIDITY_WARNING"


def test_sweep_window_closed():
    assert decide(settings=policy(sweep_window_open=False)).action == "HOLD"


@pytest.mark.parametrize("overrides,amount", [({"sweep_cap_cents": 200000}, 200000),
    ({"max_allocation_bps": 2500}, 250000),
    ({"sweep_cap_cents": 300000, "max_allocation_bps": 1000}, 100000)])
def test_sweep_caps(overrides, amount):
    result = decide(settings=policy(**overrides))
    assert result.action == "SWEEP" and result.amount_cents == amount


def test_capped_below_minimum():
    assert decide(settings=policy(sweep_cap_cents=9999)).action == "HOLD"


def test_negative_benefit_investment():
    result = decide(settings=policy(vault_terms=(terms(transaction_cost_cents=1000),)))
    assert result.action == "HOLD"
    assert "expected_net_benefit_cents=-877" in result.reason


def test_zero_benefit_and_ineligible_sweeps_hold():
    assert decide(positions=(vault(annual_yield_bps=0),)).action == "HOLD"
    assert decide(settings=policy(vault_terms=(terms(sweep_eligible=False),))).action == "HOLD"
    assert decide(positions=(vault(withdrawal_delay_minutes=1441),)).action == "HOLD"


def test_penalty_can_make_a_large_position_insufficient():
    result = decide(balance=0, positions=(vault(withdrawable_cents=100000),),
        settings=policy(vault_terms=(terms(maturity_at=NOW + timedelta(days=3),
            early_redemption_allowed=True, early_redemption_penalty_bps=100),)))
    assert result.action == "LIQUIDITY_WARNING"
    assert "accessible_net_cents=99000" in result.reason
    assert "unfunded_cents=1000" in result.reason


def test_deterministic_tie_break_ignores_input_order():
    settings = policy(vault_terms=(terms("a"), terms("b")))
    forward = decide(positions=(vault("a"), vault("b")), settings=settings)
    reverse = decide(positions=(vault("b"), vault("a")), settings=settings)
    assert forward == reverse and forward.vault_id == "a"


def test_transaction_fee_cannot_take_checking_below_reserve():
    result = decide(settings=policy(vault_terms=(terms(transaction_cost_cents=10),)))
    assert result.action == "SWEEP" and result.amount_cents == 899990
    assert 1000000 - result.amount_cents - 10 == result.reserve.required_reserve_cents


def test_multiple_vaults_best_positive_economics():
    result = decide(positions=(vault("low", annual_yield_bps=100), vault("high", annual_yield_bps=600)),
        settings=policy(vault_terms=(terms("low"), terms("high"))))
    assert result.action == "SWEEP" and result.vault_id == "high"


def test_multiple_vaults_cheapest_withdrawal():
    result = decide(balance=50000, positions=(vault("costly"), vault("cheap")),
        settings=policy(vault_terms=(terms("costly", transaction_cost_cents=100), terms("cheap"))))
    assert result.action == "WITHDRAW" and result.vault_id == "cheap"


def test_aggregate_cover_requires_separate_multi_vault_plan():
    result = decide(balance=0, positions=(vault("a", withdrawable_cents=60000), vault("b", withdrawable_cents=60000)),
        settings=policy(vault_terms=(terms("a"), terms("b"))))
    assert result.action == "LIQUIDITY_WARNING"
    assert "accessible_net_cents=120000" in result.reason
    assert "unfunded_cents=0" in result.reason


def test_action_precedence_deficit_before_window_minimum_or_investment():
    result = decide(balance=50000, settings=policy(sweep_window_open=False,
        min_transfer_cents=1000000, sweep_cap_cents=0))
    assert result.action == "WITHDRAW"
    assert decide(balance=50000, positions=(), settings=policy(vault_terms=())).action == "LIQUIDITY_WARNING"


def test_forecast_deficit_precedes_sweep_even_with_positive_checking():
    result = decide(flow=forecast(outflow=1_000_000))
    assert result.action == "WITHDRAW" and result.amount_cents == 100000
    assert "peak_shortfall_cents=1000000" in result.reason


def test_early_exit_permission_and_sweep_penalty():
    locked = terms(maturity_at=NOW + timedelta(days=3))
    assert decide(settings=policy(vault_terms=(locked,))).action == "HOLD"
    penalized = locked.model_copy(update={"early_redemption_allowed": True, "early_redemption_penalty_bps": 100})
    result = decide(settings=policy(vault_terms=(penalized,)))
    assert result.action == "HOLD" and "penalty_cents=9000" in result.reason
    assert decide(settings=policy(vault_terms=(locked,), holding_minutes=3 * 1440)).action == "SWEEP"


def test_plain_policy_keeps_missing_eligibility_closed():
    plain = e.TreasuryPolicy(**policy().model_dump(include=set(e.TreasuryPolicy.model_fields)))
    assert decide(settings=plain).action == "HOLD"
    assert decide(balance=0, settings=plain).action == "LIQUIDITY_WARNING"


def test_unknown_or_duplicate_terms_are_rejected():
    with pytest.raises(ValueError):
        decide(settings=policy(vault_terms=(terms("unknown"),)))
    with pytest.raises(ValueError):
        policy(vault_terms=(terms(), terms()))


def test_json_policy_round_trip():
    settings = policy(vault_terms=(terms(maturity_at=NOW),))
    assert e.TreasuryDecisionPolicy.model_validate_json(settings.model_dump_json()) == settings


@pytest.mark.parametrize("overrides", [{"sweep_window_open": 1}, {"holding_minutes": 0},
    {"sweep_cap_cents": -1}])
def test_invalid_controls(overrides):
    with pytest.raises(ValueError):
        policy(**overrides)


@pytest.mark.parametrize("timestamp", [NOW.replace(tzinfo=None), 1, "2026-10-17T12:00:00+05:30"])
def test_invalid_maturity_timestamps(timestamp):
    with pytest.raises(ValueError):
        terms(maturity_at=timestamp)


def test_mismatched_context_time_is_rejected():
    with pytest.raises(ValueError):
        decide(flow=forecast().model_copy(update={"generated_at": NOW - timedelta(minutes=1)}))
