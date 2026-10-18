import { afterEach, describe, expect, it, vi } from 'vitest';
import { requestJson } from '../src/api/http';
import { createRealApi, flattenBacktestMetrics, flattenPerformanceReport } from '../src/api/treasuryApi';
import { createMockApi } from '../src/api/mockTreasuryApi';
import { validateSnapshot, validateItems, validateForecast } from '../src/api/validation';
import { createEngine, snapshot } from '../src/mocks/mockEngine';
afterEach(() => vi.unstubAllGlobals());

describe('API boundary', () => {
  it('allows five minutes for the real synchronous seven-day comparison', async () => {
    const timer = vi.spyOn(globalThis, 'setTimeout');
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ results: [] }))));
    try {
      await createRealApi('http://localhost:8000').runBacktest('id', { days: 7 });
      expect(timer).toHaveBeenCalledWith(expect.any(Function), 300000);
    } finally {
      timer.mockRestore();
    }
  });

  it('reads actual sweeps and debt from detailed accounting and retains report history', () => {
    const row = {
      strategy: 'RESERVE_JUGGLER',
      metrics: { net_benefit_cents: -3 },
      accounting: { sweeps: 2, borrowing_outstanding_cents: 123 },
      history: [{ timestamp: '2026-01-01T00:00:00', checking_cents: 456 }],
    };
    const comparison = flattenBacktestMetrics({ results: [row] });
    expect(comparison.results[0].sweeps).toBe(2);
    expect(comparison.results[0].borrowing_outstanding_cents).toBe(123);
    const report = flattenPerformanceReport(row);
    expect(report.results[0].sweeps).toBe(2);
    expect(report.results[0].borrowing_outstanding_cents).toBe(123);
    expect(report.results[0].history).toEqual(row.history);
  });

  it('exposes interchangeable mock and real operations', () => {
    expect(Object.keys(createRealApi()).sort()).toEqual(Object.keys(createMockApi()).sort());
  });
  it('uses the exact versioned routes and snake_case payloads', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ run_id: 'id' }), { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);
    const api = createRealApi('http://localhost:8000/');
    await api.advanceRun('id', { expected_step: 4 });
    expect(fetchMock).toHaveBeenCalledWith('http://localhost:8000/api/v1/runs/id/advance', expect.objectContaining({ method: 'POST', body: '{"expected_step":4}' }));
  });
  it('distinguishes a stale-step conflict from network failure', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{"detail":"stale step"}', { status: 409 })));
    await expect(requestJson('/test')).rejects.toMatchObject({ status: 409, message: 'stale step' });
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')));
    await expect(requestJson('/test')).rejects.toMatchObject({ code: 'NETWORK_ERROR' });
  });
  it('preserves Member 2 error_code and message, including unimplemented services', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ error_code: 'NOT_IMPLEMENTED', message: 'Simulation service not implemented.', details: {} }), { status: 501 })));
    await expect(createRealApi().createRun({})).rejects.toMatchObject({ status: 501, code: 'NOT_IMPLEMENTED', message: 'Simulation service not implemented.' });
  });
  it('accepts backend array collections and nullable summary-only forecasts without inventing points', () => {
    expect(validateItems([{ step: 0 }])).toEqual({ items: [{ step: 0 }] });
    expect(validateForecast(null)).toBeNull();
    const summary = { model_version: 'supplied-model', peak_shortfall_cents: 100, uncertainty_buffer_cents: 20, operational_buffer_cents: 30 };
    expect(validateForecast(summary)).toEqual(summary);
    expect(validateForecast(summary)).not.toHaveProperty('points');
    expect(validateSnapshot({ ...snapshot(createEngine()), required_reserve_cents: null }).required_reserve_cents).toBeNull();
  });
  it('rejects invalid JSON and invalid financial units', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('<html>not JSON</html>')));
    await expect(requestJson('/test')).rejects.toMatchObject({ code: 'INVALID_RESPONSE' });
    const valid = snapshot(createEngine());
    expect(() => validateSnapshot({ ...valid, checking_cents: 1.25 })).toThrow();
    expect(() => validateSnapshot({ ...valid, timestamp: '2026-10-17T08:00:00' })).toThrow();
  });
  it('cancels an uncompleted mock mutation without changing its run', async () => {
    const api = createMockApi({ latency: 1 }); const run = await api.createRun({});
    const abort = new AbortController();
    const operation = api.advanceRun(run.run_id, { expected_step: 0 }, { signal: abort.signal });
    abort.abort(); await expect(operation).rejects.toMatchObject({ name: 'AbortError' });
    expect((await api.getSnapshot(run.run_id)).step).toBe(0);
  });
  it('implements the full API journey with coherent snapshots', async () => {
    const api = createMockApi({ latency: 0 }); const { run_id } = await api.createRun({});
    const before = await api.getSnapshot(run_id);
    await api.applyScenario(run_id, { scenario: 'HIGH_WITHDRAWAL', effective_step: 1 });
    expect((await api.getSnapshot(run_id)).checking_cents).toBe(before.checking_cents);
    await api.advanceRun(run_id, { expected_step: 0 });
    expect((await api.getHistory(run_id)).items).toHaveLength(2);
    expect((await api.getTransactions(run_id)).items.length).toBeGreaterThan(0);
    expect((await api.getDecisions(run_id)).items).toHaveLength(1);
    await api.updatePolicy(run_id, { risk_percentile: 99 });
    expect((await api.getSnapshot(run_id)).policy.risk_percentile).toBe(99);
    expect((await api.getForecast(run_id, 60)).points).toHaveLength(4);
  });
});
