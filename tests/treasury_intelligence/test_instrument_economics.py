from datetime import datetime, timedelta
from decimal import Decimal, ROUND_DOWN, localcontext
import json
from pathlib import Path

import pytest

import treasury_intelligence as e

D = Decimal
ENTRY = datetime(2026, 1, 1, 17)
MATURITY = datetime(2026, 1, 2, 8)
ROOT = Path(__file__).parent / "fixtures"


def fixing(at=ENTRY, rate="5"):
    return e.AnnualRateFixing(observed_at=at, annual_rate_pct=rate)


def repo(*, principal=500_000_000, allowed=False, fee="0.5"):
    return e.Tier1RepoPosition(position_id="repo", principal_cents=principal,
        entered_at=ENTRY, matures_at=MATURITY, entry_apy_pct="5",
        early_break_allowed=allowed, early_break_fee_pct=fee,
        estimated_interest_cents=99999999)  # Deliberately ignored: not booked income.


def portfolio():
    request = e.FourTierRecommendationRequest.model_validate_json((ROOT / "four_tier_request.json").read_text())
    return request.portfolio


def round_trip(value):
    assert type(value).model_validate_json(value.model_dump_json()) == value
    assert json.loads(value.model_dump_json())["calculation_only"] is True


def test_actual_repo_maturity_and_fifteen_hour_interest():
    assert e.repo_maturity_at(ENTRY) == MATURITY
    result = e.calculate_repo_economics(repo(), as_of=MATURITY, rate_history=(fixing(),))
    assert result.holding_seconds == D("54000")
    # $5M * 5% * (15 / (365*24)) = $428.08219..., not a full-day $684.93.
    assert result.accrued_interest_cents == 42808
    assert result.gross_claim_cents == 500042808
    assert result.net_redemption_proceeds_cents == result.gross_claim_cents
    assert result.early_break_fee_cents == 0
    assert result.immediately_redeemable and result.matured
    round_trip(result)


def test_repo_stops_accruing_at_maturity():
    at_maturity = e.calculate_repo_economics(repo(), as_of=MATURITY, rate_history=(fixing(),))
    later = e.calculate_repo_economics(repo(), as_of=MATURITY + timedelta(days=1), rate_history=(fixing(),))
    assert later.accrued_interest_cents == at_maturity.accrued_interest_cents


def test_zero_principal_zero_quotes_and_zero_exposure():
    result = e.calculate_repo_economics(repo(principal=0), as_of=MATURITY, rate_history=())
    assert result.accrued_interest_cents == result.net_redemption_proceeds_cents == 0
    result = e.calculate_repo_economics(repo(), as_of=MATURITY, rate_history=(fixing(rate="0"),))
    assert result.accrued_interest_cents == 0
    risk = e.calculate_equity_risk(0, 0, current_price_index=D(1), peak_price_index=D(1), annual_volatility_pct=D(0))
    assert risk.exposure_fraction == risk.drawdown_fraction == D(0)


def test_repo_floating_rate_segments_and_single_final_rounding():
    rates = (fixing(rate="4.292"), fixing(ENTRY + timedelta(hours=7), "5.123456789"))
    result = e.calculate_repo_economics(repo(), as_of=MATURITY, rate_history=rates)
    expected = D(500000000) * (D("4.292") * 7 + D("5.123456789") * 8) / D(100 * 365 * 24)
    assert result.accrued_interest_cents == int(expected.to_integral_value(rounding="ROUND_HALF_UP"))
    assert result.accrued_interest_cents != e.calculate_repo_economics(repo(), as_of=MATURITY, rate_history=(rates[0],)).accrued_interest_cents
    # A fixing exactly at the end governs the next interval, not this one.
    result_end = e.calculate_repo_economics(repo(), as_of=MATURITY, rate_history=(*rates, fixing(MATURITY, "99")))
    assert result_end.accrued_interest_cents == result.accrued_interest_cents


