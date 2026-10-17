import { advanceEngine, backtest, createEngine, forecastSeries, MockError, report, scheduleScenario, setPolicy, snapshot } from '../mocks/mockEngine';
import { validateForecast, validateItems, validateSnapshot, validateFourTierPortfolio } from './validation';
import { getMockFourTierSnapshot, getMockHourlyHistory, MOCK_MULTI_ASSET_DECISIONS, getMockFourTierBacktestResults } from '../mocks/fourTierFixtures';
import { ApiError } from './http';

function delay(ms, signal) {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) return reject(new DOMException('Cancelled', 'AbortError'));
    const abort = () => { clearTimeout(timer); reject(new DOMException('Cancelled', 'AbortError')); };
    const timer = setTimeout(() => { signal?.removeEventListener('abort', abort); resolve(); }, ms);
    signal?.addEventListener('abort', abort, { once: true });
  });
}
export function createMockApi({ latency = 100 } = {}) {
  const runs = new Map(); let counter = 0;
  const get = (id) => { const run = runs.get(id); if (!run) throw new MockError('Simulation not found.', 404); return run; };
  const respond = async (operation, options = {}, multiplier = 1) => {
    await delay(latency * multiplier, options.signal);
    try { return structuredClone(await operation()); } catch (error) {
      if (error instanceof MockError) throw new ApiError(error.message, { status: error.status, code: error.status === 409 ? 'STALE_STEP' : 'VALIDATION_ERROR' });
      throw error;
    }
  };
  return {
    mode: 'mock',
    health: (options) => respond(() => ({ status: 'healthy', mode: 'mock' }), options),
    createRun: (body, options) => respond(() => {
      const id = `mock-${++counter}`; const run = createEngine(body, id); runs.set(id, run);
      return { run_id: id, status: 'PAUSED' };
    }, options, 2),
    getSnapshot: (id, options) => respond(() => validateSnapshot(snapshot(get(id))), options),
    advanceRun: (id, body, options) => respond(() => advanceEngine(get(id), body.expected_step), options, 2),
    applyScenario: (id, body, options) => respond(() => scheduleScenario(get(id), body), options, 2),
    updatePolicy: (id, body, options) => respond(() => setPolicy(get(id), body), options, 2),
    getHistory: (id, options) => respond(() => validateItems({ items: get(id).history }), options),
    getForecast: (id, horizon, options) => respond(() => validateForecast(forecastSeries(get(id), horizon)), options),
    getDecisions: (id, options) => respond(() => validateItems({ items: get(id).decisions.slice().reverse().slice(0, 50) }), options),
    getTransactions: (id, options) => respond(() => validateItems({ items: get(id).transactions.slice().reverse().slice(0, 60) }), options),
    runBacktest: (id, body, options) => respond(async () => {
      const run = get(id);
      const result = typeof Worker === 'undefined' ? backtest(body, run.policy) : await new Promise((resolve, reject) => {
        if (options?.signal?.aborted) return reject(new DOMException('Cancelled', 'AbortError'));
        const worker = new Worker(new URL('../mocks/backtest.worker.js', import.meta.url), { type: 'module' });
        const finish = () => { worker.terminate(); options?.signal?.removeEventListener('abort', abort); };
        const abort = () => { finish(); reject(new DOMException('Cancelled', 'AbortError')); };
        worker.onmessage = ({ data }) => { finish(); data.error ? reject(new MockError(data.error)) : resolve(data.result); };
        worker.onerror = () => { finish(); reject(new Error('Mock backtest could not complete. Please retry.')); };
        options?.signal?.addEventListener('abort', abort, { once: true });
        worker.postMessage({ input: body, policy: run.policy });
      });
      run.backtest = result; return result;
    }, options, 5),
    getReport: (id, options) => respond(() => get(id).backtest ?? report(get(id)), options),
    getFourTierSnapshot: (id, options) => respond(() => validateFourTierPortfolio(snapshot(get(id)).four_tier ?? getMockFourTierSnapshot()), options),
    getHourlyHistory: (id, count = 24, options) => respond(() => getMockHourlyHistory(count), options),
    getMultiAssetDecisions: (id, options) => respond(() => ({ items: MOCK_MULTI_ASSET_DECISIONS }), options),
    getFourTierBacktest: (id, options) => respond(() => getMockFourTierBacktestResults(), options),
  };
}
