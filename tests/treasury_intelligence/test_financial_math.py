from datetime import datetime, timedelta, timezone
from decimal import localcontext

import pytest

import treasury_intelligence as e

NOW = datetime(2026, 10, 17, 12, tzinfo=timezone.utc)
MILLION = 100_000_000  # $1M in cents


def path(*flows, uncertainty=0):
    return e.ForecastResult(generated_at=NOW, model_version="test", points=tuple(
        e.ForecastPoint(start_at=NOW + timedelta(hours=i),
                        end_at=NOW + timedelta(hours=i + 1),
                        inflow_cents=inflow, outflow_cents=outflow,
                        uncertainty_cents=uncertainty)
        for i, (inflow, outflow) in enumerate(flows)
    ))


def context(balance=10 * MILLION, withdrawable=0):
    return e.TreasuryContext(as_of=NOW, currency="USD", checking_balance_cents=2 * MILLION,
        vaults=(e.VaultPosition(vault_id="locked", balance_cents=balance,
                withdrawable_cents=withdrawable, annual_yield_bps=500,
                withdrawal_delay_minutes=1440),))


def maturity(minutes, amount=8 * MILLION, **kwargs):
    return e.VaultMaturity(vault_id="locked", available_at=NOW + timedelta(minutes=minutes),
                           amount_cents=amount, **kwargs)


def test_withdrawal_before_matching_inflow():
    forecast = path((0, 8 * MILLION), (8 * MILLION, 0))
    assert e.maximum_cumulative_shortfall(forecast) == 8 * MILLION
    # Opposite ordering requires no opening reserve.
    assert e.maximum_cumulative_shortfall(path((8 * MILLION, 0), (0, 8 * MILLION))) == 0


def test_within_bucket_timing_is_conservative():
    assert e.maximum_cumulative_shortfall(path((8 * MILLION, 8 * MILLION))) == 8 * MILLION