def test_repo_lock_and_half_percent_early_break():
    cutoff = ENTRY + timedelta(hours=1)
    locked = e.calculate_repo_economics(repo(), as_of=cutoff, rate_history=(fixing(),))
    assert not locked.immediately_redeemable and locked.accessible_redemption_cents == 0
    permitted = e.calculate_repo_economics(repo(allowed=True), as_of=cutoff, rate_history=(fixing(),))
    assert permitted.early_break_fee_cents == 2_500_000
    assert permitted.interest_payable_on_redemption_cents == 0
    assert permitted.net_redemption_proceeds_cents == 497_500_000
    assert permitted.accessible_redemption_cents == permitted.net_redemption_proceeds_cents
    paid_interest = e.calculate_repo_economics(repo(allowed=True), as_of=cutoff, rate_history=(fixing(),),
        pay_accrued_interest_on_early_break=True)
    assert paid_interest.net_redemption_proceeds_cents == 497_500_000 + paid_interest.accrued_interest_cents


def test_repo_source_haircut_and_negative_rate():
    result = e.calculate_repo_economics(repo(principal=10000, allowed=True, fee="0.5123456789"),
        as_of=ENTRY, rate_history=())
    assert result.early_break_fee_cents == 52
    loss = e.calculate_repo_economics(repo(), as_of=MATURITY, rate_history=(fixing(rate="-1"),))
    assert loss.accrued_interest_cents == -8562
    assert loss.net_redemption_proceeds_cents < loss.principal_cents


def test_rate_source_observations_are_preserved():
    observations = tuple(e.OrganizerHourlyObservation.model_validate(r) for r in json.loads((ROOT / "organizer_hourly_series.json").read_text())[:2])
    rates = e.rate_fixings_from_observations(observations, instrument="repo")
    assert rates[0].annual_rate_pct == D("4.292")
    assert rates[0].observed_at == observations[0].timestamp
    overdraft = e.rate_fixings_from_observations(observations, instrument="overdraft")
    assert overdraft[0].annual_rate_pct == D("12.0")
    assert e.AnnualRateFixing.model_validate_json(rates[0].model_dump_json()) == rates[0]


@pytest.mark.parametrize("rates", [(), (fixing(ENTRY + timedelta(hours=1)),),
    (fixing(), fixing(ENTRY)), (fixing(ENTRY), fixing(ENTRY - timedelta(hours=1))),
    (fixing(), fixing(MATURITY + timedelta(hours=1)))])
def test_missing_unordered_duplicate_or_future_rates_rejected(rates):
    with pytest.raises(ValueError):
        e.calculate_repo_economics(repo(), as_of=MATURITY, rate_history=rates)


@pytest.mark.parametrize("timestamp", ["2026-01-01T17:00:00Z", "2026-01-01T17:00:00+05:30",
                                      "2026-01-01T16:00:00", "2026-01-01T17:00:01", 0])
def test_repo_entry_and_timestamp_semantics(timestamp):
    with pytest.raises(ValueError):
        e.repo_maturity_at(timestamp)


@pytest.mark.parametrize("price,pnl", [("110", 10000), ("90", -10000)])
def test_bond_observed_price_gain_and_loss(price, pnl):
    result = e.calculate_bond_economics(D("10"), D("100"), D(price), quoted_yield_pct=D("4.8"))
    assert result.cost_basis_cents == 100000
    assert result.unrealized_pnl_cents == pnl
    assert result.market_value_cents == 100000 + pnl
    assert result.liquidation_cost_cents == e.percentage_cost_cents(result.market_value_cents, D("2"))
    assert result.net_liquidation_proceeds_cents + result.liquidation_cost_cents == result.market_value_cents
    assert result.realized_pnl_if_sold_cents == result.net_liquidation_proceeds_cents - result.cost_basis_cents
    round_trip(result)


def test_bond_yield_quote_and_duration_not_added_to_mark():
    first = e.calculate_bond_economics(D(10), D(100), D(101), quoted_yield_pct=D("4.8"))
    second = e.calculate_bond_economics(D(10), D(100), D(101), quoted_yield_pct=D("99"))
    assert first.market_value_cents == second.market_value_cents == 101000
    assert first.unrealized_pnl_cents == second.unrealized_pnl_cents == 1000
    stress = e.calculate_duration_sensitivity(D("1.92"), previous_yield_pct=D("4.8"), current_yield_pct=D("5.8"))
    assert stress.yield_change_decimal == D("0.01")
    assert stress.estimated_price_change_fraction == D("-0.0192")
    assert stress.estimated_price_change_pct == D("-1.92")
    assert first.market_value_cents == 101000  # Stress never mutates or re-marks actual prices.
    round_trip(stress)


