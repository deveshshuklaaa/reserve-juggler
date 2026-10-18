"""Shared execution accounting conventions; no strategy or forecasting logic."""
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP, localcontext

from sqlalchemy import select
from app.persistence.models import BondPosition, InvestmentMovement, OrganizerObservation, OverdraftMovement
from treasury_intelligence.instrument_economics import usd_to_ledger_cents


def market_cost_basis(session, position):
    """Remaining actual acquisition cents, not a repricing of the original lot.

    Execution movements release basis on each sale. Legacy opening positions
    without movements retain their persisted value-minus-unrealized basis.
    """
    link = (InvestmentMovement.bond_position_id if isinstance(position, BondPosition)
            else InvestmentMovement.equity_position_id)
    rows = list(session.scalars(select(InvestmentMovement).where(
        InvestmentMovement.run_id == position.run_id, link == position.id,
        InvestmentMovement.kind.in_(["INVESTMENT", "LIQUIDATION"]))))
    buys = [m for m in rows if m.kind == "INVESTMENT"]
    if buys:
        basis = sum(m.principal_cents or 0 for m in buys) - sum(
            m.principal_cents or 0 for m in rows if m.kind == "LIQUIDATION")
    elif position.current_market_value_cents is not None and position.unrealized_pnl_cents is not None:
        basis = position.current_market_value_cents - position.unrealized_pnl_cents
    else:
        with localcontext() as context:
            context.prec = 80
            basis = usd_to_ledger_cents(position.quantity * position.acquisition_price_index)
    if basis < 0:
        raise ValueError("Market movements release more basis than was acquired")
    return basis


def repo_hourly_rates(session, position, as_of, publication_delay_seconds=0):
    """Freeze each earning hour's rate at that hour's close, not at later replay.

    Simulation convention confirmed by the project owner. It is not a claim
    about the organizer's actual publication behavior or real repo contracts.
    """
    from bisect import bisect_right
    if type(publication_delay_seconds) is not int or not 0 <= publication_delay_seconds <= 2147483647:
        raise ValueError("Publication delay must be nonnegative integer seconds within int32")
    end = min(as_of, position.scheduled_maturity_at)
    seconds = (end-position.entered_at).total_seconds()
    if seconds < 0 or seconds % 3600:
        raise ValueError("Repo accrual requires complete native earning hours")
    count = int(seconds // 3600)
    if not count:
        return []
    last_cutoff = end-timedelta(hours=1, seconds=publication_delay_seconds)
    rows = list(session.scalars(select(OrganizerObservation).where(
        OrganizerObservation.dataset_id == position.dataset_id,
        OrganizerObservation.timestamp <= last_cutoff
    ).order_by(OrganizerObservation.timestamp.desc()).limit(count+2)))
    rows.reverse()
    timestamps = [row.timestamp for row in rows]
    result = []
    for hour in range(count):
        earned_at = position.entered_at+timedelta(hours=hour)
        close = earned_at+timedelta(hours=1)
        cutoff = earned_at-timedelta(seconds=publication_delay_seconds)
        index = bisect_right(timestamps, cutoff)-1
        if index < 0:
            raise ValueError("Repo accrual has no eligible published rate")
        row = rows[index]
        if not publication_delay_seconds and row.timestamp != earned_at:
            raise ValueError("Repo accrual requires complete, contiguous earned source hours")
        result.append(dict(earned_at=earned_at.isoformat(), accrual_cutoff=close.isoformat(),
            rate_observed_at=row.timestamp.isoformat(),
            rate_available_at=(row.timestamp+timedelta(hours=1, seconds=publication_delay_seconds)).isoformat(),
            apy_pct=str(row.tier1_repo_rate_apy)))
    return result


def repo_interest_cents(session, position, as_of, publication_delay_seconds=0):
    """ACT/365 simple floating interest: accumulate exact selected APYs, round once."""
    rates = repo_hourly_rates(session, position, as_of, publication_delay_seconds)
    with localcontext() as context:
        context.prec = 80
        interest = Decimal(position.principal_cents) * sum(
            (Decimal(row["apy_pct"]) for row in rates), Decimal(0)) / Decimal(876000)
        return int(interest.to_integral_value(rounding=ROUND_HALF_UP))


def paid_financing_costs(session, run_id, before=None):
    """Cumulative paid expense by loan, distinct from principal repayment."""
    statement = select(OverdraftMovement).where(
        OverdraftMovement.run_id == run_id, OverdraftMovement.kind == "REPAYMENT")
    if before is not None:
        statement = statement.where(OverdraftMovement.occurred_at < before)
    result = {}
    for row in session.scalars(statement):
        result[row.liability_id] = result.get(row.liability_id, 0) + row.financing_cost_cents
    return result
