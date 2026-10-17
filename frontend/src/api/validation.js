import { ApiError } from './http';
const invalid = (message) => { throw new ApiError(message, { code: 'INVALID_RESPONSE' }); };
export function validateSnapshot(data) {
  if (!data || typeof data.run_id !== 'string' || !Number.isInteger(data.step) || data.step < 0) invalid('Snapshot is missing its run identity or step.');
  if (typeof data.timestamp !== 'string' || !/(Z|\+00:00)$/.test(data.timestamp) || !Number.isFinite(Date.parse(data.timestamp))) invalid('Snapshot timestamp must be ISO UTC.');
  for (const key of ['checking_cents', 'vault_locked_cents', 'vault_redeemable_cents', 'required_reserve_cents']) {
    if (!Number.isSafeInteger(data[key]) || data[key] < 0) invalid(`Snapshot ${key} must be nonnegative integer cents.`);
  }
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
  if (!Array.isArray(data?.items)) invalid('Expected a collection with an items array.');
  return data;
}
export function validateForecast(data) {
  if (!Array.isArray(data?.points)) invalid('Expected forecast points.');
  for (const point of data.points) for (const key of ['predicted_net_cents', 'lower_cents', 'upper_cents']) {
    if (point[key] != null && !Number.isSafeInteger(point[key])) invalid(`Forecast ${key} must use integer cents.`);
  }
  return data;
}
