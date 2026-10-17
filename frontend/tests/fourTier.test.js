import { describe, expect, it } from 'vitest';
import {
  createTier0Cash,
  createTier1Repo,
  createTier2Bonds,
  createTier3Equities,
  createOverdraft,
  createFourTierPortfolio,
  REPO_RULES,
  BOND_RULES,
  EQUITY_RULES,
} from '../src/models/fourTier';
import {
  formatDecimal,
  parseDecimalString,
  formatRateDecimal,
  formatSourceTimestamp,
} from '../src/utils/precision';
import {
  getMockFourTierSnapshot,
  getMockHourlyHistory,
  MOCK_MULTI_ASSET_DECISIONS,
  getMockFourTierBacktestResults,
} from '../src/mocks/fourTierFixtures';
import { createMockApi } from '../src/api/mockTreasuryApi';
import { validateFourTierPortfolio } from '../src/api/validation';

describe('TASK F1A — Four-Tier Frontend Financial Models & Precision', () => {
  describe('Tier 0 — Cash Buffer', () => {
    it('correctly calculates surplus, deficit, and immediate liquidity', () => {
      const cash = createTier0Cash({
        checking_cents: 2000000000,
        required_reserve_cents: 450000000,
      });

      expect(cash.tier).toBe(0);
      expect(cash.checking_cents).toBe(2000000000);
      expect(cash.required_reserve_cents).toBe(450000000);
      expect(cash.deployable_surplus_cents).toBe(1550000000);
      expect(cash.reserve_deficit_cents).toBe(0);
      expect(cash.immediate_liquidity_cents).toBe(2000000000);
      expect(cash.status).toBe('SURPLUS');
    });

    it('identifies reserve deficits when cash falls below required buffer', () => {
      const deficitCash = createTier0Cash({
        checking_cents: 300000000,
        required_reserve_cents: 450000000,
      });

      expect(deficitCash.deployable_surplus_cents).toBe(0);
      expect(deficitCash.reserve_deficit_cents).toBe(150000000);
      expect(deficitCash.status).toBe('DEFICIT');
    });

    it('handles missing or zero values safely', () => {
      const emptyCash = createTier0Cash();
      expect(emptyCash.checking_cents).toBe(0);
      expect(emptyCash.required_reserve_cents).toBe(0);
      expect(emptyCash.deployable_surplus_cents).toBe(0);
      expect(emptyCash.status).toBe('BALANCED');
    });
  });

  describe('Tier 1 — Overnight Repo', () => {
    it('enforces locked status and calculates 50 bps early break fee', () => {
      const repo = createTier1Repo({
        principal_cents: 600000000,
        repo_apy_bps: 520,
        status: 'LOCKED',
        early_redemption_allowed: true,
        early_break_fee_bps: 50,
      });

      expect(repo.tier).toBe(1);
      expect(repo.status).toBe('LOCKED');
      expect(repo.early_break_fee_bps).toBe(50);
      // 50 bps of $6M = $30,000 (3,000,000 cents)
      expect(repo.break_fee_cents).toBe(3000000);
      expect(repo.net_redeemable_cents).toBe(597000000);
      expect(repo.entry_time).toBe('17:00');
      expect(repo.maturity_time).toBe('08:00');
    });

    it('returns full principal plus accrued interest upon maturity without penalty', () => {
      const maturedRepo = createTier1Repo({
        principal_cents: 600000000,
        accrued_interest_cents: 85479,
        status: 'MATURED',
      });

      expect(maturedRepo.break_fee_cents).toBe(0);
      expect(maturedRepo.net_redeemable_cents).toBe(600085479);
    });

    it('withholds liquidity if early redemption is forbidden while locked', () => {
      const lockedRepo = createTier1Repo({
        principal_cents: 600000000,
        status: 'LOCKED',
        early_redemption_allowed: false,
      });

      expect(lockedRepo.net_redeemable_cents).toBe(0);
      expect(lockedRepo.immediate_liquidity_cents).toBe(0);
    });
  });

  describe('Tier 2 — Sovereign Bonds (Market Valuation, Losses, & Liquidation Haircut)', () => {
    it('calculates mark-to-market unrealized gains and 2% liquidation haircut', () => {
      const bond = createTier2Bonds({
        notional_cents: 400000000,
        acquisition_price: '98.5000',
        current_price: '101.2500',
        market_value_cents: 411167512,
        liquidation_haircut_bps: 200,
      });

      expect(bond.tier).toBe(2);
      expect(bond.market_value_cents).toBe(411167512);
      expect(bond.unrealized_pnl_cents).toBeGreaterThan(0);
      // 2.0% haircut on $4,111,675.12
      expect(bond.haircut_cents).toBe(Math.round((411167512 * 200) / 10000));
      expect(bond.available_liquidity_cents).toBe(bond.market_value_cents - bond.haircut_cents);
      expect(bond.modified_duration).toBe(4.25);
    });

    it('correctly records negative mark-to-market P&L during bond price declines', () => {
      const distressedBond = createTier2Bonds({
        notional_cents: 400000000,
        acquisition_price: '100.0000',
        current_price: '92.5000',
        market_value_cents: 370000000,
        unrealized_pnl_cents: -30000000, // -$300,000 loss
      });

      expect(distressedBond.unrealized_pnl_cents).toBe(-30000000);
      expect(distressedBond.market_value_cents).toBeLessThan(distressedBond.notional_cents);
    });
  });

  describe('Tier 3 — Growth Equities (Volatility, P&L, & Emergency Slippage)', () => {
    it('applies 15% emergency slippage penalty for available liquidation cash', () => {
      const equities = createTier3Equities({
        market_value_cents: 200000000, // $2,000,000
        cost_basis_cents: 180000000,
        emergency_slippage_bps: 1500,  // 15%
        unrealized_pnl_cents: 20000000,
      });

      expect(equities.tier).toBe(3);
      expect(equities.market_value_cents).toBe(200000000);
      expect(equities.unrealized_pnl_cents).toBe(20000000);
      // 15% slippage on $2M = $300,000 (30,000,000 cents)
      expect(equities.slippage_cents).toBe(30000000);
      expect(equities.available_liquidity_cents).toBe(170000000);
      expect(equities.volatility_bps).toBe(1650);
    });

    it('handles negative equity market crash P&L', () => {
      const crashedEquities = createTier3Equities({
        cost_basis_cents: 200000000,
        market_value_cents: 140000000,
        unrealized_pnl_cents: -60000000, // -$600,000 crash
      });

      expect(crashedEquities.unrealized_pnl_cents).toBe(-60000000);
      expect(crashedEquities.market_value_cents).toBe(140000000);
    });
  });

  describe('Emergency Overdraft Liabilities', () => {
    it('maps outstanding borrowing liability and 10% financing rate', () => {
      const overdraft = createOverdraft({
        borrowing_outstanding_cents: 50000000, // $500,000 liability
        financing_rate_bps: 1000,
        financing_cost_cents: 125000,
      });

      expect(overdraft.borrowing_outstanding_cents).toBe(50000000);
      expect(overdraft.financing_rate_bps).toBe(1000);
      expect(overdraft.financing_cost_cents).toBe(125000);
      expect(overdraft.liability_status).toBe('ACTIVE');
      expect(overdraft.is_active).toBe(true);
    });

    it('marks cleared liability status when borrowing is zero', () => {
      const cleared = createOverdraft({ borrowing_outstanding_cents: 0 });
      expect(cleared.liability_status).toBe('CLEARED');
      expect(cleared.is_active).toBe(false);
    });
  });

  describe('Portfolio Aggregation', () => {
    it('accurately computes gross assets, net portfolio value, and liquidity', () => {
      const portfolio = createFourTierPortfolio({
        tier0: createTier0Cash({ checking_cents: 2000000000, required_reserve_cents: 450000000 }),
        tier1: createTier1Repo({ principal_cents: 600000000 }),
        tier2: createTier2Bonds({ market_value_cents: 400000000, notional_cents: 400000000 }),
        tier3: createTier3Equities({ market_value_cents: 200000000 }),
        overdraft: createOverdraft({ borrowing_outstanding_cents: 50000000 }),
      });

      const agg = portfolio.aggregates;
      // Gross: 20M + 6M + 4M + 2M = 32M = 3,200,000,000 cents
      expect(agg.gross_assets_cents).toBe(3200000000);
      expect(agg.total_liabilities_cents).toBe(50000000);
      // Net: 32M - 0.5M = 31.5M = 3,150,000,000 cents
      expect(agg.net_portfolio_value_cents).toBe(3150000000);
      // Liquid: Tier 0 cash (20M) + Tier 1 net (5.97M) + Tier 2 after haircut (3.92M) + Tier 3 after slippage (1.7M)
      expect(agg.total_immediate_liquidity_cents).toBeGreaterThan(3100000000);
      expect(agg.total_immediate_liquidity_cents).toBeLessThan(agg.gross_assets_cents);
    });
  });
});