@pytest.mark.parametrize("new_yield,change", [("4.7", "0.00192"), ("4.9", "-0.00192"), ("4.8", "0")])
def test_duration_sign_and_percentage_point_conversion(new_yield, change):
    result = e.calculate_duration_sensitivity(D("1.92"), previous_yield_pct=D("4.8"), current_yield_pct=D(new_yield))
    assert result.estimated_price_change_fraction == D(change)


@pytest.mark.parametrize("price,pnl", [("5500", 50000), ("4500", -50000)])
def test_equity_price_driven_gain_and_loss(price, pnl):
    result = e.calculate_equity_economics(D(1), D(5000), D(price), annual_volatility_pct=D("18"))
    assert result.unrealized_pnl_cents == pnl
    assert result.realized_pnl_if_sold_cents == pnl
    assert result.liquidation_cost_cents == 0
    assert result.market_value_cents == 500000 + pnl
    round_trip(result)


def test_equity_emergency_fifteen_percent_slippage():
    result = e.calculate_equity_economics(D(1), D(5000), D(5000), annual_volatility_pct=D("18"), emergency_sale=True)
    assert result.market_value_cents == 500000
    assert result.liquidation_cost_cents == 75000
    assert result.net_liquidation_proceeds_cents == 425000
    assert result.realized_pnl_if_sold_cents == -75000


def test_equity_volatility_does_not_generate_income():
    low = e.calculate_equity_economics(D(1), D(5000), D(5000), annual_volatility_pct=D(0))
    high = e.calculate_equity_economics(D(1), D(5000), D(5000), annual_volatility_pct=D(100))
    assert low.unrealized_pnl_cents == high.unrealized_pnl_cents == 0
    assert low.market_value_cents == high.market_value_cents
    risk = e.calculate_equity_risk(250000, 1000000, current_price_index=D("75"),
        peak_price_index=D("100"), annual_volatility_pct=D("18.123456789"))
    assert risk.exposure_fraction == risk.drawdown_fraction == D("0.25")
    assert risk.annual_volatility_pct == D("18.123456789")
    round_trip(risk)


def test_index_quantity_notional_and_unspent_cash():
    result = e.calculate_index_acquisition(10000, D(3), unit_decimal_places=2)
    assert result.index_units == D("33.33")
    assert result.acquisition_notional_usd == D("99.99")
    assert result.cost_basis_cents == 9999 and result.unallocated_cents == 1
    assert result.cost_basis_cents + result.unallocated_cents == result.budget_cents
    round_trip(result)


def test_explicit_actual_cost_basis_and_zero_units():
    # Caller may supply actual acquisition fees/allocated lot basis separately.
    marked = e.calculate_bond_economics(D(10), D(100), D(101), quoted_yield_pct=D(5), cost_basis_cents=100500)
    assert marked.unrealized_pnl_cents == 500
    empty = e.calculate_equity_economics(D(0), D(100), D(99), annual_volatility_pct=D(18), emergency_sale=True)
    assert empty.market_value_cents == empty.realized_pnl_if_sold_cents == empty.liquidation_cost_cents == 0


def test_overdraft_actual_duration_cost_and_asset_conservation():
    # $1M * 12% * 15h / 8760h = $205.47945..., costs ceil to $205.48.
    result = e.calculate_overdraft_economics(0, draw_cents=100000000, start_at=ENTRY, end_at=MATURITY,
        rate_history=(fixing(rate="12"),))
    assert result.interval_financing_cost_cents == 20548
    assert result.closing_principal_cents == 100000000
    assert result.outstanding_liability_cents == 100020548
    assert result.net_cash_change_cents == 100000000
    assert result.net_portfolio_value_effect_cents == -20548
    assert result.net_cash_change_cents - result.net_liability_change_cents == -20548
    round_trip(result)


def test_overdraft_designated_repayments_no_interest_on_interest():
    result = e.calculate_overdraft_economics(100000, principal_repayment_cents=20000,
        accrued_financing_cost_cents=500, paid_financing_cost_cents=200,
        start_at=ENTRY, end_at=ENTRY + timedelta(days=365), rate_history=(fixing(rate="12"),))
    assert result.closing_principal_cents == 80000
    assert result.interval_financing_cost_cents == 9600
    assert result.unpaid_prior_financing_cost_cents == 300
    assert result.outstanding_liability_cents == 89900
    assert result.net_portfolio_value_effect_cents == -9600


