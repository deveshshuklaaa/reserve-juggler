"""Expected simple economics, not realized returns or execution."""
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP, localcontext

from .reserve import nonnegative_integer


def _rate(value: int) -> int:
    nonnegative_integer(value, "rate_bps")
    if value > 10_000:
        raise ValueError("rate_bps must not exceed 10000")
    return value


def simple_annualized_vault_yield(
    principal_cents: int, annual_yield_bps: int, *, holding_minutes: int,
) -> int:
    """Expected simple interest, ACT/365 fixed, rounded half up to cents."""
    nonnegative_integer(principal_cents, "principal_cents")
    _rate(annual_yield_bps)
    nonnegative_integer(holding_minutes, "holding_minutes")
    product = principal_cents * annual_yield_bps * holding_minutes
    with localcontext() as ctx:
        ctx.prec = max(28, len(str(product)) + 10)
        interest = Decimal(product) / Decimal(10_000 * 365 * 24 * 60)
        return int(interest.to_integral_value(rounding=ROUND_HALF_UP))


def early_redemption_penalty(
    redeemed_principal_cents: int, penalty_bps: int, *,
    early_redemption: bool, fixed_fee_cents: int = 0,
) -> int:
    """Explicit contractual principal haircut plus fee; ceil costs to a cent.

    No fee for a zero redemption or a redemption at/after maturity. This helper
    does not assume a product permits early redemption at all.
    """
    nonnegative_integer(redeemed_principal_cents, "redeemed_principal_cents")
    _rate(penalty_bps)
    nonnegative_integer(fixed_fee_cents, "fixed_fee_cents")
    if type(early_redemption) is not bool:
        raise ValueError("early_redemption must be boolean")
    if not early_redemption or redeemed_principal_cents == 0:
        return 0
    product = redeemed_principal_cents * penalty_bps
    with localcontext() as ctx:
        ctx.prec = max(28, len(str(product)) + 10)
        haircut = int((Decimal(product) / Decimal(10_000)).to_integral_value(rounding=ROUND_CEILING))
    return haircut + fixed_fee_cents


def expected_net_economic_benefit(
    expected_yield_cents: int, *, penalty_cents: int = 0,
    transaction_cost_cents: int = 0, opportunity_cost_cents: int = 0,
) -> int:
    """Signed expected benefit from rounded monetary components; may be negative."""
    values = (expected_yield_cents, penalty_cents, transaction_cost_cents, opportunity_cost_cents)
    for name, value in zip(("expected_yield_cents", "penalty_cents", "transaction_cost_cents", "opportunity_cost_cents"), values):
        nonnegative_integer(value, name)
    with localcontext() as ctx:
        ctx.prec = max(28, max(len(str(v)) for v in values) + 10)
        return int(Decimal(expected_yield_cents) - Decimal(penalty_cents)
                   - Decimal(transaction_cost_cents) - Decimal(opportunity_cost_cents))
