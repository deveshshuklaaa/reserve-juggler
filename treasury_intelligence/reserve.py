"""Pure pathwise liquidity mathematics; all amounts are integer cents."""
from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal, ROUND_CEILING, localcontext

from pydantic import StrictBool, field_validator

from .types import Cents, Contract, ForecastResult, Name, ReserveResult, TreasuryContext, TreasuryPolicy


def nonnegative_integer(value: int, name: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")
    return value


class VaultMaturity(Contract):
    """Caller-attested contractual settlement, separate from forecast inflows."""
    vault_id: Name
    available_at: datetime
    amount_cents: Cents
    already_in_checking: StrictBool = False

    @field_validator("available_at", mode="before")
    @classmethod
    def explicit_timestamp(cls, value):
        if not isinstance(value, (str, datetime)):
            raise ValueError("available_at requires an ISO 8601 string or datetime")
        return value


def known_vault_maturities(
    context: TreasuryContext, maturities: Sequence[VaultMaturity],
) -> tuple[VaultMaturity, ...]:
    """Validate a single principal settlement per vault, excluding booked cash.

    An explicit schedule is required: neither balance nor withdrawable balance
    implies automatic settlement. Unbooked settlements cannot predate the context.
    """
    vaults = {v.vault_id: v for v in context.vaults}
    seen = set()
    pending = []
    for maturity in maturities:
        if not isinstance(maturity, VaultMaturity):
            raise ValueError("maturities must contain VaultMaturity values")
        if maturity.vault_id in seen:
            raise ValueError("duplicate vault settlement")
        seen.add(maturity.vault_id)
        if maturity.vault_id not in vaults:
            raise ValueError("settlement references an unknown vault")
        if maturity.already_in_checking:
            if maturity.available_at > context.as_of:
                raise ValueError("future settlement cannot already be in checking")
            continue
        if maturity.available_at < context.as_of:
            raise ValueError("past settlement must be reconciled into checking")
        if maturity.amount_cents > vaults[maturity.vault_id].balance_cents:
            raise ValueError("settlement exceeds vault principal balance")
        pending.append(maturity)
    return tuple(sorted(pending, key=lambda m: (m.available_at, m.vault_id)))


def maximum_cumulative_shortfall(
    forecast: ForecastResult, *, context: TreasuryContext | None = None,
    maturities: Sequence[VaultMaturity] = (),
) -> int:
    """Peak funding needed from zero opening cash; not an end-of-path net drain.

    Bucket outflows occur at start, inflows at end. Available settlements at
    the same instant are credited before withdrawals. Opening checking is
    deliberately excluded; it is compared with the reserve separately.
    """
    if context is not None and context.as_of != forecast.generated_at:
        raise ValueError("context and forecast timestamps must match")
    if maturities and context is None:
        raise ValueError("maturity schedules require a treasury context")
    settlements = known_vault_maturities(context, maturities) if context is not None else ()
    # Each timestamp stores credits and debits. Use integer sums: no money drift.
    events: dict[datetime, list[int]] = {}
    for point in forecast.points:
        events.setdefault(point.start_at, [0, 0])[1] += point.outflow_cents
        events.setdefault(point.end_at, [0, 0])[0] += point.inflow_cents
    end_at = forecast.points[-1].end_at
    for maturity in settlements:
        if maturity.available_at <= end_at:
            events.setdefault(maturity.available_at, [0, 0])[0] += maturity.amount_cents
    running_cash = peak = 0
    for _, (credits, debits) in sorted(events.items()):
        running_cash += credits - debits
        peak = max(peak, -running_cash)
    return peak


def reserve_for_path(
    forecast: ForecastResult, *, uncertainty_buffer_cents: int,
    operational_buffer_cents: int, context: TreasuryContext | None = None,
    maturities: Sequence[VaultMaturity] = (),
) -> ReserveResult:
    """Combine peak shortfall with explicitly supplied, already calibrated buffers."""
    nonnegative_integer(uncertainty_buffer_cents, "uncertainty_buffer_cents")
    nonnegative_integer(operational_buffer_cents, "operational_buffer_cents")
    peak = maximum_cumulative_shortfall(forecast, context=context, maturities=maturities)
    return ReserveResult(
        as_of=forecast.generated_at, net_drain_cents=peak,
        uncertainty_buffer_cents=uncertainty_buffer_cents,
        base_buffer_cents=operational_buffer_cents,
        required_reserve_cents=peak + uncertainty_buffer_cents + operational_buffer_cents,
    )


def calculate_required_reserve(forecast: ForecastResult, policy: TreasuryPolicy) -> ReserveResult:
    """Frozen API: conservatively sum supplied point uncertainties, scale, ceil.

    No independence assumption is made. The frozen signature carries no vault
    schedule; callers needing maturities use reserve_for_path explicitly.
    """
    uncertainty = sum(p.uncertainty_cents for p in forecast.points)
    product = uncertainty * policy.uncertainty_multiplier_bps
    with localcontext() as ctx:
        ctx.prec = max(28, len(str(product)) + 10)
        buffer = int((Decimal(product) / Decimal(10_000)).to_integral_value(rounding=ROUND_CEILING))
    return reserve_for_path(forecast, uncertainty_buffer_cents=buffer,
                            operational_buffer_cents=policy.base_buffer_cents)


def candidate_deployable_surplus(checking_balance_cents: int, required_reserve_cents: int) -> int:
    """Candidate only: no vault balances or unarrived settlements added to checking."""
    nonnegative_integer(checking_balance_cents, "checking_balance_cents")
    nonnegative_integer(required_reserve_cents, "required_reserve_cents")
    return max(0, checking_balance_cents - required_reserve_cents)
