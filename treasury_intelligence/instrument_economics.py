"""Pure four-tier economics. No trading, booking, or assumed future observations."""
from collections.abc import Sequence
from datetime import datetime, time, timedelta
from decimal import Decimal, ROUND_CEILING, ROUND_DOWN, ROUND_HALF_UP, localcontext
from typing import Literal

from pydantic import StrictBool, StrictInt, TypeAdapter, field_validator

from .four_tier import (
    ExactDecimal, FourTierContract, FourTierPortfolioState, Fraction, LocalTimestamp,
    NonnegativeDecimal, OrganizerHourlyObservation, Percent, PositiveDecimal, Tier1RepoPosition,
)
from .reserve import nonnegative_integer
from .types import Cents, Name


def _dec(value, *, minimum=None, maximum=None) -> Decimal:
    result = TypeAdapter(ExactDecimal).validate_python(value)
    if (minimum is not None and result < minimum) or (maximum is not None and result > maximum):
        raise ValueError("decimal input outside allowed bounds")
    return result


def _precision(*values) -> int:
    # Include coefficient and exponent widths, independent of the caller's context.
    return max(80, 40 + sum(len(Decimal(v).as_tuple().digits) + abs(Decimal(v).as_tuple().exponent) for v in values))


def _time(value) -> datetime:
    return TypeAdapter(LocalTimestamp).validate_python(value)


def _microseconds(start, end) -> int:
    start, end = _time(start), _time(end)
    if end < start:
        raise ValueError("end must not precede start")
    delta = end - start
    return (delta.days * 86400 + delta.seconds) * 1_000_000 + delta.microseconds


class EconomicsResult(FourTierContract):
    calculation_only: Literal[True] = True

    @field_validator("calculation_only", mode="before")
    @classmethod
    def calculation_flag(cls, value):
        if value is not True:
            raise ValueError("pure calculation results cannot be execution receipts")
        return value


class AnnualRateFixing(FourTierContract):
    observed_at: LocalTimestamp
    annual_rate_pct: ExactDecimal


def rate_fixings_from_observations(
    observations: Sequence[OrganizerHourlyObservation], *, instrument: Literal["repo", "overdraft"],
) -> tuple[AnnualRateFixing, ...]:
    if instrument not in ("repo", "overdraft"):
        raise ValueError("instrument must be repo or overdraft")
    return tuple(AnnualRateFixing(observed_at=o.timestamp, annual_rate_pct=(
        o.tier1_repo_rate_apy if instrument == "repo" else o.emergency_overdraft_penalty_apr_pct
    )) for o in observations)


def usd_to_ledger_cents(amount_usd: Decimal) -> int:
    """Signed USD to integer cents, half away from zero (ROUND_HALF_UP)."""
    value = _dec(amount_usd)
    with localcontext() as ctx:
        ctx.prec = _precision(value)
        return int((value * 100).to_integral_value(rounding=ROUND_HALF_UP))


def percentage_cost_cents(amount_cents: int, percentage: Decimal) -> int:
    """Nonnegative haircut/cost, rounded upward once, never beyond principal."""
    nonnegative_integer(amount_cents, "amount_cents")
    percentage = _dec(percentage, minimum=0, maximum=100)
    with localcontext() as ctx:
        ctx.prec = _precision(amount_cents, percentage)
        return int((Decimal(amount_cents) * percentage / 100).to_integral_value(rounding=ROUND_CEILING))


def repo_maturity_at(entered_at: datetime) -> datetime:
    entered_at = _time(entered_at)
    if entered_at.time() != time(17):
        raise ValueError("repo entry must be exactly 17:00")
    return entered_at + timedelta(hours=15)


