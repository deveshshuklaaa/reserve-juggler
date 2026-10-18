import { requestJson, ApiError } from './http';
import { validateSnapshot, validateItems, validateForecast } from './validation';

export { ApiError };

export function normalizeStrategyToBackend(name) {
  const map = {
    STATIC: 'STATIC',
    STATIC_RESERVE: 'STATIC',
    REACTIVE: 'REACTIVE',
    REACTIVE_RESERVE: 'REACTIVE',
    RESERVE_JUGGLER: 'RESERVE_JUGGLER',
  };
  return map[name] || name;
}

export function normalizeStrategyToFrontend(name) {
  const map = {
    STATIC: 'STATIC',
    STATIC_RESERVE: 'STATIC',
    REACTIVE: 'REACTIVE',
    REACTIVE_RESERVE: 'REACTIVE',
    RESERVE_JUGGLER: 'RESERVE_JUGGLER',
  };
  return map[name] || name;
}

export function normalizePolicy(policy = {}) {
  const p = { ...policy };
  if (p.operational_buffer_cents == null && p.base_buffer_cents != null) {
    p.operational_buffer_cents = p.base_buffer_cents;
  }
  if (p.minimum_sweep_cents == null && p.min_transfer_cents != null) {
    p.minimum_sweep_cents = p.min_transfer_cents;
  }
  if (p.early_redemption_penalty_bps == null && p.early_break_fee_bps != null) {
    p.early_redemption_penalty_bps = p.early_break_fee_bps;
  }
  if (p.risk_percentile != null && p.risk_percentile <= 1) {
    p.risk_percentile = Math.round(p.risk_percentile * 100);
  }
  return p;
}

