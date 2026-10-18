import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import portfolio from './fixtures/member1-portfolio.json';
import { canonicalPortfolio, canonicalOptimizer, canonicalHourlyForecast } from '../src/models/canonical';
import { formatDecimal, formatRateDecimal } from '../src/utils/precision';
import { previewLiquidityShock } from '../src/mocks/liquidityPreview';
import PortfolioInspector from '../src/components/PortfolioInspector';
import StressMatrix from '../src/components/StressMatrix';
import ArenaAnalytics from '../src/components/ArenaAnalytics';

// Portfolio copied verbatim from Member 1 14a8d72, canonical_liquidity_portfolio.json.
// Optimizer below is a minimal frontend boundary test fixture, not a measured engine run.
const recommendation = () => ({
  recommendation_only: true, execution_status: 'NOT_EXECUTED', search_truncated: false,
  summary_action: 'INVEST', model_version: 'boundary-test', policy_version: 'test-policy',
  estimated_income_cents: 10, estimated_price_change_cents: -5, modeled_financing_cost_cents: 3,
  decision: { run_id: portfolio.run_id, as_of: portfolio.as_of, time_basis: portfolio.time_basis,
    recommendation_only: true, execution_status: 'NOT_EXECUTED', feasible: true,
    reason: 'Supplied reserve is protected.', reserve: { required_reserve_cents: 100000 },
    explanations: ['Expected returns are estimates.'], orders: [{ id: 'test-order', action: 'INVEST_REPO', tier: 1,
      amount_cents: 50000, recommendation_only: true, execution_status: 'NOT_EXECUTED', reason: 'Illustrative surplus allocation.' }] },
});

describe('RJ-M1-14 frontend boundary', () => {
  it('accepts the actual Member 1 portfolio without converting decimals or hourly timestamps', () => {
    expect(canonicalPortfolio(portfolio)).toBe(portfolio);
    expect(portfolio.as_of).toBe('2026-01-01T17:00:00');
    expect(portfolio.repo_positions[0].applicable_apy_pct).toBe('4.308');
  });
  it('rejects unsafe nested money and an unreconciled net valuation', () => {
    const unsafe = structuredClone(portfolio); unsafe.bond_positions[0].current_market_value_cents = Number.MAX_SAFE_INTEGER + 1;
    expect(() => canonicalPortfolio(unsafe)).toThrow(/safe integer/);
    const wrong = structuredClone(portfolio); wrong.valuation.net_portfolio_value_cents += 1;
    expect(() => canonicalPortfolio(wrong)).toThrow(/reconcile/);
  });
  it('rejects fabricated UTC source labels, recommendation fills and another run’s result', () => {
    expect(() => canonicalPortfolio({ ...portfolio, as_of: `${portfolio.as_of}Z` })).toThrow(/time_basis/);
    const result = recommendation(); result.decision.orders[0].execution_status = 'EXECUTED';
    expect(() => canonicalOptimizer(result, portfolio)).toThrow(/execution receipt/);
    const other = recommendation(); other.decision.run_id = 'other-run';
    expect(() => canonicalOptimizer(other, portfolio)).toThrow(/provenance/);
  });
  it('formats decimal strings with half-up rounding without binary float loss or unit guessing', () => {
    expect(formatDecimal('9007199254740993.125', 2)).toBe('9,007,199,254,740,993.13');
    expect(formatDecimal('-1.005', 2)).toBe('-1.01');
    expect(formatRateDecimal('4.292', 3)).toBe('4.292%');
    expect(formatRateDecimal(50, 2, 'bps')).toBe('0.50%');
    expect(formatRateDecimal('75', 2)).toBe('75.00%');
  });
  it('keeps forecast derived net separate from independent source net and has no invented interval', () => {
    const forecast = { time_basis: 'UNSPECIFIED', net_flow_target: 'deposits_minus_withdrawals', points: [{
      start_at: portfolio.as_of, predicted_deposits_cents: 100, predicted_withdrawals_cents: 150,
      predicted_net_flow_cents: -50, supplied_uncertainty_buffer_cents: 20 }] };
    expect(canonicalHourlyForecast(forecast).points[0]).not.toHaveProperty('upper_cents');
    expect(canonicalHourlyForecast(forecast).points[0]).not.toHaveProperty('net_flow_usd');
  });
  it('shows supplied positions and unexecuted orders without regulatory or realized-return claims', () => {
    render(<PortfolioInspector snapshot={{ portfolio, optimizer_result: recommendation() }} />);
    expect(screen.getByText('4.308%')).toBeInTheDocument();
    expect(screen.getByText('NOT EXECUTED')).toBeInTheDocument();
    expect(screen.getByText('Unknown')).toBeInTheDocument();
    expect(screen.queryByText(/Basel III|118.5%|Confirmed Executed/)).not.toBeInTheDocument();
  });
  it('shows an unavailable state in LIVE mode instead of accepting mock financial data', () => {
    render(<PortfolioInspector mode="real" snapshot={{ four_tier: {} }} />);
    expect(screen.getByText('Awaiting canonical portfolio data')).toBeInTheDocument();
    expect(screen.queryByText('Mock · Compatibility model')).not.toBeInTheDocument();
  });
  it('never fabricates Monte Carlo risk or a winning strategy in advanced panels', () => {
    render(<><StressMatrix snapshot={{ checking_cents: 0, vault_locked_cents: 0, vault_redeemable_cents: 0 }} /><ArenaAnalytics results={[{ strategy: 'STATIC_RESERVE', net_benefit_cents: -100, failed_payouts: 2 }]} /></>);
    expect(screen.getByText('Risk result not supplied')).toBeInTheDocument();
    expect(screen.getByText('-$1.00')).toBeInTheDocument();
    expect(screen.queryByText(/99.99%|Winner|2.45/)).not.toBeInTheDocument();
  });
});

describe('landing liquidity illustration', () => {
  it.each([-1500000000, -600000000, 0, 1500000000])('conserves cash for shock %i and keeps allocation unexecuted', (shock) => {
    const result = previewLiquidityShock(shock);
    expect(result.checking_cents).toBe(result.opening_cash_cents + shock);
    expect(result.proposed_allocation_cents).toBe(Math.max(0, result.checking_cents - result.required_reserve_cents));
    expect(result.execution_status).toBe('NOT_EXECUTED');
    expect(result).toEqual(previewLiquidityShock(shock));
  });
  it('shows a reserve shortfall under severe stress and never changes cash between policies', () => {
    const adaptive = previewLiquidityShock(-1500000000); const fixed = previewLiquidityShock(-1500000000, false);
    expect(adaptive.checking_cents).toBe(fixed.checking_cents);
    expect(adaptive.reserve_deficit_cents).toBeGreaterThan(0);
    expect(adaptive.proposed_allocation_cents).toBe(0);
  });
});
