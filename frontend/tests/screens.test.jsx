import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { SimulationProvider, useSimulation } from '../src/context/SimulationContext';
import { createMockApi } from '../src/api/mockTreasuryApi';
import { AppRoutes } from '../src/App';
import { DecisionCard, TransactionFeed } from '../src/components/Treasury';
import ModelEvaluation from '../src/components/ModelEvaluation';

vi.mock('../src/components/Charts', () => ({
  TimeChart: ({ summary, series }) => <div role="img" aria-label={summary}>{series?.map((s) => s.name).join(', ')}</div>,
  ComparisonBars: ({ summary }) => <div role="img" aria-label={summary} />,
}));

function renderApp(api = createMockApi({ latency: 0 }), path = '/') {
  const user = userEvent.setup();
  render(<MemoryRouter initialEntries={[path]}><SimulationProvider api={api}><AppRoutes /></SimulationProvider></MemoryRouter>);
  return { user, api };
}
async function start(user) {
  await user.click(screen.getAllByRole('button', { name: /create simulation/i })[0]);
  await screen.findByRole('button', { name: 'Advance one step' });
}

describe('three-screen frontend workflow', () => {
  it('opens the mobile navigation with keyboard focus and closes on Escape', async () => {
    const { user } = renderApp();
    const opener = screen.getByRole('button', { name: 'Open navigation' });
    await user.click(opener);
    expect(screen.getByRole('button', { name: 'Close navigation' })).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByRole('link', { name: 'Command Center', exact: true })).toHaveFocus();
    await user.keyboard('{Shift>}{Tab}{/Shift}');
    expect(screen.getByRole('button', { name: 'Close navigation' })).toHaveFocus();
    await user.keyboard('{Escape}');
    expect(screen.getByRole('button', { name: 'Open navigation' })).toHaveFocus();
    expect(document.querySelector('.workspace-main')).not.toHaveAttribute('inert');
  });
  it('loads the exact API balances and distinguishes actual from forecast', async () => {
    const { user } = renderApp(); await start(user);
    expect(screen.getByTitle('$20,000,000.00')).toBeInTheDocument();
    expect(screen.getByText('Realized interest')).toBeInTheDocument();
    expect(screen.getByRole('img', { name: /Solid: observed/ })).toHaveTextContent('Actual net flow, Forecast net flow');
    expect(screen.getByText(/Mock environment/)).toBeInTheDocument();
  });
  it('schedules HIGH_WITHDRAWAL then observes two real snapshots and compares strategies', async () => {
    const { user, api } = renderApp(); const scenarioSpy = vi.spyOn(api, 'applyScenario');
    const originalBacktest = api.runBacktest; let finishBacktest;
    vi.spyOn(api, 'runBacktest').mockImplementation(async (...args) => {
      await new Promise((resolve) => { finishBacktest = resolve; });
      return originalBacktest(...args);
    });
    await start(user); await user.click(screen.getByRole('link', { name: 'Liquidity Shock Lab' }));
    await user.click(screen.getByRole('button', { name: 'Trigger scenario' }));
    await screen.findByText(/Shock scheduled — advance simulation/);
    expect(scenarioSpy).toHaveBeenCalledWith(expect.any(String), expect.objectContaining({ scenario: 'HIGH_WITHDRAWAL', parameters: expect.objectContaining({ multiplier_bps: 30000 }) }), expect.any(Object));
    await user.click(screen.getByRole('button', { name: 'Advance one step' }));
    await screen.findByText('Event observed');
    expect(screen.queryByText(/Shock scheduled — advance simulation/)).not.toBeInTheDocument();
    await user.click(screen.getByRole('link', { name: 'Strategy Arena' }));
    await user.click(screen.getByRole('button', { name: /Run strategy comparison/ }));
    expect(screen.getByText('Loading confirmed simulation state…')).toBeInTheDocument();
    expect(screen.queryByText('7-day treasury outcomes')).not.toBeInTheDocument();
    await act(async () => { finishBacktest(); });
    await screen.findByText('7-day treasury outcomes', {}, { timeout: 15000 });
    expect(screen.getByRole('cell', { name: 'Net financial benefit', exact: true })).toBeInTheDocument();
    expect(screen.getByText('Model evaluation not available')).toBeInTheDocument();
    expect(screen.getByText(/not measured project or ML performance/)).toBeInTheDocument();
  }, 20000);
  it('applies validated policy fields and displays the accepted confidence', async () => {
    const { user, api } = renderApp(); const spy = vi.spyOn(api, 'updatePolicy');
    await start(user); await user.click(screen.getByRole('link', { name: 'Liquidity Shock Lab' }));
    await user.selectOptions(screen.getByLabelText('Risk percentile'), '99');
    await user.click(screen.getByRole('button', { name: /Apply policy/ }));
    await screen.findByText('Active confidence: 99%');
    expect(spy).toHaveBeenCalledWith(expect.any(String), expect.objectContaining({ risk_percentile: 99, operational_buffer_cents: 50000000 }), expect.any(Object));
  });
  it('shows network errors and never substitutes demo success in real mode', async () => {
    const api = { ...createMockApi({ latency: 0 }), mode: 'real', health: vi.fn().mockRejectedValue(new Error('Backend unavailable')) };
    const { user } = renderApp(api);
    await user.click(screen.getAllByRole('button', { name: /Create simulation/ })[0]);
    expect(await screen.findByRole('alert')).toHaveTextContent('Backend unavailable');
    expect(screen.queryByTitle('$20,000,000.00')).not.toBeInTheDocument();
  });
});

