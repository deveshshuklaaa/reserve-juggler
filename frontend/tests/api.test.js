import { afterEach, describe, expect, it, vi } from 'vitest';
import { requestJson } from '../src/api/http';
import { createRealApi } from '../src/api/treasuryApi';
import { createMockApi } from '../src/api/mockTreasuryApi';
import { validateSnapshot } from '../src/api/validation';
import { createEngine, snapshot } from '../src/mocks/mockEngine';
afterEach(() => vi.unstubAllGlobals());

describe('API boundary', () => {
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
