"""Shared execution accounting conventions; no strategy or forecasting logic."""
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP, localcontext

from sqlalchemy import select
from app.persistence.models import OrganizerObservation, OverdraftMovement


def repo_interest_cents(session, position, as_of):
    """Simple ACT/365 floating APY; sum earned hourly rates, then round once.

    Entry hour is included only when it has closed. Maturity caps accrual at
    the scheduled 08:00 boundary. Source timestamps retain unspecified timezone.
    """
    end = min(as_of, position.scheduled_maturity_at)
    rows = list(session.scalars(select(OrganizerObservation).where(
        OrganizerObservation.dataset_id == position.dataset_id,
        OrganizerObservation.timestamp >= position.entered_at,
        OrganizerObservation.timestamp < end).order_by(OrganizerObservation.timestamp)))
    expected = int((end - position.entered_at).total_seconds() // 3600)
    if expected < 0 or len(rows) != expected or any(
            row.timestamp != position.entered_at + timedelta(hours=i) for i, row in enumerate(rows)):
        raise ValueError("Repo accrual requires complete, contiguous earned source hours")
    with localcontext() as context:
        context.prec = 60
        interest = Decimal(position.principal_cents) * sum(
            (row.tier1_repo_rate_apy for row in rows), Decimal(0)) / Decimal(876000)
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
