import { requestJson, ApiError } from './http';
import { validateSnapshot, validateItems, validateForecast } from './validation';

const STRATEGY_TO_BACKEND = {
  STATIC: 'STATIC_RESERVE',
  STATIC_RESERVE: 'STATIC_RESERVE',
  REACTIVE: 'REACTIVE_RESERVE',
  REACTIVE_RESERVE: 'REACTIVE_RESERVE',
  RESERVE_JUGGLER: 'RESERVE_JUGGLER',
};

const STRATEGY_TO_FRONTEND = {
  STATIC_RESERVE: 'STATIC',
  STATIC: 'STATIC',
  REACTIVE_RESERVE: 'REACTIVE',
  REACTIVE: 'REACTIVE',
  RESERVE_JUGGLER: 'RESERVE_JUGGLER',
};

export function normalizeStrategyToBackend(strategy) {
  return STRATEGY_TO_BACKEND[strategy] || strategy;
}

export function normalizeStrategyToFrontend(strategy) {
  return STRATEGY_TO_FRONTEND[strategy] || strategy;
}

export function normalizePolicy(policy) {
  if (!policy || typeof policy !== 'object') return policy;
  const p = { ...policy };

  if (p.risk_percentile != null && typeof p.risk_percentile === 'number') {
    if (p.risk_percentile <= 1 && p.risk_percentile > 0) {
      p.risk_percentile = Math.round(p.risk_percentile * 100);
    }
  }

  const minSweep = p.minimum_sweep_cents ?? p.min_sweep_cents;
  if (minSweep != null) {
    p.minimum_sweep_cents = minSweep;
    p.min_sweep_cents = minSweep;
  }

  const vaultYield = p.vault_yield_bps ?? p.vault_rate_bps;
  if (vaultYield != null) {
    p.vault_yield_bps = vaultYield;
    p.vault_rate_bps = vaultYield;
  }

  const lockSteps = p.vault_lock_steps ?? p.lock_steps;
  if (lockSteps != null) {
    p.vault_lock_steps = lockSteps;
    p.lock_steps = lockSteps;
  }

  const allowEarly = p.early_redemption_allowed ?? p.allow_early_redemption;
  if (allowEarly != null) {
    p.early_redemption_allowed = Boolean(allowEarly);
    p.allow_early_redemption = Boolean(allowEarly);
  }

  return p;
}

export function serializePolicy(policy) {
  if (!policy || typeof policy !== 'object') return policy;
  const out = {};
  if (policy.operational_buffer_cents != null) {
    out.operational_buffer_cents = policy.operational_buffer_cents;
  }
  const minSweep = policy.minimum_sweep_cents ?? policy.min_sweep_cents;
  if (minSweep != null) {
    out.minimum_sweep_cents = minSweep;
  }
  const vaultYield = policy.vault_yield_bps ?? policy.vault_rate_bps;
  if (vaultYield != null) {
    out.vault_yield_bps = vaultYield;
  }
  const lockSteps = policy.vault_lock_steps ?? policy.lock_steps;
  if (lockSteps != null) {
    out.vault_lock_steps = lockSteps;
  }
  const allowEarly = policy.early_redemption_allowed ?? policy.allow_early_redemption;
  if (allowEarly != null) {
    out.early_redemption_allowed = Boolean(allowEarly);
  }
  if (policy.early_redemption_penalty_bps != null) {
    out.early_redemption_penalty_bps = policy.early_redemption_penalty_bps;
  }
  if (policy.risk_percentile != null) {
    out.risk_percentile = policy.risk_percentile > 1
      ? Number((policy.risk_percentile / 100).toFixed(4))
      : policy.risk_percentile;
  }
  return out;
}

export function sanitizeCreateRun(body = {}) {
  const initialCash = body.initial_cash_cents ?? body.initial_checking_cents ?? 2000000000;
  const payload = {
    initial_cash_cents: initialCash,
    duration_steps: body.duration_steps ?? 288,
    seed: body.seed ?? 42,
    scenario: body.scenario ?? 'NORMAL',
  };
  if (body.start_time) {
    payload.start_time = body.start_time;
  }
  if (body.policy) {
    payload.policy = serializePolicy(body.policy);
  }
  return payload;
}