describe('decision accuracy and transaction direction', () => {
  const base = { timestamp: '2026-10-17T08:15:00Z', amount_cents: 500000000, pre_checking_cents: 2000000000, post_checking_cents: 1500000000, explanation: ['An API-provided rationale.'] };
  it.each(['HOLD', 'SWEEP', 'WITHDRAW', 'LIQUIDITY_WARNING'])('renders %s and keeps recommendations separate from execution', (action) => {
    render(<DecisionCard snapshot={{ decision: { ...base, action, executed: false }, forecast: {} }} />);
    expect(screen.getByText(action.replaceAll('_', ' '))).toBeInTheDocument();
    expect(screen.getByText('Recommended · not executed')).toBeInTheDocument();
    expect(screen.queryByText('Executed')).not.toBeInTheDocument();
  });
  it('shows confirmed execution and an early-redemption penalty', () => {
    render(<DecisionCard snapshot={{ decision: { ...base, action: 'WITHDRAW', executed: true, penalty_cents: 250000 }, forecast: {} }} />);
    expect(screen.getByText('Executed')).toBeInTheDocument(); expect(screen.getByText('Redemption penalty: $2,500.00')).toBeInTheDocument();
  });
  it('does not double-count uncertainty for scenario-quantile reserves', () => {
    render(<DecisionCard snapshot={{ decision: { ...base, action: 'HOLD', executed: false, risk_method: 'SCENARIO_QUANTILE', quantile_shortfall_cents: 500000, uncertainty_buffer_cents: 100000 }, forecast: {} }} />);
    expect(screen.getByText('Scenario percentile shortfall')).toBeInTheDocument(); expect(screen.queryByText('Uncertainty buffer')).not.toBeInTheDocument();
  });
  it('colors and signs settlements using direction, not type', () => {
    render(<TransactionFeed transactions={[
      { id: 'in', type: 'MERCHANT_SETTLEMENT', direction: 'INFLOW', amount_cents: 10000, source: 'Incoming settlement', timestamp: base.timestamp },
      { id: 'out', type: 'MERCHANT_SETTLEMENT', direction: 'OUTFLOW', amount_cents: 20000, source: 'Outgoing settlement', timestamp: base.timestamp },
    ]} />);
    expect(screen.getByText('+$100.00')).toHaveClass('positive'); expect(screen.getByText('−$200.00')).not.toHaveClass('positive');
  });
  it('displays supplied model measurements even when ML is worse', () => {
    render(<ModelEvaluation evaluation={{ baseline: { model_version: 'base-1', mae_cents: 10000, rmse_cents: 15000 }, ml: { model_version: 'ml-1', mae_cents: 12000, rmse_cents: 17000 }, sample_count: 100, started_at: '2026-10-01T00:00:00Z', ended_at: '2026-10-02T00:00:00Z' }} />);
    expect(screen.getByText('−20.0% MAE improvement')).toBeInTheDocument();
    expect(screen.getByText('$120.00')).toBeInTheDocument();
  });
  it('preserves zero in measured model errors', () => {
    render(<ModelEvaluation evaluation={{ baseline: { mae_cents: 0, rmse_cents: 0 }, ml: { mae_cents: 0, rmse_cents: 0 }, sample_count: 20 }} />);
    expect(screen.getAllByText('$0.00')).toHaveLength(4);
    expect(screen.queryByText(/MAE improvement/)).not.toBeInTheDocument();
  });
});

function Controls() {
  const sim = useSimulation();
  return <><button onClick={() => sim.createRun()}>Initialize</button><button onClick={sim.advance}>Advance</button><button onClick={sim.play}>Play</button><button onClick={sim.pause}>Pause</button><output>{sim.snapshot?.step ?? 'none'}</output><span>{sim.notice}</span></>;
}
describe('playback concurrency', () => {
  it('allows only one in-flight advance for repeated clicks', async () => {
    const api = createMockApi({ latency: 15 }); const advance = vi.spyOn(api, 'advanceRun');
    render(<SimulationProvider api={api}><Controls /></SimulationProvider>);
    fireEvent.click(screen.getByText('Initialize')); await screen.findByText('0');
    fireEvent.click(screen.getByText('Advance')); fireEvent.click(screen.getByText('Advance'));
    await screen.findByText('1'); expect(advance).toHaveBeenCalledTimes(1);
  });
  it('reconciles a stale step without repeating the failed mutation', async () => {
    const api = createMockApi({ latency: 0 });
    vi.spyOn(api, 'advanceRun').mockRejectedValueOnce(Object.assign(new Error('stale'), { status: 409 }));
    render(<SimulationProvider api={api}><Controls /></SimulationProvider>);
    fireEvent.click(screen.getByText('Initialize')); await screen.findByText('0');
    fireEvent.click(screen.getByText('Advance'));
    await screen.findByText(/run advanced elsewhere/); expect(api.advanceRun).toHaveBeenCalledTimes(1);
  });
  it('pauses playback before the scheduled first advance', async () => {
    const api = createMockApi({ latency: 0 }); const advance = vi.spyOn(api, 'advanceRun');
    render(<SimulationProvider api={api}><Controls /></SimulationProvider>);
    fireEvent.click(screen.getByText('Initialize')); await screen.findByText('0');
    fireEvent.click(screen.getByText('Play')); fireEvent.click(screen.getByText('Pause'));
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 500)); });
    expect(advance).not.toHaveBeenCalled();
  });
});
