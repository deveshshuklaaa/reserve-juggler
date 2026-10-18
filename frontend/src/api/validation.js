import { ApiError } from './http';
const invalid = (message) => { throw new ApiError(message, { code: 'INVALID_RESPONSE' }); };
export function validateSnapshot(data) {
  if (!data || typeof data.run_id !== 'string' || !Number.isInteger(data.step) || data.step < 0) invalid('Snapshot is missing its run identity or step.');
  if (typeof data.timestamp !== 'string' || !/(Z|\+00:00)$/.test(data.timestamp) || !Number.isFinite(Date.parse(data.timestamp))) invalid('Snapshot timestamp must be ISO UTC.');
  for (const key of ['checking_cents', 'vault_locked_cents', 'vault_redeemable_cents']) {
    if (!Number.isSafeInteger(data[key]) || data[key] < 0) invalid(`Snapshot ${key} must be nonnegative integer cents.`);
  }
  if (data.required_reserve_cents != null && (!Number.isSafeInteger(data.required_reserve_cents) || data.required_reserve_cents < 0)) invalid('Required reserve must be nonnegative integer cents or null.');
  for (const [key, value] of Object.entries(data)) {
    if (key.endsWith('_cents') && value != null && !Number.isSafeInteger(value)) invalid(`${key} must be integer cents.`);
  }
  if (data.decision) {
    if (!['HOLD', 'SWEEP', 'WITHDRAW', 'LIQUIDITY_WARNING'].includes(data.decision.action)
      || !Number.isSafeInteger(data.decision.amount_cents) || typeof data.decision.executed !== 'boolean') invalid('Decision fields do not match the target contract.');
  }
  return data;
}
export function validateItems(data) {
  // Member 2's frozen v1 contract returns bare arrays; mocks use items envelopes.
  if (Array.isArray(data)) return { items: data };
  if (!Array.isArray(data?.items)) invalid('Expected a collection with an items array.');
  return data;
}
export function validateForecast(data) {
  if (data == null) return null;
  // Member 2 currently specifies a summary only, without a chart series.
  if (!('points' in data) && typeof data.model_version === 'string' && Number.isSafeInteger(data.peak_shortfall_cents)) {
    for (const key of ['peak_shortfall_cents', 'uncertainty_buffer_cents', 'operational_buffer_cents']) {
      if (!Number.isSafeInteger(data[key]) || data[key] < 0) invalid(`Forecast ${key} must use nonnegative integer cents.`);
    }
    return data;
  }
  if (!Array.isArray(data?.points)) invalid('Expected forecast points.');
  for (const point of data.points) for (const key of ['predicted_net_cents', 'lower_cents', 'upper_cents']) {
    if (point[key] != null && !Number.isSafeInteger(point[key])) invalid(`Forecast ${key} must use integer cents.`);
  }
  return data;
}

export function validateFourTierPortfolio(portfolio) {
  if (!portfolio || typeof portfolio !== 'object') invalid('Expected a four-tier portfolio object.');
  const { tier0, tier1, tier2, tier3, overdraft, aggregates } = portfolio;
  if (!tier0 || !tier1 || !tier2 || !tier3 || !overdraft || !aggregates) {
    invalid('Portfolio must contain tier0, tier1, tier2, tier3, overdraft, and aggregates.');
  }

  if (!Number.isSafeInteger(tier0.checking_cents) || tier0.checking_cents < 0) {
    invalid('Tier 0 checking_cents must be nonnegative integer cents.');
  }
  if (!Number.isSafeInteger(tier1.principal_cents) || tier1.principal_cents < 0) {
    invalid('Tier 1 principal_cents must be nonnegative integer cents.');
  }
  if (!Number.isSafeInteger(tier2.market_value_cents) || tier2.market_value_cents < 0) {
    invalid('Tier 2 market_value_cents must be nonnegative integer cents.');
  }
  if (!Number.isSafeInteger(tier3.market_value_cents) || tier3.market_value_cents < 0) {
    invalid('Tier 3 market_value_cents must be nonnegative integer cents.');
  }
  if (!Number.isSafeInteger(overdraft.borrowing_outstanding_cents) || overdraft.borrowing_outstanding_cents < 0) {
    invalid('Overdraft borrowing_outstanding_cents must be nonnegative integer cents.');
  }

  // Unrealized and realized P&L can be negative or positive integers
  for (const pnlKey of ['unrealized_pnl_cents', 'realized_pnl_cents']) {
    if (tier2[pnlKey] != null && !Number.isSafeInteger(tier2[pnlKey])) {
      invalid(`Tier 2 ${pnlKey} must be integer cents.`);
    }
    if (tier3[pnlKey] != null && !Number.isSafeInteger(tier3[pnlKey])) {
      invalid(`Tier 3 ${pnlKey} must be integer cents.`);
    }
  }

  return portfolio;
}

