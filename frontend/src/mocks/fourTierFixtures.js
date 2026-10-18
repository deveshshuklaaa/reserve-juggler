/**
 * FOUR-TIER DETERMINISTIC MOCK FIXTURES & ADAPTERS
 * Task F1A: Deterministic four-tier portfolio fixtures, native hourly timeline history,
 * multi-asset recommendations, and comparative benchmark data.
 */

import {
  createFourTierPortfolio,
  createTier0Cash,
  createTier1Repo,
  createTier2Bonds,
  createTier3Equities,
  createOverdraft,
} from '../models/fourTier';

/**
 * Standard deterministic four-tier portfolio snapshot fixture.
 */
export function getMockFourTierSnapshot(overrides = {}) {
  const tier0 = createTier0Cash({
    checking_cents: 2000000000,          // $20,000,000.00
    required_reserve_cents: 450000000,   // $4,500,000.00
    operational_buffer_cents: 50000000,  // $500,000.00
    ...overrides.tier0,
  });

  const tier1 = createTier1Repo({
    id: 'REPO-2026-001',
    principal_cents: 600000000,          // $6,000,000.00
    repo_apy_bps: 525,                   // 5.25%
    repo_apy_decimal: '5.2500',
    accrued_interest_cents: 86301,       // $863.01 accrued
    realized_interest_cents: 172602,     // $1,726.02 realized
    status: 'LOCKED',
    entry_window_open: false,            // 17:00 window closed at current time
    early_redemption_allowed: true,
    early_break_fee_bps: 50,             // 0.5%
    entry_time: '17:00',
    maturity_time: '08:00',
    maturity_timestamp: '2026-10-18T08:00:00.000Z',
    ...overrides.tier1,
  });

  const tier2 = createTier2Bonds({
    id: 'BOND-T2-10Y',
    notional_cents: 400000000,           // $4,000,000.00 par
    quantity: 40000,
    acquisition_price: '98.5000',
    current_price: '101.2500',
    market_value_cents: 411167512,       // $4,111,675.12
    ytm_bps: 445,
    ytm_decimal: '4.4500',
    modified_duration: 4.25,
    liquidation_haircut_bps: 200,        // 2.0%
    realized_pnl_cents: 2500000,         // $25,000.00
    unrealized_pnl_cents: 11167512,      // +$111,675.12
    ...overrides.tier2,
  });

  const tier3 = createTier3Equities({
    id: 'EQ-T3-GLOBAL',
    quantity: 5000,
    acquisition_price: '420.0000',
    current_price: '445.5000',
    market_value_cents: 222750000,       // $2,227,500.00
    cost_basis_cents: 210000000,         // $2,100,000.00
    volatility_bps: 1680,                // 16.80%
    volatility_decimal: '16.80',
    emergency_slippage_bps: 1500,        // 15.0%
    realized_pnl_cents: 0,
    unrealized_pnl_cents: 12750000,      // +$127,500.00
    ...overrides.tier3,
  });

  const overdraft = createOverdraft({
    borrowing_outstanding_cents: 0,
    financing_rate_bps: 1000,            // 10.0%
    financing_cost_cents: 0,
    liability_status: 'CLEARED',
    ...overrides.overdraft,
  });

  return createFourTierPortfolio({
    tier0,
    tier1,
    tier2,
    tier3,
    overdraft,
    timestamp: overrides.timestamp ?? '2026-10-17T08:00:00.000Z',
  });
}

/**
 * Native hourly historical observation series (1-hour resolution).
 * Preserves raw organizer timeline format without synthesizing quarter-hours.
 */
export function getMockHourlyHistory(count = 24, startHour = '2026-01-01 00:00:00') {
  const items = [];
  const baseChecking = 2000000000;
  const baseReserve = 450000000;

  for (let hour = 0; hour < count; hour++) {
    const hourNum = hour % 24;
    const hourStr = String(hourNum).padStart(2, '0');
    // Source timestamp format without timezone specification
    const timestamp = `2026-01-01 ${hourStr}:00:00`;
    const inflow = Math.round(150000000 + Math.sin(hour) * 40000000);
    const outflow = Math.round(140000000 + Math.cos(hour) * 35000000);
    const netFlow = inflow - outflow;

    items.push({
      step: hour,
      timestamp,
      interval: '1h',
      checking_cents: baseChecking + netFlow,
      required_reserve_cents: baseReserve,
      inflow_cents: inflow,
      outflow_cents: outflow,
      net_flow_cents: netFlow,
      tier1_repo_cents: 600000000,
      tier2_bonds_market_cents: 411000000,
      tier3_equities_market_cents: 222000000,
      overdraft_cents: 0,
    });
  }

  return { items };
}