def _floating_interest(principal_cents, start_at, end_at, rate_history, *, cutoff, cost=False):
    """Left-continuous fixes valid from observed_at, simple ACT/365 fixed."""
    nonnegative_integer(principal_cents, "principal_cents")
    _microseconds(start_at, end_at)
    if any(not isinstance(r, AnnualRateFixing) for r in rate_history):
        raise ValueError("rate history requires AnnualRateFixing values")
    if any(b.observed_at <= a.observed_at for a, b in zip(rate_history, rate_history[1:])):
        raise ValueError("rate history must be strictly ordered and unique")
    if any(r.observed_at > cutoff for r in rate_history):
        raise ValueError("future rate observations are forbidden")
    if cost and any(r.annual_rate_pct < 0 for r in rate_history):
        raise ValueError("financing APR cannot be negative")
    if start_at == end_at or principal_cents == 0:
        return 0
    previous = [r for r in rate_history if r.observed_at <= start_at]
    if not previous:
        raise ValueError("rate history must cover the interval start")
    active = previous[-1].annual_rate_pct
    cursor = start_at
    weighted = []
    for fixing in rate_history:
        if start_at < fixing.observed_at < end_at:
            weighted.append((active, _microseconds(cursor, fixing.observed_at)))
            active, cursor = fixing.annual_rate_pct, fixing.observed_at
    weighted.append((active, _microseconds(cursor, end_at)))
    with localcontext() as ctx:
        ctx.prec = _precision(principal_cents, *(r for r, _ in weighted)) + len(str(len(weighted)))
        numerator = sum((rate * micros for rate, micros in weighted), Decimal(0)) * principal_cents
        # Source quotes are percentage points; no compounding and no per-hour rounding.
        interest = numerator / Decimal(100 * 365 * 86400 * 1_000_000)
        return int(interest.to_integral_value(rounding=ROUND_CEILING if cost else ROUND_HALF_UP))


class RepoEconomicsResult(EconomicsResult):
    position_id: Name
    as_of: LocalTimestamp
    matures_at: LocalTimestamp
    holding_seconds: NonnegativeDecimal
    principal_cents: Cents
    accrued_interest_cents: StrictInt
    gross_claim_cents: Cents
    interest_payable_on_redemption_cents: StrictInt
    early_break_fee_cents: Cents
    net_redemption_proceeds_cents: Cents
    immediately_redeemable: StrictBool
    accessible_redemption_cents: Cents
    matured: StrictBool


def calculate_repo_economics(
    position: Tier1RepoPosition, *, as_of: datetime,
    rate_history: Sequence[AnnualRateFixing], pay_accrued_interest_on_early_break: bool = False,
) -> RepoEconomicsResult:
    as_of = _time(as_of)
    if as_of < position.entered_at:
        raise ValueError("position has not entered yet")
    if type(pay_accrued_interest_on_early_break) is not bool:
        raise ValueError("early-break interest permission must be boolean")
    end = min(as_of, position.matures_at)
    interest = _floating_interest(position.principal_cents, position.entered_at, end, rate_history, cutoff=as_of)
    matured = as_of >= position.matures_at
    payable = interest if matured or pay_accrued_interest_on_early_break else min(interest, 0)
    fee = 0 if matured else percentage_cost_cents(position.principal_cents, position.early_break_fee_pct)
    net = position.principal_cents + payable - fee
    claim = position.principal_cents + interest
    if min(net, claim) < 0:
        raise ValueError("supplied rates/costs imply a negative repo claim or proceeds")
    accessible = matured or position.early_break_allowed
    with localcontext() as ctx:
        ctx.prec = 40
        seconds = Decimal(_microseconds(position.entered_at, end)) / 1_000_000
    return RepoEconomicsResult(position_id=position.position_id, as_of=as_of,
        matures_at=position.matures_at, holding_seconds=seconds, principal_cents=position.principal_cents,
        accrued_interest_cents=interest, gross_claim_cents=claim, interest_payable_on_redemption_cents=payable,
        early_break_fee_cents=fee, net_redemption_proceeds_cents=net,
        immediately_redeemable=accessible, accessible_redemption_cents=net if accessible else 0, matured=matured)


