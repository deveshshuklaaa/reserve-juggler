// Member 1 RJ-M1-14 boundary. This module does not infer HTTP envelopes or execute orders.
import { cents } from '../utils/format';

const fail = (message) => { throw new TypeError(`Invalid quantitative response: ${message}`); };
const list = (value, name) => { if (!Array.isArray(value)) fail(`${name} must be an array`); return value; };
const object = (value, name) => { if (!value || typeof value !== 'object' || Array.isArray(value)) fail(`${name} is required`); return value; };
export function validateFinancialIntegers(value) {
  if (!value || typeof value !== 'object') return;
  for (const [key, item] of Object.entries(value)) {
    if (key.endsWith('_cents') && item != null && key !== 'objective_cents') cents(item);
    if (item && typeof item === 'object') validateFinancialIntegers(item);
  }
}

export function validateTimeBasis(timestamp, basis) {
  if (!['UTC', 'UNSPECIFIED'].includes(basis) || typeof timestamp !== 'string') fail('explicit time_basis and timestamp required');
  const naive = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?$/;
  if (basis === 'UNSPECIFIED' ? !naive.test(timestamp) : !/^\d{4}-\d{2}-\d{2}T.*(?:Z|\+00:00)$/.test(timestamp)) fail('timestamp contradicts time_basis');
  // Parse naive labels only for validity; the original string is returned unchanged.
  if (!Number.isFinite(Date.parse(basis === 'UNSPECIFIED' ? `${timestamp}Z` : timestamp))) fail('invalid timestamp');
  return timestamp;
}

export function canonicalPortfolio(portfolio) {
  object(portfolio, 'portfolio');
  validateFinancialIntegers(portfolio);
  validateTimeBasis(portfolio.as_of, portfolio.time_basis);
  if (portfolio.currency !== 'USD') fail('expected USD portfolio');
  if (portfolio.source_type === 'ORGANIZER_HISTORICAL' && portfolio.native_interval_seconds !== 3600) fail('organizer data must stay hourly');
  object(portfolio.cash, 'cash');
  object(portfolio.valuation, 'valuation');
  for (const key of ['repo_positions', 'bond_positions', 'equity_positions', 'overdrafts']) list(portfolio[key], key);
  const valuation = portfolio.valuation;
  const required = ['tier0_cash_cents', 'tier1_value_cents', 'tier2_market_value_cents', 'tier3_market_value_cents',
    'total_portfolio_value_cents', 'net_portfolio_value_cents', 'liabilities_cents', 'immediately_available_cents',
    'restricted_value_cents', 'liquidatable_value_cents'];
  required.forEach((key) => cents(valuation[key]));
  if (required.some((key) => key !== 'net_portfolio_value_cents' && valuation[key] < 0)) fail('asset and liability amounts cannot be negative');
  cents(portfolio.cash.balance_cents);
  const positions = [portfolio.cash, ...portfolio.repo_positions, ...portfolio.bond_positions, ...portfolio.equity_positions];
  const records = [...positions, ...portfolio.overdrafts, valuation];
  for (const record of records) {
    if (['run_id', 'source_type', 'time_basis', 'dataset_id'].some((key) => record[key] !== portfolio[key])) fail('nested record provenance disagrees');
  }
  const ids = [...positions, ...portfolio.overdrafts].map((position) => position.id);
  if (ids.some((id) => typeof id !== 'string') || new Set(ids).size !== ids.length) fail('position identities must be unique');
  for (const position of positions) {
    object(position.liquidity, 'position liquidity');
    if (position !== portfolio.cash && position.liquidity.available_cents !== 0) fail('held instruments cannot be immediately available cash');
  }
  if (portfolio.cash.liquidity.available_cents !== portfolio.cash.balance_cents
    || portfolio.cash.liquidity.locked_cents !== 0) fail('cash liquidity must reconcile');
  // BigInt prevents intermediate sums from silently overflowing before comparison.
  const gross = ['tier0_cash_cents', 'tier1_value_cents', 'tier2_market_value_cents', 'tier3_market_value_cents']
    .reduce((total, key) => total + BigInt(valuation[key]), 0n);
  if (gross !== BigInt(valuation.total_portfolio_value_cents)
    || gross - BigInt(valuation.liabilities_cents) !== BigInt(valuation.net_portfolio_value_cents)
    || portfolio.cash.balance_cents !== valuation.tier0_cash_cents) fail('portfolio valuation does not reconcile');
  return portfolio;
}

const orderTiers = { INVEST_REPO: 1, REDEEM_REPO: 1, BUY_BONDS: 2, SELL_BONDS: 2,
  BUY_EQUITIES: 3, SELL_EQUITIES: 3, BORROW_OVERDRAFT: 0, REPAY_OVERDRAFT: 0 };

export function canonicalOptimizer(result, portfolio) {
  object(result, 'optimizer result');
  object(result.decision, 'decision');
  validateFinancialIntegers(result);
  const decision = result.decision;
  for (const record of [result, decision, ...list(decision.orders, 'orders')]) {
    if (record.recommendation_only !== true || record.execution_status !== 'NOT_EXECUTED') fail('recommendation cannot be an execution receipt');
  }
  validateTimeBasis(decision.as_of, decision.time_basis);
  if (portfolio && (decision.run_id !== portfolio.run_id || decision.as_of !== portfolio.as_of
    || decision.time_basis !== portfolio.time_basis)) fail('portfolio and recommendation provenance disagree');
  decision.orders.forEach((order) => {
    if (orderTiers[order.action] !== order.tier || !Number.isInteger(order.tier) || order.amount_cents <= 0) fail('order action, tier or amount is invalid');
    if (order.run_id != null && order.run_id !== decision.run_id) fail('order belongs to another run');
  });
  if (typeof decision.feasible !== 'boolean' || typeof result.search_truncated !== 'boolean') fail('feasibility and search status required');
  return result;
}

export function canonicalHourlyForecast(result) {
  object(result, 'hourly forecast');
  validateFinancialIntegers(result);
  list(result.points, 'forecast points').forEach((point) => {
    validateTimeBasis(point.start_at, point.time_basis ?? result.time_basis);
    for (const key of ['predicted_deposits_cents', 'predicted_withdrawals_cents', 'predicted_net_flow_cents', 'supplied_uncertainty_buffer_cents']) cents(point[key]);
    if (BigInt(point.predicted_deposits_cents) - BigInt(point.predicted_withdrawals_cents) !== BigInt(point.predicted_net_flow_cents)) fail('forecast net must equal deposits minus withdrawals');
  });
  return result; // No invented bands, source net flow, evaluation scores, or timezone conversion.
}