/**
 * Multi-asset treasury recommendation fixtures.
 */
export const MOCK_MULTI_ASSET_DECISIONS = [
  {
    id: 'DEC-4T-001',
    action: 'INVEST_REPO',
    asset_tier: 1,
    instrument: 'Overnight Repo',
    amount_cents: 200000000,
    executed: false, // Explicit recommendation status
    rationale: ['Tier 0 cash exceeds 99% reserve threshold.', '17:00 entry window available for 5.25% overnight yield.'],
    estimated_yield_bps: 525,
    liquidity_impact: 'Accessible at 08:00 tomorrow or subject to 50 bps early-break fee.',
  },
  {
    id: 'DEC-4T-002',
    action: 'INVEST_BONDS',
    asset_tier: 2,
    instrument: 'Sovereign 10Y Bond',
    amount_cents: 150000000,
    executed: false,
    rationale: ['Surplus capital exceeds 3-day projected burn.', 'Attractive 4.45% YTM with duration hedge.'],
    estimated_yield_bps: 445,
    liquidity_impact: '2-day settlement liquidation subject to 200 bps market haircut.',
  },
  {
    id: 'DEC-4T-003',
    action: 'REBALANCE',
    asset_tier: 3,
    instrument: 'Growth Equities Index',
    amount_cents: 100000000,
    executed: true, // Confirmed trade execution
    rationale: ['Rebalancing Tier 3 equity gains to replenish Tier 0 liquid buffer.', 'Reduced equity risk ahead of anticipated volatility.'],
    realized_pnl_cents: 12500000,
    liquidity_impact: 'Immediate cash proceeds credited to Tier 0 checking.',
  },
  {
    id: 'DEC-4T-004',
    action: 'LIQUIDITY_WARNING',
    asset_tier: 0,
    instrument: 'Cash Buffer',
    amount_cents: 0,
    executed: false,
    rationale: ['Checking balance approaches 95% quantile minimum.', 'Recommend pausing Tier 1 sweeps and holding cash.'],
    liquidity_impact: 'Defensive cash posture required.',
  },
];

/**
 * Four-tier Strategy Arena benchmark comparison fixtures.
 */
export function getMockFourTierBacktestResults() {
  return {
    source: 'DETERMINISTIC_BENCHMARK_ENGINE',
    is_mock: true,
    benchmark_period_days: 7,
    interval: '1h',
    strategies: [
      {
        id: 'ALL_CASH',
        name: 'All Cash (Tier 0 Only)',
        color: '#86868b',
        ending_net_portfolio_cents: 2000000000,
        realized_yield_cents: 0,
        realized_pnl_cents: 0,
        unrealized_pnl_cents: 0,
        overdraft_costs_cents: 0,
        reserve_breaches: 0,
        capital_efficiency_score: '1.0x',
      },
      {
        id: 'CASH_PLUS_REPO',
        name: 'Cash + Repo (Tier 0 + Tier 1)',
        color: '#2997ff',
        ending_net_portfolio_cents: 2002100000,
        realized_yield_cents: 2100000,
        realized_pnl_cents: 0,
        unrealized_pnl_cents: 0,
        overdraft_costs_cents: 0,
        reserve_breaches: 0,
        capital_efficiency_score: '2.4x',
      },
      {
        id: 'FOUR_TIER_AUTOPILOT',
        name: 'Four-Tier Reserve Juggler',
        color: '#30d158',
        ending_net_portfolio_cents: 2005400000,
        realized_yield_cents: 2800000,
        realized_pnl_cents: 2600000,
        unrealized_pnl_cents: 3400000,
        overdraft_costs_cents: 0,
        reserve_breaches: 0,
        capital_efficiency_score: '4.8x',
      },
    ],
  };
}