class MarketEconomicsResult(EconomicsResult):
    instrument: Literal["TIER2_BOND", "TIER3_EQUITY"]
    index_units: NonnegativeDecimal
    acquisition_price_index: PositiveDecimal
    current_price_index: PositiveDecimal
    acquisition_notional_usd: NonnegativeDecimal
    market_value_usd: NonnegativeDecimal
    cost_basis_cents: Cents
    market_value_cents: Cents
    unrealized_pnl_cents: StrictInt
    liquidation_haircut_pct: Percent
    liquidation_cost_cents: Cents
    net_liquidation_proceeds_cents: Cents
    realized_pnl_if_sold_cents: StrictInt
    quoted_yield_pct: ExactDecimal | None = None
    annual_volatility_pct: NonnegativeDecimal | None = None


class IndexAcquisitionResult(EconomicsResult):
    budget_cents: Cents
    acquisition_price_index: PositiveDecimal
    index_units: NonnegativeDecimal
    acquisition_notional_usd: NonnegativeDecimal
    cost_basis_cents: Cents
    unallocated_cents: Cents


def calculate_index_acquisition(budget_cents: int, acquisition_price_index: Decimal, *,
                                 unit_decimal_places: int = 18) -> IndexAcquisitionResult:
    """Normalized units rounded down to a declared precision, leaving residual cash."""
    nonnegative_integer(budget_cents, "budget_cents")
    nonnegative_integer(unit_decimal_places, "unit_decimal_places")
    if unit_decimal_places > 1000:
        raise ValueError("unit precision must not exceed 1000 decimal places")
    price = _dec(acquisition_price_index, minimum=0)
    if not price:
        raise ValueError("acquisition price must be positive")
    with localcontext() as ctx:
        ctx.prec = _precision(budget_cents, price) + unit_decimal_places
        quantum = Decimal(1).scaleb(-unit_decimal_places)
        units = (Decimal(budget_cents) / 100 / price).quantize(quantum, rounding=ROUND_DOWN)
        notional = units * price
    basis = usd_to_ledger_cents(notional)
    return IndexAcquisitionResult(budget_cents=budget_cents, acquisition_price_index=price,
        index_units=units, acquisition_notional_usd=notional, cost_basis_cents=basis,
        unallocated_cents=budget_cents - basis)


def _market_economics(instrument, index_units, acquisition_price_index, current_price_index,
                      haircut_pct, cost_basis_cents, quoted_yield_pct=None, annual_volatility_pct=None):
    units = _dec(index_units, minimum=0)
    acquisition = _dec(acquisition_price_index, minimum=0)
    current = _dec(current_price_index, minimum=0)
    if not acquisition or not current:
        raise ValueError("price indices must be positive")
    haircut = _dec(haircut_pct, minimum=0, maximum=100)
    with localcontext() as ctx:
        ctx.prec = _precision(units, acquisition, current)
        notional, value = units * acquisition, units * current
    basis = usd_to_ledger_cents(notional) if cost_basis_cents is None else nonnegative_integer(cost_basis_cents, "cost_basis_cents")
    marked = usd_to_ledger_cents(value)
    fee = percentage_cost_cents(marked, haircut)
    return MarketEconomicsResult(instrument=instrument, index_units=units,
        acquisition_price_index=acquisition, current_price_index=current, acquisition_notional_usd=notional,
        market_value_usd=value, cost_basis_cents=basis, market_value_cents=marked,
        unrealized_pnl_cents=marked - basis, liquidation_haircut_pct=haircut,
        liquidation_cost_cents=fee, net_liquidation_proceeds_cents=marked - fee,
        realized_pnl_if_sold_cents=marked - fee - basis,
        quoted_yield_pct=quoted_yield_pct, annual_volatility_pct=annual_volatility_pct)


def calculate_bond_economics(index_units: Decimal, acquisition_price_index: Decimal,
                             current_price_index: Decimal, *, quoted_yield_pct: Decimal,
                             liquidation_haircut_pct: Decimal = Decimal("2"),
                             cost_basis_cents: int | None = None) -> MarketEconomicsResult:
    """Observed-index valuation; YTM is metadata, never an added coupon."""
    return _market_economics("TIER2_BOND", index_units, acquisition_price_index, current_price_index,
        liquidation_haircut_pct, cost_basis_cents, quoted_yield_pct=_dec(quoted_yield_pct))


