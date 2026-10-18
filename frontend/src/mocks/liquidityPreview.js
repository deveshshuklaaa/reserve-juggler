// A small, deterministic landing-page illustration, separate from Member 1's engine.
export function previewLiquidityShock(shock_cents, adaptive = true) {
  if (!Number.isSafeInteger(shock_cents) || Math.abs(shock_cents) > 1500000000) throw new RangeError('Shock must be integer cents within the preview range.');
  const opening_cash_cents = 2000000000;
  const checking_cents = opening_cash_cents + shock_cents;
  const required_reserve_cents = 450000000 + (adaptive && shock_cents < 0 ? Math.ceil(-shock_cents / 4) : 0);
  const reserve_deficit_cents = Math.max(0, required_reserve_cents - checking_cents);
  return { opening_cash_cents, shock_cents, checking_cents, required_reserve_cents, reserve_deficit_cents,
    proposed_allocation_cents: adaptive ? Math.max(0, checking_cents - required_reserve_cents) : 0,
    execution_status: 'NOT_EXECUTED' };
}