describe('Precision, Decimal Formatting & Time Invariants', () => {
  it('formats decimals preserving exact string precision without float drift', () => {
    expect(formatDecimal('101.2500', 4)).toBe('101.2500');
    expect(formatDecimal(445.5, 2)).toBe('445.50');
    expect(formatDecimal(null)).toBe('—');
  });

  it('formats decimal percentages without truncating to integer bps', () => {
    expect(formatRateDecimal('5.2500')).toBe('5.25%');
    expect(formatRateDecimal(525)).toBe('5.25%');
    expect(formatRateDecimal(null)).toBe('—');
  });

  it('preserves timezone-unspecified hourly historical timestamps', () => {
    // Organizer source format without timezone
    const sourceTs = '2026-01-01 17:00:00';
    const formatted = formatSourceTimestamp(sourceTs, true);
    expect(formatted).toContain('17:00');
    expect(formatted).not.toContain('UTC'); // Must not fabricate UTC suffix for source time
  });

  it('preserves ISO UTC timestamps when explicit Z suffix is supplied', () => {
    const utcTs = '2026-10-17T08:00:00.000Z';
    const formatted = formatSourceTimestamp(utcTs, true);
    expect(formatted).toContain('08:00 UTC');
  });
});

describe('Deterministic Mock Adapter & Multi-Asset Recommendations', () => {
  it('distinguishes recommendations from executed trades', () => {
    const recommendation = MOCK_MULTI_ASSET_DECISIONS.find((d) => d.action === 'INVEST_REPO');
    const executedTrade = MOCK_MULTI_ASSET_DECISIONS.find((d) => d.action === 'REBALANCE');

    expect(recommendation.executed).toBe(false);
    expect(executedTrade.executed).toBe(true);
  });

  it('generates native hourly historical timeline without synthesizing 15-minute steps', () => {
    const history = getMockHourlyHistory(24);
    expect(history.items).toHaveLength(24);
    expect(history.items[0].interval).toBe('1h');
    expect(history.items[0].timestamp).toMatch(/2026-01-01 00:00:00/);
    expect(history.items[1].timestamp).toMatch(/2026-01-01 01:00:00/);
  });

  it('provides deterministic four-tier strategy arena backtest results', () => {
    const backtest = getMockFourTierBacktestResults();
    expect(backtest.strategies).toHaveLength(3);
    const rj = backtest.strategies.find((s) => s.id === 'FOUR_TIER_AUTOPILOT');
    expect(rj.capital_efficiency_score).toBe('4.8x');
    expect(rj.ending_net_portfolio_cents).toBeGreaterThan(2000000000);
  });

  it('provides four-tier snapshot and validates with validateFourTierPortfolio', async () => {
    const api = createMockApi({ latency: 0 });
    const { run_id } = await api.createRun();
    const fourTier = await api.getFourTierSnapshot(run_id);

    expect(fourTier).toBeDefined();
    expect(fourTier.tier0.checking_cents).toBeGreaterThan(0);
    expect(fourTier.tier1.principal_cents).toBeGreaterThan(0);
    expect(() => validateFourTierPortfolio(fourTier)).not.toThrow();
  });
});