def calculate_equity_economics(index_units: Decimal, acquisition_price_index: Decimal,
                               current_price_index: Decimal, *, annual_volatility_pct: Decimal,
                               emergency_sale: bool = False, slippage_pct: Decimal = Decimal("15"),
                               cost_basis_cents: int | None = None) -> MarketEconomicsResult:
    """Price-only P&L; no assumed annual expected return is booked."""
    if type(emergency_sale) is not bool:
        raise ValueError("emergency_sale must be boolean")
    slippage = _dec(slippage_pct, minimum=0, maximum=100)
    return _market_economics("TIER3_EQUITY", index_units, acquisition_price_index, current_price_index,
        slippage if emergency_sale else Decimal(0), cost_basis_cents,
        annual_volatility_pct=_dec(annual_volatility_pct, minimum=0))


class DurationSensitivityResult(EconomicsResult):
    modified_duration_years: NonnegativeDecimal
    yield_change_decimal: ExactDecimal
    estimated_price_change_fraction: ExactDecimal
    estimated_price_change_pct: ExactDecimal


def calculate_duration_sensitivity(modified_duration_years: Decimal, *, previous_yield_pct: Decimal,
                                   current_yield_pct: Decimal) -> DurationSensitivityResult:
    duration = _dec(modified_duration_years, minimum=0)
    previous, current = _dec(previous_yield_pct), _dec(current_yield_pct)
    with localcontext() as ctx:
        ctx.prec = _precision(duration, previous, current)
        delta = (current - previous) / 100
        change = -duration * delta
        return DurationSensitivityResult(modified_duration_years=duration, yield_change_decimal=delta,
            estimated_price_change_fraction=change, estimated_price_change_pct=change * 100)


class EquityRiskResult(EconomicsResult):
    exposure_fraction: Fraction
    drawdown_fraction: Fraction
    annual_volatility_pct: NonnegativeDecimal


def calculate_equity_risk(market_value_cents: int, gross_asset_value_cents: int, *,
                          current_price_index: Decimal, peak_price_index: Decimal,
                          annual_volatility_pct: Decimal) -> EquityRiskResult:
    nonnegative_integer(market_value_cents, "market_value_cents")
    nonnegative_integer(gross_asset_value_cents, "gross_asset_value_cents")
    if market_value_cents > gross_asset_value_cents:
        raise ValueError("equity value exceeds gross assets")
    current, peak = _dec(current_price_index, minimum=0), _dec(peak_price_index, minimum=0)
    if not peak or not current or current > peak:
        raise ValueError("positive running peak must be at least current price")
    with localcontext() as ctx:
        ctx.prec = _precision(current, peak, market_value_cents, gross_asset_value_cents)
        return EquityRiskResult(exposure_fraction=Decimal(market_value_cents) / gross_asset_value_cents if gross_asset_value_cents else Decimal(0),
            drawdown_fraction=(peak - current) / peak, annual_volatility_pct=_dec(annual_volatility_pct, minimum=0))


class OverdraftEconomicsResult(EconomicsResult):
    closing_principal_cents: Cents
    unpaid_prior_financing_cost_cents: Cents
    interval_financing_cost_cents: Cents
    outstanding_liability_cents: Cents
    net_cash_change_cents: StrictInt
    net_liability_change_cents: StrictInt
    net_portfolio_value_effect_cents: StrictInt


