/**
 * FOUR-TIER FRONTEND FINANCIAL MODELS
 * Task F1A: Canonical frontend representation for Tier 0 (Cash), Tier 1 (Overnight Repo),
 * Tier 2 (Sovereign Bonds), Tier 3 (Growth Equities), and Emergency Overdraft.
 *
 * Money amounts are strictly integer USD cents.
 * Index prices, volatility, and yields preserve precision via decimal strings where applicable.
 */

import { cents } from '../utils/format';
import { formatDecimal, parseDecimalString } from '../utils/precision';

export const REPO_RULES = Object.freeze({
  ENTRY_WINDOW_START_HOUR: 17, // 17:00 daily entry window
  MATURITY_HOUR: 8,            // 08:00 next-day maturity
  EARLY_BREAK_FEE_BPS: 50,     // 0.5% early termination penalty
  DEFAULT_REPO_APY_BPS: 520,   // 5.20% floating APY
});

export const BOND_RULES = Object.freeze({
  DEFAULT_HAIRCUT_BPS: 200,    // 2.0% liquidation haircut
  DEFAULT_MODIFIED_DURATION: 4.25,
});

export const EQUITY_RULES = Object.freeze({
  DEFAULT_SLIPPAGE_BPS: 1500,  // 15.0% emergency liquidation slippage
});

export const OVERDRAFT_RULES = Object.freeze({
  DEFAULT_FINANCING_RATE_BPS: 1000, // 10.0% annualized emergency financing cost
});

/**
 * Creates or normalizes a Tier 0 Cash Buffer.
 */
export function createTier0Cash({
  checking_cents = 0,
  required_reserve_cents = 0,
  operational_buffer_cents = 0,
} = {}) {
  cents(checking_cents);
  cents(required_reserve_cents);
  const surplus_cents = Math.max(0, checking_cents - required_reserve_cents);
  const reserve_deficit_cents = Math.max(0, required_reserve_cents - checking_cents);

  return {
    tier: 0,
    name: 'Operating Cash Buffer',
    checking_cents,
    required_reserve_cents,
    operational_buffer_cents,
    deployable_surplus_cents: surplus_cents,
    reserve_deficit_cents,
    immediate_liquidity_cents: checking_cents,
    status: reserve_deficit_cents > 0 ? 'DEFICIT' : surplus_cents > 0 ? 'SURPLUS' : 'BALANCED',
  };
}

/**
 * Creates or normalizes a Tier 1 Overnight Repo position.
 */
export function createTier1Repo({
  id = 'REPO-1',
  principal_cents = 0,
  repo_apy_bps = REPO_RULES.DEFAULT_REPO_APY_BPS,
  repo_apy_decimal = '5.20',
  accrued_interest_cents = 0,
  realized_interest_cents = 0,
  status = 'LOCKED', // 'LOCKED' | 'MATURED' | 'REDEEMED'
  entry_window_open = false,
  early_redemption_allowed = true,
  early_break_fee_bps = REPO_RULES.EARLY_BREAK_FEE_BPS,
  entry_time = '17:00',
  maturity_time = '08:00',
  maturity_timestamp = null,
} = {}) {
  cents(principal_cents);
  cents(accrued_interest_cents);
  cents(realized_interest_cents);

  const break_fee_cents = early_redemption_allowed && status === 'LOCKED'
    ? Math.round((principal_cents * early_break_fee_bps) / 10000)
    : 0;

  const net_redeemable_cents = status === 'MATURED'
    ? principal_cents + accrued_interest_cents
    : early_redemption_allowed
      ? Math.max(0, principal_cents - break_fee_cents)
      : 0;

  return {
    tier: 1,
    id,
    name: 'Overnight Repo',
    principal_cents,
    repo_apy_bps,
    repo_apy_decimal: String(repo_apy_decimal ?? formatDecimal(repo_apy_bps / 100, 2)),
    accrued_interest_cents,
    realized_interest_cents,
    status,
    entry_window_open,
    early_redemption_allowed,
    early_break_fee_bps,
    break_fee_cents,
    net_redeemable_cents,
    immediate_liquidity_cents: net_redeemable_cents,
    entry_time,
    maturity_time,
    maturity_timestamp,
  };
}

/**
 * Creates or normalizes a Tier 2 Sovereign Bond position.
 */
export function createTier2Bonds({
  id = 'BOND-SOV-1',
  notional_cents = 0,
  quantity = 1,
  acquisition_price = '100.0000',
  current_price = '100.0000',
  market_value_cents = notional_cents,
  ytm_bps = 450,
  ytm_decimal = '4.50',
  modified_duration = BOND_RULES.DEFAULT_MODIFIED_DURATION,
  liquidation_haircut_bps = BOND_RULES.DEFAULT_HAIRCUT_BPS,
  realized_pnl_cents = 0,
  unrealized_pnl_cents = 0,
} = {}) {
  cents(notional_cents);
  cents(market_value_cents);
  cents(realized_pnl_cents);
  cents(unrealized_pnl_cents);

  const acq = parseDecimalString(acquisition_price, 100);
  const cur = parseDecimalString(current_price, 100);
  const calculated_pnl = acq > 0 ? Math.round(((cur - acq) / acq) * notional_cents) : unrealized_pnl_cents;
  const pnl = unrealized_pnl_cents !== 0 ? unrealized_pnl_cents : calculated_pnl;

  const haircut_cents = Math.round((market_value_cents * liquidation_haircut_bps) / 10000);
  const available_liquidity_cents = Math.max(0, market_value_cents - haircut_cents);

  return {
    tier: 2,
    id,
    name: 'Sovereign Bonds',
    notional_cents,
    quantity,
    acquisition_price: String(acquisition_price),
    current_price: String(current_price),
    market_value_cents,
    ytm_bps,
    ytm_decimal: String(ytm_decimal ?? formatDecimal(ytm_bps / 100, 2)),
    modified_duration: Number(modified_duration),
    liquidation_haircut_bps,
    haircut_cents,
    realized_pnl_cents,
    unrealized_pnl_cents: pnl,
    available_liquidity_cents,
    liquidity_status: '2-DAY_SETTLEMENT_OR_HAIRCUT',
  };
}

