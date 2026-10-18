import { afterEach, describe, expect, it, vi } from 'vitest';
import { requestJson } from '../src/api/http';
import {
  createRealApi,
  flattenBacktestMetrics,
  flattenPerformanceReport,
  normalizePolicy,
  normalizeStrategyToBackend,
  normalizeStrategyToFrontend,
  sanitizeBacktestRequest,
  sanitizeCreateRun,
  serializePolicy,
} from '../src/api/treasuryApi';
import { createMockApi } from '../src/api/mockTreasuryApi';
import { validateSnapshot } from '../src/api/validation';
import { createEngine, snapshot } from '../src/mocks/mockEngine';

afterEach(() => vi.unstubAllGlobals());

describe('API boundary', () => {
  it('allows five minutes for the real synchronous seven-day comparison', async () => {
    const timer = vi.spyOn(globalThis, 'setTimeout');
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ results: [] }))));
    try {
      await createRealApi('http://localhost:8017').runBacktest('id', { days: 7 });
      expect(timer).toHaveBeenCalledWith(expect.any(Function), 300000);
    } finally {
      timer.mockRestore();
    }
  });

  it('exposes interchangeable mock and real operations', () => {
    expect(Object.keys(createRealApi()).sort()).toEqual(Object.keys(createMockApi()).sort());
  });

  it('reads actual sweeps and debt from detailed accounting and retains report history', () => {
    const row = { strategy: 'RESERVE_JUGGLER', metrics: { net_benefit_cents: -3 },
      accounting: { sweeps: 2, borrowing_outstanding_cents: 123 },
      history: [{ timestamp: '2026-01-01T00:00:00', checking_cents: 456 }] };
    const comparison = flattenBacktestMetrics({ results: [row] });
    expect(comparison.results[0].sweeps).toBe(2);
    expect(comparison.results[0].borrowing_outstanding_cents).toBe(123);
    const report = flattenPerformanceReport(row);
    expect(report.results[0].sweeps).toBe(2);
    expect(report.results[0].borrowing_outstanding_cents).toBe(123);
    expect(report.results[0].history).toEqual(row.history);
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

  describe('Contract gap integration adapters', () => {
    it('sanitizes run-creation body and removes unsupported request fields', async () => {
      const dirtyBody = {
        seed: 2026,
        duration_steps: 192,
        step_minutes: 15,
        start_time: '2026-10-17T08:00:00.000Z',
        initial_checking_cents: 2000000000,
        initial_vault_cents: 600000000,
        policy: {
          risk_percentile: 95,
          min_sweep_cents: 1000000,
          vault_rate_bps: 500,
          lock_steps: 96,
          allow_early_redemption: true,
        },
      };

      const sanitized = sanitizeCreateRun(dirtyBody);
      expect(sanitized).toEqual({
        initial_cash_cents: 2000000000,
        duration_steps: 192,
        seed: 2026,
        scenario: 'NORMAL',
        start_time: '2026-10-17T08:00:00.000Z',
        policy: {
          risk_percentile: 0.95,
          minimum_sweep_cents: 1000000,
          vault_yield_bps: 500,
          vault_lock_steps: 96,
          early_redemption_allowed: true,
        },
      });
      expect(sanitized.step_minutes).toBeUndefined();
      expect(sanitized.initial_vault_cents).toBeUndefined();
      expect(sanitized.initial_checking_cents).toBeUndefined();

      const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ run_id: 'new-run-id', status: 'READY' }), { status: 201 }));
      vi.stubGlobal('fetch', fetchMock);
      const api = createRealApi('http://localhost:8000');
      const res = await api.createRun(dirtyBody);
      expect(res.run_id).toBe('new-run-id');
      const calledBody = JSON.parse(fetchMock.mock.calls[0][1].body);
      expect(calledBody.step_minutes).toBeUndefined();
      expect(calledBody.initial_vault_cents).toBeUndefined();
      expect(calledBody.initial_cash_cents).toBe(2000000000);
    });

    it('normalizes strategy IDs between frontend Arena and backend contract', () => {
      expect(normalizeStrategyToBackend('STATIC')).toBe('STATIC_RESERVE');
      expect(normalizeStrategyToBackend('REACTIVE')).toBe('REACTIVE_RESERVE');
      expect(normalizeStrategyToBackend('RESERVE_JUGGLER')).toBe('RESERVE_JUGGLER');
      expect(normalizeStrategyToBackend('STATIC_RESERVE')).toBe('STATIC_RESERVE');

      expect(normalizeStrategyToFrontend('STATIC_RESERVE')).toBe('STATIC');
      expect(normalizeStrategyToFrontend('REACTIVE_RESERVE')).toBe('REACTIVE');
      expect(normalizeStrategyToFrontend('RESERVE_JUGGLER')).toBe('RESERVE_JUGGLER');

      const sanitizedReq = sanitizeBacktestRequest({
        scenario: 'HIGH_WITHDRAWAL',
        days: 7,
        seed: 2026,
        strategies: ['STATIC', 'REACTIVE', 'RESERVE_JUGGLER'],
      });
      expect(sanitizedReq).toEqual({
        strategies: ['STATIC_RESERVE', 'REACTIVE_RESERVE', 'RESERVE_JUGGLER'],
      });
      expect(sanitizedReq.days).toBeUndefined();
      expect(sanitizedReq.seed).toBeUndefined();
      expect(sanitizedReq.scenario).toBeUndefined();
    });

    it('normalizes canonical policy response keys and risk-percentile', async () => {
      const backendPolicy = {
        risk_percentile: 0.95,
        operational_buffer_cents: 50000000,
        minimum_sweep_cents: 1000000,
        vault_yield_bps: 500,
        vault_lock_steps: 96,
        early_redemption_allowed: true,
        early_redemption_penalty_bps: 200,
      };

      const normalized = normalizePolicy(backendPolicy);
      expect(normalized.risk_percentile).toBe(95);
      expect(normalized.min_sweep_cents).toBe(1000000);
      expect(normalized.minimum_sweep_cents).toBe(1000000);
      expect(normalized.vault_rate_bps).toBe(500);
      expect(normalized.vault_yield_bps).toBe(500);
      expect(normalized.lock_steps).toBe(96);
      expect(normalized.vault_lock_steps).toBe(96);
      expect(normalized.allow_early_redemption).toBe(true);
      expect(normalized.early_redemption_allowed).toBe(true);

      const serialized = serializePolicy({
        risk_percentile: 95,
        min_sweep_cents: 2000000,
        vault_rate_bps: 600,
        lock_steps: 128,
        allow_early_redemption: false,
      });
      expect(serialized).toEqual({
        risk_percentile: 0.95,
        minimum_sweep_cents: 2000000,
        vault_yield_bps: 600,
        vault_lock_steps: 128,
        early_redemption_allowed: false,
      });
    });

    it('flattens nested backtest metrics into the structure expected by Strategy Arena', async () => {
      const backendBacktestResponse = {
        run_id: '3fa85f64-5717-4562-b3fc-2c963f66afa6',
        scenario: 'HIGH_WITHDRAWAL',
        seed: 42,
        started_at: '2026-10-18T00:00:00Z',
        ended_at: '2026-10-25T00:00:00Z',
        results: [
          {
            strategy: 'STATIC_RESERVE',
            metrics: {
              realized_interest_cents: 500000,
              accrued_interest_cents: 10000,
              average_checking_cents: 1400000000,
              average_vault_cents: 600000000,
              redemption_penalties_cents: 50000,
              emergency_borrowing_cost_cents: 20000,
              emergency_events: 1,
              reserve_breaches: 2,
              failed_payouts: 0,
              unpaid_cents: 0,
              net_benefit_cents: 430000,
            },
          },
          {
            strategy: 'RESERVE_JUGGLER',
            metrics: {
              realized_interest_cents: 800000,
              accrued_interest_cents: 20000,
              average_checking_cents: 800000000,
              average_vault_cents: 1200000000,
              redemption_penalties_cents: 0,
              emergency_borrowing_cost_cents: 0,
              emergency_events: 0,
              reserve_breaches: 0,
              failed_payouts: 0,
              unpaid_cents: 0,
              net_benefit_cents: 800000,
            },
          },
        ],
      };

      const flattened = flattenBacktestMetrics(backendBacktestResponse, { days: 7, seed: 42, scenario: 'HIGH_WITHDRAWAL' });
      expect(flattened.status).toBe('COMPLETED');
      expect(flattened.days).toBe(7);
      expect(flattened.seed).toBe(42);
      expect(flattened.scenario).toBe('HIGH_WITHDRAWAL');
      expect(flattened.results).toHaveLength(2);

      const staticRes = flattened.results[0];
      expect(staticRes.strategy).toBe('STATIC');
      expect(staticRes.realized_interest_cents).toBe(500000);
      expect(staticRes.average_checking_cents).toBe(1400000000);
      expect(staticRes.penalties_cents).toBe(50000);
      expect(staticRes.borrowing_costs_cents).toBe(20000);
      expect(staticRes.reserve_breaches).toBe(2);
      expect(staticRes.emergency_events).toBe(1);
      expect(staticRes.failed_payouts).toBe(0);
      expect(staticRes.net_benefit_cents).toBe(430000);

      const jugglerRes = flattened.results[1];
      expect(jugglerRes.strategy).toBe('RESERVE_JUGGLER');
      expect(jugglerRes.net_benefit_cents).toBe(800000);
    });

    it('flattens performance report response for Strategy Arena consumption', () => {
      const backendReport = {
        run_id: 'run-report-1',
        scenario: 'NORMAL',
        seed: 100,
        started_at: '2026-10-18T00:00:00Z',
        ended_at: '2026-10-25T00:00:00Z',
        metrics: {
          realized_interest_cents: 120000,
          accrued_interest_cents: 0,
          average_checking_cents: 1500000000,
          average_vault_cents: 500000000,
          redemption_penalties_cents: 0,
          emergency_borrowing_cost_cents: 0,
          emergency_events: 0,
          reserve_breaches: 0,
          failed_payouts: 0,
          unpaid_cents: 0,
          net_benefit_cents: 120000,
        },
      };

      const flattened = flattenPerformanceReport(backendReport);
      expect(flattened.status).toBe('COMPLETED');
      expect(flattened.days).toBe(7);
      expect(flattened.results).toHaveLength(1);
      expect(flattened.results[0].strategy).toBe('RESERVE_JUGGLER');
      expect(flattened.results[0].realized_interest_cents).toBe(120000);
    });
  });
});