def calculate_overdraft_economics(principal_cents: int, *, start_at: datetime, end_at: datetime,
                                  rate_history: Sequence[AnnualRateFixing], draw_cents: int = 0,
                                  principal_repayment_cents: int = 0,
                                  accrued_financing_cost_cents: int = 0,
                                  paid_financing_cost_cents: int = 0) -> OverdraftEconomicsResult:
    """All designated principal/cost payments occur at interval start; simple APR.

    For intrainterval principal changes, call on separate constant-principal intervals.
    No interest-on-interest; principal repayment is distinct from paying finance costs.
    """
    for name, value in (("principal_cents", principal_cents), ("draw_cents", draw_cents),
                        ("principal_repayment_cents", principal_repayment_cents),
                        ("accrued_financing_cost_cents", accrued_financing_cost_cents),
                        ("paid_financing_cost_cents", paid_financing_cost_cents)):
        nonnegative_integer(value, name)
    start, end = _time(start_at), _time(end_at)
    closing = principal_cents + draw_cents - principal_repayment_cents
    prior = accrued_financing_cost_cents - paid_financing_cost_cents
    if min(closing, prior) < 0:
        raise ValueError("repayment exceeds designated outstanding principal or accrued cost")
    charge = _floating_interest(closing, start, end, rate_history, cutoff=end, cost=True)
    liability = closing + prior + charge
    cash_change = draw_cents - principal_repayment_cents - paid_financing_cost_cents
    liability_change = liability - principal_cents - accrued_financing_cost_cents
    return OverdraftEconomicsResult(closing_principal_cents=closing, unpaid_prior_financing_cost_cents=prior,
        interval_financing_cost_cents=charge, outstanding_liability_cents=liability,
        net_cash_change_cents=cash_change, net_liability_change_cents=liability_change,
        net_portfolio_value_effect_cents=cash_change - liability_change)


class PortfolioValueResult(EconomicsResult):
    immediately_available_cash_cents: Cents
    cash_investment_yield_cents: Literal[0] = 0
    repo_gross_claim_cents: Cents
    bond_market_value_cents: Cents
    equity_market_value_cents: Cents
    gross_asset_value_cents: Cents
    potential_liquidation_proceeds_cents: Cents
    outstanding_liability_cents: Cents
    net_portfolio_value_cents: StrictInt
    net_liquidation_value_cents: StrictInt


def calculate_portfolio_values(portfolio: FourTierPortfolioState, *,
                                repo_rate_history: Sequence[AnnualRateFixing] = (),
                                pay_accrued_interest_on_early_break: bool = False) -> PortfolioValueResult:
    """Snapshot only. Settled repos must already be removed by Member 2.

    Modeled accrued repo interest is a claim, not checking liquidity. Recorded
    realized costs and price P&L are already in the snapshot; never subtract again.
    Potential liquidation includes immediate repo redemption and haircut market
    sales, but is not an assertion that those trades have settled into cash.
    """
    repos = [calculate_repo_economics(p, as_of=portfolio.as_of, rate_history=repo_rate_history,
        pay_accrued_interest_on_early_break=pay_accrued_interest_on_early_break) for p in portfolio.repos]
    bond_value = sum(p.market_value_cents for p in portfolio.bonds)
    equity_value = sum(p.market_value_cents for p in portfolio.equities)
    claims = sum(p.gross_claim_cents for p in repos)
    gross = portfolio.cash.available_cents + claims + bond_value + equity_value
    liquidation = portfolio.cash.available_cents + sum(p.accessible_redemption_cents for p in repos)
    liquidation += sum(p.market_value_cents - percentage_cost_cents(p.market_value_cents, p.liquidation_haircut_pct) for p in portfolio.bonds)
    liquidation += sum(p.market_value_cents - percentage_cost_cents(p.market_value_cents, p.emergency_sale_slippage_pct) for p in portfolio.equities)
    debt = portfolio.overdraft.principal_cents + portfolio.overdraft.accrued_financing_cost_cents
    return PortfolioValueResult(immediately_available_cash_cents=portfolio.cash.available_cents,
        repo_gross_claim_cents=claims, bond_market_value_cents=bond_value, equity_market_value_cents=equity_value,
        gross_asset_value_cents=gross, potential_liquidation_proceeds_cents=liquidation,
        outstanding_liability_cents=debt, net_portfolio_value_cents=gross - debt,
        net_liquidation_value_cents=liquidation - debt)