export function sanitizeBacktestRequest(body = {}) {
  const rawStrategies = Array.isArray(body.strategies) && body.strategies.length > 0
    ? body.strategies
    : ['STATIC', 'REACTIVE', 'RESERVE_JUGGLER'];
  const strategies = rawStrategies.map(normalizeStrategyToBackend);
  return { strategies };
}

export function flattenBacktestMetrics(data, originalRequest = {}) {
  if (!data || typeof data !== 'object') return data;

  let days = originalRequest.days;
  if (!days && data.started_at && data.ended_at) {
    const diffMs = new Date(data.ended_at).getTime() - new Date(data.started_at).getTime();
    days = Math.max(1, Math.round(diffMs / (24 * 3600 * 1000)));
  }
  if (!days) days = 7;

  const rawResults = Array.isArray(data.results) ? data.results : [];
  const results = rawResults.map((item) => {
    const metrics = item.metrics || {};
    const strategy = normalizeStrategyToFrontend(item.strategy);
    return {
      strategy,
      realized_interest_cents: metrics.realized_interest_cents ?? item.realized_interest_cents ?? 0,
      accrued_interest_cents: metrics.accrued_interest_cents ?? item.accrued_interest_cents ?? 0,
      average_checking_cents: metrics.average_checking_cents ?? item.average_checking_cents ?? 0,
      average_vault_cents: metrics.average_vault_cents ?? item.average_vault_cents ?? 0,
      penalties_cents: metrics.redemption_penalties_cents ?? metrics.penalties_cents ?? item.penalties_cents ?? 0,
      redemption_penalties_cents: metrics.redemption_penalties_cents ?? metrics.penalties_cents ?? item.redemption_penalties_cents ?? 0,
      borrowing_costs_cents: metrics.emergency_borrowing_cost_cents ?? metrics.borrowing_costs_cents ?? item.borrowing_costs_cents ?? 0,
      emergency_borrowing_cost_cents: metrics.emergency_borrowing_cost_cents ?? metrics.borrowing_costs_cents ?? item.emergency_borrowing_cost_cents ?? 0,
      borrowing_outstanding_cents: metrics.borrowing_outstanding_cents ?? item.borrowing_outstanding_cents ?? 0,
      emergency_events: metrics.emergency_events ?? item.emergency_events ?? 0,
      reserve_breaches: metrics.reserve_breaches ?? item.reserve_breaches ?? 0,
      failed_payouts: metrics.failed_payouts ?? item.failed_payouts ?? 0,
      failed_payout_cents: metrics.unpaid_cents ?? metrics.failed_payout_cents ?? item.failed_payout_cents ?? 0,
      unpaid_cents: metrics.unpaid_cents ?? metrics.failed_payout_cents ?? item.unpaid_cents ?? 0,
      sweeps: metrics.sweeps ?? item.sweeps ?? 0,
      net_benefit_cents: metrics.net_benefit_cents ?? item.net_benefit_cents ?? 0,
      inflow_cents: metrics.inflow_cents ?? item.inflow_cents ?? 0,
      paid_outflow_cents: metrics.paid_outflow_cents ?? item.paid_outflow_cents ?? 0,
      history: item.history || [],
      metrics,
    };
  });

  return {
    status: 'COMPLETED',
    source: data.source ?? 'backend',
    run_id: data.run_id,
    scenario: data.scenario ?? originalRequest.scenario ?? 'NORMAL',
    seed: data.seed ?? originalRequest.seed,
    days,
    started_at: data.started_at,
    ended_at: data.ended_at,
    model_evaluation: data.model_evaluation ?? null,
    results,
  };
}

