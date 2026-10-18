import { describe, expect, it } from 'vitest';
import { advanceEngine, backtest, createEngine, forecastSeries, report, scheduleScenario, setPolicy, snapshot } from '../src/mocks/mockEngine';

const assets = (run) => { const s = snapshot(run); return s.checking_cents + s.vault_locked_cents + s.vault_redeemable_cents; };
describe('deterministic mock treasury engine', () => {
  it('replays the same seed and conserves capital across internal transfers', () => {
    const a = createEngine(); const b = createEngine();
    for (let step = 0; step < 110; step++) {
      expect(advanceEngine(a)).toEqual(advanceEngine(b));
      const r = report(a);
      expect(assets(a) - a.borrowed).toBe(2600000000 + a.inflow_total - a.outflow_total + r.realized_interest_cents - r.penalties_cents - r.borrowing_costs_cents);
      expect(Number.isSafeInteger(assets(a))).toBe(true);
    }
  });
  it('schedules stress without mutating current balances and affects future steps', () => {
    const normal = createEngine(); const stressed = createEngine(); const before = snapshot(stressed);
    scheduleScenario(stressed, { scenario: 'HIGH_WITHDRAWAL', effective_step: 2, parameters: { multiplier_bps: 30000 } });
    expect(snapshot(stressed).checking_cents).toBe(before.checking_cents);
    advanceEngine(normal); advanceEngine(stressed);
    expect(stressed.transactions).toEqual(normal.transactions);
    advanceEngine(normal); advanceEngine(stressed);
    expect(stressed.history.at(-1).outflow_cents).toBeGreaterThan(normal.history.at(-1).outflow_cents);
  });
  it.each(['NORMAL', 'HIGH_WITHDRAWAL', 'LOW_DEPOSIT', 'SETTLEMENT_DELAY', 'LIQUIDITY_SHOCK'])('executes %s without fractional money or negative cash', (scenario) => {
    const run = createEngine(); scheduleScenario(run, { scenario });
    for (let step = 0; step < 20; step++) {
      const result = advanceEngine(run); expect(result.checking_cents).toBeGreaterThanOrEqual(0);
      for (const [key, value] of Object.entries(result)) if (key.endsWith('_cents')) expect(Number.isSafeInteger(value), key).toBe(true);
      const r = report(run);
      expect(assets(run) - run.borrowed).toBe(2600000000 + run.inflow_total - run.outflow_total + r.realized_interest_cents - r.penalties_cents - r.borrowing_costs_cents);
    }
  });
  it('does not make locked vault principal available under extreme stress', () => {
    const run = createEngine(); const principal = run.positions[0].principal_cents;
    scheduleScenario(run, { scenario: 'LIQUIDITY_SHOCK', parameters: { shock_cents: 10000000000 } });
    const result = advanceEngine(run);
    expect(run.positions[0].principal_cents).toBe(principal);
    expect(result.failed_payouts).toBeGreaterThan(0); expect(result.decision.action).toBe('LIQUIDITY_WARNING');
    expect(result.decision.executed).toBe(false);
  });
  it('preserves position terms when policy changes', () => {
    const run = createEngine(); const original = { ...run.positions[0] };
    setPolicy(run, { lock_steps: 4, vault_rate_bps: 900, allow_early_redemption: true });
    expect(run.positions[0]).toEqual(original);
    advanceEngine(run);
    expect(run.positions.at(-1).rate_bps).toBe(900);
    expect(run.positions.at(-1).maturity_step).toBe(5);
  });
  it('separates accrual from interest realized at maturity', () => {
    const run = createEngine({ policy: { lock_steps: 2 }, duration_steps: 4 });
    advanceEngine(run); expect(run.yield).toBe(0); expect(snapshot(run).accrued_interest_cents).toBeGreaterThan(0);
    advanceEngine(run); expect(run.yield).toBeGreaterThan(0);
  });
  it('rejects stale expected steps without duplicate financial effects', () => {
    const run = createEngine(); advanceEngine(run, 0);
    expect(() => advanceEngine(run, 0)).toThrow('Simulation step changed'); expect(run.step).toBe(1);
  });
  it('creates forecasts from observations rather than future transactions', () => {
    const a = createEngine(); const b = createEngine();
    scheduleScenario(b, { scenario: 'LIQUIDITY_SHOCK', effective_step: 8 });
    expect(forecastSeries(a)).toEqual(forecastSeries(b));
    expect(forecastSeries(a).points[0].timestamp).toBe('2026-10-17T08:15:00.000Z');
  });
  it('delays settlement receipts and later releases the exact amount', () => {
    const run = createEngine(); scheduleScenario(run, { scenario: 'SETTLEMENT_DELAY', parameters: { duration_steps: 1, delay_steps: 2, fraction_bps: 10000 } });
    advanceEngine(run); expect(run.delayed).toHaveLength(1); const amount = run.delayed[0].amount_cents;
    advanceEngine(run); advanceEngine(run);
    const baseline = createEngine(); advanceEngine(baseline); advanceEngine(baseline); advanceEngine(baseline);
    expect(run.history[3].inflow_cents - baseline.history[3].inflow_cents).toBe(amount); expect(run.delayed).toHaveLength(0);
  });
  it('compares all three strategies on identical external demand', () => {
    const result = backtest({ scenario: 'HIGH_WITHDRAWAL', days: 7, seed: 2026 });
    expect(result.results.map((r) => r.strategy)).toEqual(['STATIC', 'REACTIVE', 'RESERVE_JUGGLER']);
    expect(new Set(result.results.map((r) => r.inflow_cents)).size).toBe(1);
    expect(new Set(result.results.map((r) => r.paid_outflow_cents + r.failed_payout_cents)).size).toBe(1);
    expect(result.model_evaluation).toBe(null);
    for (const r of result.results) expect(r.net_benefit_cents).toBe(r.realized_interest_cents - r.penalties_cents - r.borrowing_costs_cents);
  });
});
