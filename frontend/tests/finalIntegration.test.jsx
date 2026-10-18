import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { createRealApi, flattenBacktestMetrics } from '../src/api/treasuryApi';
import PortfolioInspector from '../src/components/PortfolioInspector';
afterEach(() => vi.unstubAllGlobals());
describe('final real runtime integration', () => {
  it('creates a separate hourly parent with the selected scenario, capital and seed', async () => {
    const fetch = vi.fn().mockImplementation(async () => new Response(JSON.stringify({run_id:'new-parent', results:[]})));
    vi.stubGlobal('fetch', fetch);
    await createRealApi('http://127.0.0.1:8017').runBacktest('live-parent', {days:7, seed:42, scenario:'NORMAL'});
    expect(fetch.mock.calls[0][0]).toBe('http://127.0.0.1:8017/api/v1/runs');
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toMatchObject({duration_steps:168, initial_cash_cents:2000000000, scenario:'NORMAL', seed:42, start_time:'2026-01-01T00:00:00Z'});
    expect(fetch.mock.calls[1][0]).toBe('http://127.0.0.1:8017/api/v1/runs/new-parent/backtest');
    expect(JSON.parse(fetch.mock.calls[1][1].body)).toMatchObject({days:7, retain_runs:true});
  });
  it('maps a persisted repo debit to an outgoing cash transaction', async () => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation(async () => new Response(JSON.stringify({items:[{transaction_id:'ledger',source:'OVERNIGHT_REPO_SWEEP_DEBIT',direction:'INFLOW',amount_cents:100}]}))));
    const data=await createRealApi().getTransactions('run');
    expect(data.items[0]).toMatchObject({id:'ledger',direction:'OUTFLOW',amount_cents:100});
  });
  it('keeps persisted child identities and negative financial results', () => {
    expect(flattenBacktestMetrics({child_run_ids:{STATIC_RESERVE:'child'},results:[{strategy:'STATIC_RESERVE',metrics:{net_benefit_cents:-19}}]}).results[0]).toMatchObject({run_id:'child',strategy:'STATIC',net_benefit_cents:-19});
  });
  it('displays only supplied real v1 balances and debt', () => {
    const four_tier={tier0:{checking_cents:100},tier1:{principal_cents:200},tier2:{market_value_cents:300},tier3:{market_value_cents:400},overdraft:{financing_cost_cents:3},aggregates:{required_reserve_cents:50,total_immediate_liquidity_cents:100,gross_assets_cents:1000,total_liabilities_cents:25,net_portfolio_value_cents:975},publication_delay_seconds:3600};
    render(<PortfolioInspector mode="real" snapshot={{four_tier}} />);
    expect(screen.getByText('$9.75')).toBeInTheDocument();
    expect(screen.getByText('$0.25')).toBeInTheDocument();
    expect(screen.getByText(/UNSPECIFIED/)).toBeInTheDocument();
    expect(screen.queryByText('Awaiting canonical portfolio data')).not.toBeInTheDocument();
  });
});