def test_overdraft_zero_duration_and_floating_rate():
    zero = e.calculate_overdraft_economics(0, draw_cents=1000000, start_at=ENTRY, end_at=ENTRY, rate_history=())
    assert zero.net_portfolio_value_effect_cents == zero.interval_financing_cost_cents == 0
    assert zero.net_cash_change_cents == zero.net_liability_change_cents == 1000000
    changed = e.calculate_overdraft_economics(100000000, start_at=ENTRY, end_at=MATURITY,
        rate_history=(fixing(rate="12"), fixing(ENTRY + timedelta(hours=5), "24")))
    expected = D(100000000) * (D(12) * 5 + D(24) * 10) / D(100 * 8760)
    assert changed.interval_financing_cost_cents == int(expected.to_integral_value(rounding="ROUND_CEILING"))


def test_overdraft_rejects_future_fixings_and_financing_overpayment():
    with pytest.raises(ValueError):
        e.calculate_overdraft_economics(100, start_at=ENTRY, end_at=MATURITY,
            rate_history=(fixing(), fixing(MATURITY + timedelta(hours=1))))
    with pytest.raises(ValueError):
        e.calculate_overdraft_economics(100, accrued_financing_cost_cents=50, paid_financing_cost_cents=51,
            start_at=ENTRY, end_at=ENTRY, rate_history=())


def test_subsecond_duration_never_uses_float_seconds():
    result = e.calculate_overdraft_economics(1, start_at=ENTRY, end_at=ENTRY + timedelta(microseconds=1),
        rate_history=(fixing(rate="0.00000000001"),))
    assert result.interval_financing_cost_cents == 1  # Positive financing cost rounds up.


def test_portfolio_cash_market_value_liquidation_and_debt_are_distinct():
    state = portfolio()
    before = state.model_dump_json()
    result = e.calculate_portfolio_values(state, repo_rate_history=(fixing(),))
    assets = state.cash.available_cents + sum(p.principal_cents for p in state.repos)
    assets += sum(p.market_value_cents for p in (*state.bonds, *state.equities))
    assert result.gross_asset_value_cents == assets
    assert result.immediately_available_cash_cents == state.cash.available_cents
    assert result.cash_investment_yield_cents == 0
    assert result.gross_asset_value_cents > result.potential_liquidation_proceeds_cents
    assert result.potential_liquidation_proceeds_cents > result.immediately_available_cash_cents
    debt = state.overdraft.model_copy(update={"principal_cents": 1000000, "accrued_financing_cost_cents": 123})
    costs = e.CostBreakdown(market_loss_cents=100000, funding_cost_cents=123)
    updated = state.model_copy(update={"overdraft": debt, "realized_costs": costs})
    after = e.calculate_portfolio_values(updated, repo_rate_history=(fixing(),))
    assert after.gross_asset_value_cents == result.gross_asset_value_cents
    assert after.net_portfolio_value_cents == result.net_portfolio_value_cents - 1000123
    assert state.model_dump_json() == before
    round_trip(result)


def test_repo_settlement_once_preserves_assets_net_of_break_fee():
    state = portfolio()
    initial = e.calculate_portfolio_values(state, repo_rate_history=(fixing(),))
    redemption = e.calculate_repo_economics(state.repos[0], as_of=state.as_of, rate_history=(fixing(),))
    # Pure scenario construction only; actual settlement belongs to Member 2.
    settled = state.model_copy(update={"repos": (), "cash": e.Tier0CashPosition(
        available_cents=state.cash.available_cents + redemption.net_redemption_proceeds_cents)})
    closing = e.calculate_portfolio_values(settled)
    assert closing.gross_asset_value_cents == initial.gross_asset_value_cents - redemption.early_break_fee_cents


