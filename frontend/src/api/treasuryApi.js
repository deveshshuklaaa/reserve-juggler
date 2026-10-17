import { requestJson, ApiError } from './http';
import { validateSnapshot, validateItems, validateForecast } from './validation';

export function createRealApi(baseUrl = '') {
  const base = baseUrl.replace(/\/$/, '');
  const path = (id, resource) => `/api/v1/runs/${encodeURIComponent(id)}/${resource}`;
  const get = (url, options) => requestJson(`${base}${url}`, options);
  const post = (url, body, options) => get(url, { ...options, method: 'POST', body });
  return {
    mode: 'real',
    health: (options) => get('/health', options),
    createRun: async (body, options) => {
      const data = await post('/api/v1/runs', body, options);
      if (typeof data?.run_id !== 'string') throw new ApiError('Create run response is missing run_id.', { code: 'INVALID_RESPONSE' });
      return data;
    },
    getSnapshot: async (id, options) => validateSnapshot(await get(path(id, 'snapshot'), options)),
    advanceRun: (id, body, options) => post(path(id, 'advance'), body, options),
    applyScenario: (id, body, options) => post(path(id, 'scenario'), body, options),
    updatePolicy: (id, body, options) => get(path(id, 'policy'), { ...options, method: 'PATCH', body }),
    getHistory: async (id, options) => validateItems(await get(path(id, 'history'), options)),
    getForecast: async (id, horizon, options) => validateForecast(await get(`${path(id, 'forecast')}?horizon_minutes=${horizon}`, options)),
    getDecisions: async (id, options) => validateItems(await get(path(id, 'decisions'), options)),
    getTransactions: async (id, options) => validateItems(await get(path(id, 'transactions'), options)),
    runBacktest: (id, body, options) => post(path(id, 'backtest'), body, { timeout_ms: 60000, ...options }),
    getReport: (id, options) => get(path(id, 'report'), options),
  };
}
