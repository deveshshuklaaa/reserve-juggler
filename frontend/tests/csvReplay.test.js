import { describe, expect, it, vi } from 'vitest';
import { advanceEngine, backtest, createEngine, forecastSeries, report, scheduleScenario, snapshot } from '../src/mocks/mockEngine';
import { createMockApi } from '../src/api/mockTreasuryApi';

const dataset = (interval = 15, values = [[20000, 30000], [50000, 10000], [10000, 20000]]) => ({
  rows: values.map(([inflow_cents, outflow_cents], index) => ({
    timestamp: new Date(Date.UTC(2026, 9, 18, 8) + index * interval * 60000).toISOString(),
    inflow_cents, outflow_cents,
  })),
});

describe('imported CSV mock replay', () => {
  it('posts the exact imported cash flows and derives a bounded timeline from rows', () => {
    const input = { ...dataset(), start_time: '2000-01-01T00:00:00Z', duration_steps: 2000, interval_minutes: 60 };
    const run = createEngine({ cashflow_input: input, duration_steps: 1 });
    expect(snapshot(run)).toMatchObject({ step: 0, duration_steps: 3, timestamp: '2026-10-18T07:45:00.000Z',
      input_source: { type: 'CSV', row_count: 3, interval_minutes: 15,
        start_time: '2026-10-18T08:00:00.000Z', end_time: '2026-10-18T08:30:00.000Z' } });
    input.rows[0].inflow_cents = 999;
    while (run.step < run.config.duration_steps) advanceEngine(run);
    expect(run.history.slice(1).map((point) => [point.inflow_cents, point.requested_outflow_cents]))
      .toEqual([[20000, 30000], [50000, 10000], [10000, 20000]]);
    expect(report(run)).toMatchObject({ inflow_cents: 80000, paid_outflow_cents: 60000, duration_steps: 3 });
    expect(run.transactions.every((transaction) => transaction.source.startsWith('CSV cash'))).toBe(true);
    expect(snapshot(run).input_source).not.toHaveProperty('rows');
    expect(snapshot(run)).not.toHaveProperty('cashflow_input');
    expect(() => advanceEngine(run)).toThrow('completed');
  });

  it('posts hourly observations once and inserts zero flow in intervening 15-minute steps', () => {
    const run = createEngine({ cashflow_input: dataset(60, [[100, 200], [300, 400]]) });
    expect(run.config.duration_steps).toBe(5);
    while (run.step < run.config.duration_steps) advanceEngine(run);
    expect(run.history.slice(1).map((point) => [point.inflow_cents, point.requested_outflow_cents]))
      .toEqual([[100, 200], [0, 0], [0, 0], [0, 0], [300, 400]]);
    expect(run.transactions).toHaveLength(4);
  });

  it('uses observed history without exposing future CSV observations to the forecast', () => {
    const first = dataset(); const futureChanged = dataset();
    futureChanged.rows[2].inflow_cents = 100000000000;
    const a = createEngine({ cashflow_input: first }); const b = createEngine({ cashflow_input: futureChanged });
    expect(forecastSeries(a)).toEqual(forecastSeries(b));
    expect(forecastSeries(a).points[0].predicted_inflow_cents).toBe(0);
    advanceEngine(a); advanceEngine(b);
    expect(forecastSeries(a)).toEqual(forecastSeries(b));
    expect(forecastSeries(a).points[0].predicted_inflow_cents).toBe(20000);
  });

  it('rejects settlement delays when imported total inflows do not identify merchant settlements', () => {
    const run = createEngine({ cashflow_input: dataset() });
    expect(() => scheduleScenario(run, { scenario: 'SETTLEMENT_DELAY' }))
      .toThrow('CSV cash flows do not identify merchant settlements. Choose another scenario.');
    expect(run.events).toEqual([]);
    expect(run.step).toBe(0);
    scheduleScenario(run, { scenario: 'HIGH_WITHDRAWAL' });
    advanceEngine(run);
    expect(run.history.at(-1).requested_outflow_cents).toBe(90000);
  });

  it('conserves capital, including paid and unpaid borrowing costs during imported shortfalls', () => {
    const run = createEngine({ cashflow_input: dataset(15, [[100, 5000000000], [0, 0], [1000, 100]]) });
    while (run.step < run.config.duration_steps) {
      const current = advanceEngine(run); const totals = report(run);
      const netAssets = current.checking_cents + current.vault_locked_cents + current.vault_redeemable_cents - current.borrowing_outstanding_cents;
      expect(netAssets).toBe(2600000000 + totals.inflow_cents - totals.paid_outflow_cents
        + totals.realized_interest_cents - totals.penalties_cents - totals.borrowing_costs_cents);
      expect(current.checking_cents).toBeGreaterThanOrEqual(0);
      expect(Number.isSafeInteger(netAssets)).toBe(true);
    }
    expect(run.failed_payouts).toBe(1);
  });

  it.each([
    ['missing data', null],
    ['single observation', { rows: dataset().rows.slice(0, 1) }],
    ['invalid calendar date', { rows: [{ ...dataset().rows[0], timestamp: '2026-02-30T08:00:00Z' }, dataset().rows[1]] }],
    ['local timestamp', { rows: [{ ...dataset().rows[0], timestamp: '2026-10-18T08:00:00' }, dataset().rows[1]] }],
    ['fractional cents', { rows: [{ ...dataset().rows[0], inflow_cents: 1.5 }, dataset().rows[1]] }],
    ['negative amount', { rows: [{ ...dataset().rows[0], outflow_cents: -1 }, dataset().rows[1]] }],
    ['excessive amount', { rows: [{ ...dataset().rows[0], outflow_cents: 100000000001 }, dataset().rows[1]] }],
    ['duplicate timestamps', { rows: [dataset().rows[0], dataset().rows[0]] }],
    ['unsupported interval', dataset(30)],
    ['irregular observations', { rows: [dataset(15).rows[0], dataset(15).rows[1], dataset(60).rows[2]] }],
    ['excessive horizon', dataset(60, Array.from({ length: 721 }, () => [0, 0]))],
    ['excessive aggregate', dataset(15, Array.from({ length: 11 }, () => [100000000000, 100000000000]))],
  ])('rejects %s at the engine boundary instead of generating a fallback', (_, input) => {
    expect(() => createEngine({ cashflow_input: input })).toThrow();
  });

  it('compares strategies across the full dataset using identical imported demand and starting balances', () => {
    const input = { cashflow_input: dataset(60), seed: 1234, days: 30, scenario: 'LIQUIDITY_SHOCK',
      initial_checking_cents: 900000000, initial_vault_cents: 120000000 };
    const result = backtest(input, { vault_rate_bps: 725, lock_steps: 2 });
    expect(result).toMatchObject({ scenario: 'NORMAL', duration_steps: 9, label: 'Imported cash-flow replay', input_source: { type: 'CSV' } });
    expect(result.results).toHaveLength(3);
    for (const strategy of result.results) {
      expect(strategy.history[0]).toMatchObject({ checking_cents: 900000000, vault_cents: 120000000 });
      expect(strategy).toMatchObject({ inflow_cents: 80000, paid_outflow_cents: 60000, duration_steps: 9 });
      const replay = createEngine({ ...input, policy: { vault_rate_bps: 725, lock_steps: 2 } }, strategy.run_id, strategy.strategy);
      while (replay.step < replay.config.duration_steps) advanceEngine(replay);
      expect(report(replay)).toEqual(Object.fromEntries(Object.entries(strategy).filter(([key]) => key !== 'history')));
    }
  });

  it('keeps the existing generated backtest contract and seeded demand unchanged', () => {
    const a = backtest({ seed: 1234, days: 7, scenario: 'NORMAL' });
    const b = backtest({ seed: 1234, days: 7, scenario: 'NORMAL' });
    expect(a).toEqual(b);
    expect(a).toMatchObject({ days: 7, duration_steps: 672, scenario: 'NORMAL' });
    expect(a).not.toHaveProperty('input_source');
    expect(a.results.every((result) => result.inflow_cents > 0)).toBe(true);
  });

  it('creates imports through a mock-only API capability and carries the original configuration into comparisons', async () => {
    const api = createMockApi({ latency: 0 });
    const created = await api.createRunFromCashflows(dataset(60), { seed: 88, initial_checking_cents: 900000000,
      initial_vault_cents: 120000000, policy: { vault_rate_bps: 725 } });
    const initial = await api.getSnapshot(created.run_id);
    expect(initial).toMatchObject({ checking_cents: 900000000, duration_steps: 9, input_source: { type: 'CSV' } });
    await api.advanceRun(created.run_id, { expected_step: 0 });
    const comparison = await api.runBacktest(created.run_id, { days: 30, seed: 999, scenario: 'HIGH_WITHDRAWAL' });
    expect(comparison).toMatchObject({ seed: 88, scenario: 'NORMAL', duration_steps: 9 });
    expect(comparison.results.every((result) => result.history[0].checking_cents === 900000000)).toBe(true);
    expect(await api.getReport(created.run_id)).toEqual(comparison);
    await expect(api.createRunFromCashflows(null)).rejects.toMatchObject({ code: 'VALIDATION_ERROR' });
  });

  it('passes the imported dataset to the comparison worker without substituting synthetic flows', async () => {
    const posted = [];
    class BacktestWorker {
      postMessage(message) {
        posted.push(message);
        queueMicrotask(() => this.onmessage({ data: { result: backtest(message.input, message.policy) } }));
      }
      terminate() {}
    }
    vi.stubGlobal('Worker', BacktestWorker);
    try {
      const api = createMockApi({ latency: 0 });
      const created = await api.createRunFromCashflows(dataset(), { seed: 9, initial_checking_cents: 500000000 });
      const result = await api.runBacktest(created.run_id, { days: 14, seed: 777, scenario: 'HIGH_WITHDRAWAL' });
      expect(posted[0].input).toMatchObject({ seed: 9, cashflow_input: { rows: dataset().rows }, initial_checking_cents: 500000000 });
      expect(result).toMatchObject({ duration_steps: 3, scenario: 'NORMAL', input_source: { type: 'CSV' } });
    } finally { vi.unstubAllGlobals(); }
  });
});