def test_borrowed_cash_and_principal_liability_cancel_in_portfolio_value():
    state = portfolio()
    before = e.calculate_portfolio_values(state, repo_rate_history=(fixing(),))
    liability = state.overdraft.model_copy(update={"principal_cents": 1000000})
    financed = state.model_copy(update={"overdraft": liability,
        "cash": e.Tier0CashPosition(available_cents=state.cash.available_cents + 1000000)})
    after = e.calculate_portfolio_values(financed, repo_rate_history=(fixing(),))
    assert after.gross_asset_value_cents == before.gross_asset_value_cents + 1000000
    assert after.net_portfolio_value_cents == before.net_portfolio_value_cents


def test_portfolio_locked_repo_not_added_to_cash_or_liquidation():
    state = portfolio()
    locked = state.repos[0].model_copy(update={"early_break_allowed": False})
    locked_state = state.model_copy(update={"repos": (locked,)})
    with_repo = e.calculate_portfolio_values(locked_state, repo_rate_history=(fixing(),))
    without = e.calculate_portfolio_values(state.model_copy(update={"repos": ()}))
    assert with_repo.immediately_available_cash_cents == without.immediately_available_cash_cents
    assert with_repo.potential_liquidation_proceeds_cents == without.potential_liquidation_proceeds_cents
    assert with_repo.gross_asset_value_cents == without.gross_asset_value_cents + locked.principal_cents


@pytest.mark.parametrize("amount,expected", [("0.005", 1), ("-0.005", -1), ("1.0049", 100), ("1.005", 101)])
def test_signed_cent_rounding(amount, expected):
    assert e.usd_to_ledger_cents(D(amount)) == expected


def test_haircut_rounding_and_negative_pnl_are_exact_cents():
    assert e.percentage_cost_cents(1, D("0.5")) == 1
    assert e.percentage_cost_cents(1, D(100)) == 1
    result = e.calculate_bond_economics(D(1), D("1.005"), D("0.995"), quoted_yield_pct=D(5))
    assert result.cost_basis_cents == 101 and result.market_value_cents == 100
    assert result.unrealized_pnl_cents == -1
    assert result.liquidation_cost_cents == 2


def test_decimal_precision_reproducibility_and_serialization():
    units, price = D("123456789.123456789"), D("99.123456789123456789")
    expected = e.calculate_bond_economics(units, D(100), price, quoted_yield_pct=D("4.123456789123456789"))
    with localcontext() as ctx:
        ctx.prec = 3
        ctx.rounding = ROUND_DOWN
        actual = e.calculate_bond_economics(units, D(100), price, quoted_yield_pct=D("4.123456789123456789"))
        interest = e.calculate_repo_economics(repo(), as_of=MATURITY, rate_history=(fixing(),))
    assert actual == expected
    assert interest.accrued_interest_cents == 42808
    assert json.loads(actual.model_dump_json())["current_price_index"] == str(price)


@pytest.mark.parametrize("invalid", [True, 1.1, "NaN", "Infinity"])
def test_reject_lossy_decimal_inputs(invalid):
    with pytest.raises(ValueError):
        e.usd_to_ledger_cents(invalid)
    with pytest.raises(ValueError):
        e.calculate_bond_economics(D(1), D(100), invalid, quoted_yield_pct=D(5))


def test_reject_invalid_financial_inputs():
    with pytest.raises(ValueError):
        e.percentage_cost_cents(-1, D(2))
    with pytest.raises(ValueError):
        e.percentage_cost_cents(100, D(101))
    with pytest.raises(ValueError):
        e.calculate_index_acquisition(100, D(0))
    with pytest.raises(ValueError):
        e.calculate_equity_risk(101, 100, current_price_index=D(1), peak_price_index=D(2), annual_volatility_pct=D(18))
    with pytest.raises(ValueError):
        e.calculate_equity_risk(0, 0, current_price_index=D(3), peak_price_index=D(2), annual_volatility_pct=D(18))
    with pytest.raises(ValueError):
        e.calculate_overdraft_economics(100, principal_repayment_cents=101, start_at=ENTRY, end_at=ENTRY, rate_history=())
    with pytest.raises(ValueError):
        e.calculate_overdraft_economics(100, start_at=ENTRY, end_at=MATURITY, rate_history=(fixing(rate="-1"),))
    with pytest.raises(ValueError):
        e.calculate_repo_economics(repo(), as_of=ENTRY - timedelta(seconds=1), rate_history=())