/**
 * Creates or normalizes a Tier 3 Growth Equities position.
 */
export function createTier3Equities({
  id = 'EQ-IDX-1',
  quantity = 100,
  acquisition_price = '450.0000',
  current_price = '450.0000',
  market_value_cents = 0,
  cost_basis_cents = market_value_cents,
  volatility_bps = 1650,
  volatility_decimal = '16.50',
  emergency_slippage_bps = EQUITY_RULES.DEFAULT_SLIPPAGE_BPS,
  realized_pnl_cents = 0,
  unrealized_pnl_cents = 0,
} = {}) {
  cents(market_value_cents);
  cents(cost_basis_cents);
  cents(realized_pnl_cents);
  cents(unrealized_pnl_cents);

  const acq = parseDecimalString(acquisition_price, 1);
  const cur = parseDecimalString(current_price, 1);
  const calculated_pnl = acq > 0 ? Math.round(((cur - acq) / acq) * cost_basis_cents) : unrealized_pnl_cents;
  const pnl = unrealized_pnl_cents !== 0 ? unrealized_pnl_cents : calculated_pnl;

  const slippage_cents = Math.round((market_value_cents * emergency_slippage_bps) / 10000);
  const available_liquidity_cents = Math.max(0, market_value_cents - slippage_cents);

  return {
    tier: 3,
    id,
    name: 'Growth Equities',
    quantity,
    acquisition_price: String(acquisition_price),
    current_price: String(current_price),
    market_value_cents,
    cost_basis_cents,
    volatility_bps,
    volatility_decimal: String(volatility_decimal ?? formatDecimal(volatility_bps / 100, 2)),
    emergency_slippage_bps,
    slippage_cents,
    realized_pnl_cents,
    unrealized_pnl_cents: pnl,
    available_liquidity_cents,
    liquidity_status: 'MARKET_VOLATILITY_AND_SLIPPAGE',
  };
}

/**
 * Creates or normalizes an Overdraft liability.
 */
export function createOverdraft({
  borrowing_outstanding_cents = 0,
  financing_rate_bps = OVERDRAFT_RULES.DEFAULT_FINANCING_RATE_BPS,
  financing_cost_cents = 0,
  liability_status = borrowing_outstanding_cents > 0 ? 'ACTIVE' : 'CLEARED',
} = {}) {
  cents(borrowing_outstanding_cents);
  cents(financing_cost_cents);

  return {
    borrowing_outstanding_cents,
    financing_rate_bps,
    financing_cost_cents,
    liability_status,
    is_active: borrowing_outstanding_cents > 0,
  };
}

/**
 * Aggregates a full Four-Tier Portfolio.
 */
export function createFourTierPortfolio({
  tier0 = createTier0Cash(),
  tier1 = createTier1Repo(),
  tier2 = createTier2Bonds(),
  tier3 = createTier3Equities(),
  overdraft = createOverdraft(),
  timestamp = null,
} = {}) {
  const gross_assets_cents =
    tier0.checking_cents +
    tier1.principal_cents +
    tier2.market_value_cents +
    tier3.market_value_cents;

  const total_liabilities_cents = overdraft.borrowing_outstanding_cents;
  const net_portfolio_value_cents = gross_assets_cents - total_liabilities_cents;

  const total_immediate_liquidity_cents =
    tier0.immediate_liquidity_cents +
    tier1.immediate_liquidity_cents +
    tier2.available_liquidity_cents +
    tier3.available_liquidity_cents;

  const total_realized_returns_cents =
    tier1.realized_interest_cents +
    tier2.realized_pnl_cents +
    tier3.realized_pnl_cents;

  const total_unrealized_returns_cents =
    tier1.accrued_interest_cents +
    tier2.unrealized_pnl_cents +
    tier3.unrealized_pnl_cents;

  const net_financial_benefit_cents =
    total_realized_returns_cents -
    overdraft.financing_cost_cents -
    (tier1.break_fee_cents || 0);

  return {
    timestamp,
    tier0,
    tier1,
    tier2,
    tier3,
    overdraft,
    aggregates: {
      gross_assets_cents,
      total_liabilities_cents,
      net_portfolio_value_cents,
      total_immediate_liquidity_cents,
      total_realized_returns_cents,
      total_unrealized_returns_cents,
      net_financial_benefit_cents,
      checking_cents: tier0.checking_cents,
      required_reserve_cents: tier0.required_reserve_cents,
      deployable_surplus_cents: tier0.deployable_surplus_cents,
    },
  };
}