def test_fourteen_million_reserve():
    result = e.reserve_for_path(path((0, 12_500_000_00)),
        uncertainty_buffer_cents=MILLION, operational_buffer_cents=MILLION // 2)
    assert result.net_drain_cents == 12_500_000_00
    assert result.required_reserve_cents == 14 * MILLION
    assert e.ReserveResult.model_validate_json(result.model_dump_json()) == result


@pytest.mark.parametrize("flows", [((0, 0),), ((100, 0),), ((100, 0), (0, 50))])
def test_nonnegative_zero_reserve(flows):
    result = e.reserve_for_path(path(*flows), uncertainty_buffer_cents=0, operational_buffer_cents=0)
    assert result.required_reserve_cents == 0


def test_frozen_reserve_api_rounds_up_and_uses_path():
    policy = e.TreasuryPolicy(base_buffer_cents=50, uncertainty_multiplier_bps=1,
        tolerance_bps=0, min_transfer_cents=0, max_allocation_bps=10000)
    result = e.calculate_required_reserve(path((0, 100), (100, 0), uncertainty=1), policy)
    assert result.required_reserve_cents == 151
    assert result.uncertainty_buffer_cents == 1


@pytest.mark.parametrize("arrival,expected", [(0, 0), (60, 0), (61, 8 * MILLION), (180, 8 * MILLION)])
def test_settlement_arrival_timing(arrival, expected):
    forecast = path((0, 0), (0, 8 * MILLION))
    assert e.maximum_cumulative_shortfall(forecast, context=context(), maturities=[maturity(arrival)]) == expected


def test_settlement_cannot_erase_prior_peak():
    forecast = path((0, 8 * MILLION), (0, 0))
    assert e.maximum_cumulative_shortfall(forecast, context=context(), maturities=[maturity(60)]) == 8 * MILLION


def test_locked_and_withdrawable_balances_are_not_automatic_cash():
    forecast = path((0, 8 * MILLION))
    for withdrawable in (0, 10 * MILLION):
        assert e.maximum_cumulative_shortfall(forecast, context=context(withdrawable=withdrawable)) == 8 * MILLION


def test_booked_maturity_is_not_counted_again():
    booked = maturity(0, already_in_checking=True)
    assert e.VaultMaturity.model_validate_json(booked.model_dump_json()) == booked
    assert e.known_vault_maturities(context(), [booked]) == ()
    assert e.maximum_cumulative_shortfall(path((0, 8 * MILLION)), context=context(), maturities=[booked]) == 8 * MILLION
    with pytest.raises(ValueError, match="duplicate"):
        e.known_vault_maturities(context(), [booked, maturity(60)])


@pytest.mark.parametrize("schedule", [
    [maturity(-1)], [maturity(60, amount=11 * MILLION)],
    [maturity(60, already_in_checking=True)],
    [e.VaultMaturity(vault_id="unknown", available_at=NOW, amount_cents=1)],
])
def test_invalid_maturity_schedule(schedule):
    with pytest.raises(ValueError):
        e.known_vault_maturities(context(), schedule)


def test_maturity_requires_context_and_matching_time():
    forecast = path((0, 1))
    with pytest.raises(ValueError):
        e.maximum_cumulative_shortfall(forecast, maturities=[maturity(0)])
    with pytest.raises(ValueError):
        e.maximum_cumulative_shortfall(forecast, context=context().model_copy(update={"as_of": NOW + timedelta(minutes=1)}))


@pytest.mark.parametrize("timestamp", [NOW.replace(tzinfo=None), "2026-10-17T12:00:00+05:30", 1])
def test_maturity_timestamp_validation(timestamp):
    with pytest.raises(ValueError):
        e.VaultMaturity(vault_id="locked", available_at=timestamp, amount_cents=1)


def test_surplus_does_not_add_vault_cash():
    assert e.candidate_deployable_surplus(20 * MILLION, 14 * MILLION) == 6 * MILLION
    assert e.candidate_deployable_surplus(10, 20) == 0


def test_five_million_one_day_interest():
    assert e.simple_annualized_vault_yield(5 * MILLION, 500, holding_minutes=1440) == 68493
    assert e.simple_annualized_vault_yield(5 * MILLION, 500, holding_minutes=365 * 1440) == 25_000_000


def test_interest_rounding_zero_and_decimal_context_independence():
    assert e.simple_annualized_vault_yield(1, 5000, holding_minutes=365 * 1440) == 1
    assert e.simple_annualized_vault_yield(0, 500, holding_minutes=1440) == 0
    assert e.simple_annualized_vault_yield(MILLION, 500, holding_minutes=0) == 0
    with localcontext() as ctx:
        ctx.prec = 2
        assert e.simple_annualized_vault_yield(5 * MILLION, 500, holding_minutes=1440) == 68493


def test_penalties():
    assert e.early_redemption_penalty(MILLION, 25, early_redemption=True, fixed_fee_cents=100) == 250100
    assert e.early_redemption_penalty(1, 1, early_redemption=True) == 1
    assert e.early_redemption_penalty(MILLION, 25, early_redemption=False, fixed_fee_cents=100) == 0
    assert e.early_redemption_penalty(0, 25, early_redemption=True, fixed_fee_cents=100) == 0


def test_expected_net_benefit_can_be_negative():
    assert e.expected_net_economic_benefit(68493, penalty_cents=10000,
        transaction_cost_cents=500, opportunity_cost_cents=1000) == 56993
    assert e.expected_net_economic_benefit(100, penalty_cents=200) == -100


@pytest.mark.parametrize("invalid", [-1, True, 1.5, "10"])
def test_invalid_money(invalid):
    with pytest.raises(ValueError):
        e.candidate_deployable_surplus(invalid, 0)
    with pytest.raises(ValueError):
        e.simple_annualized_vault_yield(invalid, 500, holding_minutes=1)
    with pytest.raises(ValueError):
        e.early_redemption_penalty(invalid, 10, early_redemption=True)
    with pytest.raises(ValueError):
        e.expected_net_economic_benefit(0, penalty_cents=invalid)
    with pytest.raises(ValueError):
        e.reserve_for_path(path((0, 0)), uncertainty_buffer_cents=invalid, operational_buffer_cents=0)


def test_invalid_rates_durations_and_flags():
    with pytest.raises(ValueError):
        e.simple_annualized_vault_yield(100, 10001, holding_minutes=1)
    with pytest.raises(ValueError):
        e.simple_annualized_vault_yield(100, 500, holding_minutes=-1)
    with pytest.raises(ValueError):
        e.early_redemption_penalty(100, 1, early_redemption=1)