export function flattenPerformanceReport(data) {
  if (!data || typeof data !== 'object') return data;
  if (Array.isArray(data.results)) {
    return flattenBacktestMetrics(data);
  }
  if (data.metrics) {
    return flattenBacktestMetrics({
      ...data,
      results: [
        {
          strategy: data.strategy || 'RESERVE_JUGGLER',
          metrics: data.metrics,
        },
      ],
    });
  }
  return data;
}

export function createRealApi(baseUrl = '') {
  const base = baseUrl.replace(/\/$/, '');
  const path = (id, resource) => `/api/v1/runs/${encodeURIComponent(id)}/${resource}`;
  const get = (url, options) => requestJson(`${base}${url}`, options);
  const post = (url, body, options) => get(url, { ...options, method: 'POST', body });
  return {
    mode: 'real',
    health: (options) => get('/health', options),
    createRun: async (body, options) => {
      const sanitized = sanitizeCreateRun(body);
      const data = await post('/api/v1/runs', sanitized, options);
      if (typeof data?.run_id !== 'string') throw new ApiError('Create run response is missing run_id.', { code: 'INVALID_RESPONSE' });
      return data;
    },
    getSnapshot: async (id, options) => {
      const data = await get(path(id, 'snapshot'), options);
      if (data?.policy) {
        data.policy = normalizePolicy(data.policy);
      }
      if (data?.forecast?.risk_percentile != null && data.forecast.risk_percentile <= 1) {
        data.forecast.risk_percentile = Math.round(data.forecast.risk_percentile * 100);
      }
      return validateSnapshot(data);
    },
    advanceRun: (id, body, options) => post(path(id, 'advance'), body, options),
    applyScenario: (id, body, options) => post(path(id, 'scenario'), body, options),
    updatePolicy: async (id, body, options) => {
      const payload = serializePolicy(body);
      const data = await get(path(id, 'policy'), { ...options, method: 'PATCH', body: payload });
      return normalizePolicy(data);
    },
    getHistory: async (id, options) => {
      const data = await get(path(id, 'history'), options);
      if (Array.isArray(data?.items)) {
        for (const item of data.items) {
          if (item?.policy) item.policy = normalizePolicy(item.policy);
        }
      }
      return validateItems(data);
    },
    getForecast: async (id, horizon, options) => validateForecast(await get(`${path(id, 'forecast')}?horizon_minutes=${horizon}`, options)),
    getDecisions: async (id, options) => validateItems(await get(path(id, 'decisions'), options)),
    getTransactions: async (id, options) => validateItems(await get(path(id, 'transactions'), options)),
    runBacktest: async (id, body, options) => {
      const payload = sanitizeBacktestRequest(body);
      const data = await post(path(id, 'backtest'), payload, { timeout_ms: 60000, ...options });
      return flattenBacktestMetrics(data, body);
    },
    getReport: async (id, options) => {
      const data = await get(path(id, 'report'), options);
      return flattenPerformanceReport(data);
    },
    getFourTierSnapshot: async (_id, _options) => {
      throw new ApiError('Four-tier live endpoint pending Member 2 backend mapping confirmation (see PENDING_BACKEND_MAPPINGS.md).', { code: 'NOT_IMPLEMENTED', status: 501 });
    },
    getHourlyHistory: async (_id, _options) => {
      throw new ApiError('Hourly history live endpoint pending Member 2 backend mapping confirmation (see PENDING_BACKEND_MAPPINGS.md).', { code: 'NOT_IMPLEMENTED', status: 501 });
    },
    getMultiAssetDecisions: async (_id, _options) => {
      throw new ApiError('Multi-asset decisions live endpoint pending Member 2 backend mapping confirmation (see PENDING_BACKEND_MAPPINGS.md).', { code: 'NOT_IMPLEMENTED', status: 501 });
    },
    getFourTierBacktest: async (_id, _options) => {
      throw new ApiError('Four-tier backtest live endpoint pending Member 2 backend mapping confirmation (see PENDING_BACKEND_MAPPINGS.md).', { code: 'NOT_IMPLEMENTED', status: 501 });
    },
  };
}