export function serializePolicy(policy = {}) {
  const out = {};
  if (policy.operational_buffer_cents != null) {
    out.operational_buffer_cents = policy.operational_buffer_cents;
    out.base_buffer_cents = policy.operational_buffer_cents;
  }
  if (policy.minimum_sweep_cents != null) {
    out.minimum_sweep_cents = policy.minimum_sweep_cents;
    out.min_transfer_cents = policy.minimum_sweep_cents;
  }
  if (policy.early_redemption_penalty_bps != null) {
    out.early_redemption_penalty_bps = policy.early_redemption_penalty_bps;
    out.early_break_fee_bps = policy.early_redemption_penalty_bps;
  }
  if (policy.early_redemption_allowed != null) {
    out.early_redemption_allowed = Boolean(policy.early_redemption_allowed);
    out.allow_early_repo_redemption = Boolean(policy.early_redemption_allowed);
  }
  if (policy.strategy) {
    out.strategy = normalizeStrategyToBackend(policy.strategy);
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
  return { strategies, days: body.days ?? 7, retain_runs: true };
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
    const accounting = item.accounting || {};
    const strategy = normalizeStrategyToFrontend(item.strategy);
    return {
      strategy,
      run_id: data.child_run_ids?.[item.strategy] ?? null,
      realized_interest_cents: metrics.realized_interest_cents ?? item.realized_interest_cents ?? 0,
      accrued_interest_cents: metrics.accrued_interest_cents ?? item.accrued_interest_cents ?? 0,
      average_checking_cents: metrics.average_checking_cents ?? item.average_checking_cents ?? 0,
      average_vault_cents: metrics.average_vault_cents ?? item.average_vault_cents ?? 0,
      penalties_cents: metrics.redemption_penalties_cents ?? metrics.penalties_cents ?? item.penalties_cents ?? 0,
      redemption_penalties_cents: metrics.redemption_penalties_cents ?? metrics.penalties_cents ?? item.redemption_penalties_cents ?? 0,
      borrowing_costs_cents: metrics.emergency_borrowing_cost_cents ?? metrics.borrowing_costs_cents ?? item.borrowing_costs_cents ?? 0,
      emergency_borrowing_cost_cents: metrics.emergency_borrowing_cost_cents ?? metrics.borrowing_costs_cents ?? item.emergency_borrowing_cost_cents ?? 0,
      borrowing_outstanding_cents: accounting.borrowing_outstanding_cents ?? metrics.borrowing_outstanding_cents ?? item.borrowing_outstanding_cents ?? 0,
      emergency_events: metrics.emergency_events ?? item.emergency_events ?? 0,
      reserve_breaches: metrics.reserve_breaches ?? item.reserve_breaches ?? 0,
      failed_payouts: metrics.failed_payouts ?? item.failed_payouts ?? 0,
      failed_payout_cents: metrics.unpaid_cents ?? metrics.failed_payout_cents ?? item.failed_payout_cents ?? 0,
      unpaid_cents: metrics.unpaid_cents ?? metrics.failed_payout_cents ?? item.unpaid_cents ?? 0,
      sweeps: accounting.sweeps ?? metrics.sweeps ?? item.sweeps ?? 0,
      net_benefit_cents: metrics.net_benefit_cents ?? item.net_benefit_cents ?? 0,
      inflow_cents: metrics.inflow_cents ?? item.inflow_cents ?? 0,
      paid_outflow_cents: metrics.paid_outflow_cents ?? item.paid_outflow_cents ?? 0,
      history: item.history || [],
      metrics,
      accounting,
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
    child_run_ids: data.child_run_ids ?? {},
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
          accounting: data.accounting,
          history: data.history,
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
    createRunFromCashflows: async () => {
      throw new ApiError('Live CSV ingestion awaits Member 2’s upload contract. No file has been sent.', { code: 'NOT_IMPLEMENTED', status: 501 });
    },
    health: (options) => get('/health', options),
    createRun: async (body, options) => {
      const sanitized = sanitizeCreateRun(body);
      if (body?.step_minutes === 15) {
        sanitized.start_time = "2026-01-01T00:00:00Z";
        sanitized.duration_steps = 168;
      }
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
      validateSnapshot(data);
      // Legacy timestamp is response generation time; source clock is explicitly separate.
      if (data.four_tier) {
        data.source_timestamp = data.four_tier.timestamp?.replace(' ', 'T');
        data.time_basis = 'UNSPECIFIED';
        Object.assign(data, {realized_interest_cents:data.four_tier.tier1.realized_interest_cents,
          accrued_interest_cents:data.four_tier.tier1.accrued_interest_cents,
          net_benefit_cents:data.four_tier.aggregates.net_financial_benefit_cents});
      }
      return data;
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
    getTransactions: async (id, options) => {
      const data = validateItems(await get(path(id, 'transactions'), options));
      const debits = new Set(['OVERNIGHT_REPO_SWEEP_DEBIT', 'OVERDRAFT_REPAYMENT',
        'OVERDRAFT_FINANCING_PAYMENT', 'MARKET_PURCHASE_DEBIT', 'MARKET_TRANSACTION_FEE']);
      return { ...data, items: data.items.map(tx => ({ ...tx, id: tx.transaction_id ?? tx.id,
        direction: debits.has(tx.source) ? 'OUTFLOW' : tx.direction })) };
    },
    runBacktest: async (id, body, options) => {
      const payload = sanitizeBacktestRequest(body);
      // The real seven-day PostgreSQL comparison is synchronous (~171s locally).
      // A fresh parent makes the UI scenario/seed/horizon explicit, independent of live overlays.
      const parent = await post('/api/v1/runs', sanitizeCreateRun({
        initial_cash_cents: 2000000000, duration_steps: (body.days ?? 7) * 24,
        start_time: '2026-01-01T00:00:00Z', scenario: body.scenario ?? 'NORMAL', seed: body.seed ?? 42,
      }), options);
      if (!parent?.run_id) throw new ApiError('Comparison parent is missing run_id.', { code: 'INVALID_RESPONSE' });
      const data = await post(path(parent.run_id, 'backtest'), payload, { timeout_ms: 300000, ...options });
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
