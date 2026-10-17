import { useMemo, useState } from 'react';
import { ArrowDownToLine, ArrowRight, ChevronRight, Landmark } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useSimulation } from '../context/SimulationContext';
import { Alert, Badge, Button, Empty, Loading, Metric, Panel } from '../components/ui';
import { Allocation, AuditLog, DecisionCard, TransactionFeed, VaultPositions } from '../components/Treasury';
import { TimeChart } from '../components/Charts';
import { ScrollStory } from '../components/ScrollStory';
import LandingExperience from '../components/LandingExperience';
import { exportCsv, money, rate, utc } from '../utils/format';

export function StartState() {
  const { createRun, busy } = useSimulation();
  return <Panel className="welcome-panel"><div className="welcome-copy"><span className="eyebrow">INTELLIGENT TREASURY AUTOPILOT</span><h2>Every dollar.<br /><span>A little smarter.</span></h2><p>Create a simulation to begin monitoring treasury activity. Observe cash flows, test liquidity shocks, and compare reserve strategies in one workspace.</p><Button variant="primary" busy={busy} onClick={() => createRun()}>Create simulation <ArrowRight size={15} /></Button><div className="welcome-details"><span>$20M initial checking</span><span>5% vault rate</span><span>15-minute steps</span></div></div><div className="welcome-sculpture" aria-hidden="true"><div className="sculpture-monolith"><div className="monolith-face"><span className="monolith-logo">RJ</span><span className="monolith-caption">CAPITAL IN BALANCE</span></div><div className="monolith-pulse-ring" /></div></div></Panel>;
}

export default function TreasuryDashboard() {
  const sim = useSimulation(); const snapshot = sim.snapshot;
  const [windowHours, setWindowHours] = useState(6);
  const [chartView, setChartView] = useState('flows');
  const [horizon, setHorizon] = useState(1440);
  const chartData = useMemo(() => sim.history.slice(-windowHours * 4 - 1), [sim.history, windowHours]);
  const forecastData = useMemo(() => [
    ...sim.history.slice(-8).map((p) => ({ timestamp: p.timestamp, actual: p.net_flow_cents })),
    ...(sim.forecast?.points ?? []).slice(0, horizon / 15).map((p) => ({ timestamp: p.timestamp, predicted: p.predicted_net_cents, band: [p.lower_cents, p.upper_cents] })),
  ], [sim.history, sim.forecast, horizon]);
  const exportReport = () => exportCsv('reserve-juggler-snapshot.csv', ['source', 'run_id', 'seed', 'step', 'timestamp_utc', 'checking_cents', 'vault_locked_cents', 'vault_redeemable_cents', 'reserve_cents', 'realized_interest_cents', 'net_benefit_cents'], [[sim.mode, snapshot.run_id, snapshot.seed, snapshot.step, snapshot.timestamp, snapshot.checking_cents, snapshot.vault_locked_cents, snapshot.vault_redeemable_cents, snapshot.required_reserve_cents, snapshot.realized_interest_cents, snapshot.net_benefit_cents]]);
  return <div className={`page-content ${snapshot ? '' : 'landing-page'}`}>
    {snapshot && <div className="page-heading"><div><span className="eyebrow">Overview</span><h1>Treasury Command Center<span className="heading-period">.</span></h1><p>Capital, in focus.</p></div><Button variant="quiet" onClick={exportReport}><ArrowDownToLine size={15} />Export snapshot</Button></div>}
    {!snapshot ? sim.busy ? <Loading /> : <LandingExperience /> : <>
      <ScrollStory>
      <section id="position" className="story-section" aria-label="Liquidity overview"><div data-story-reveal>
      <div className="story-kicker"><span>01 / Position</span><span>Available liquidity</span></div>
      <div className="treasury-hero"><div className="hero-liquidity"><div className="hero-topline"><span>Checking balance</span><span className="snapshot-time"><span className="status-dot dot-green" />Confirmed {utc(snapshot.timestamp)} UTC</span></div><div className="hero-balance" title={money(snapshot.checking_cents)}>{money(snapshot.checking_cents, true)}</div><p className="hero-description">Ready when needed.</p><div className="hero-reserve-metrics"><Metric label="Required reserve" value={snapshot.required_reserve_cents} note={`${snapshot.policy?.risk_percentile ?? snapshot.forecast?.risk_percentile ?? '—'}% risk policy`} /><Metric label="Deployable surplus" value={snapshot.deployable_surplus_cents ?? '—'} note="After reserve and sweep constraints" /></div></div><Allocation snapshot={snapshot} hero /></div>
      <div className="metrics-grid supporting-metrics"><Metric label="Yield vault principal" value={snapshot.vault_locked_cents + snapshot.vault_redeemable_cents} note={`${money(snapshot.vault_locked_cents, true)} locked`} /><Metric label="Realized interest" value={snapshot.realized_interest_cents ?? '—'} note={`${money(snapshot.accrued_interest_cents)} accrued separately`} /><Metric label="Net financial benefit" value={snapshot.net_benefit_cents ?? '—'} note="Realized interest less financial costs" /></div>
      </div></section>
      {snapshot.alerts?.map((alert, index) => <Alert key={`${snapshot.step}-${index}`} tone={alert.severity === 'CRITICAL' ? 'danger' : alert.severity === 'WARNING' ? 'warning' : 'info'}>{alert.severity} — {alert.message}</Alert>)}
      <section id="intelligence" className="story-section" aria-label="Treasury intelligence"><div data-story-reveal>
      <div className="section-intro"><div><span className="eyebrow">02 / Intelligence</span><h2>Movement, made clear.</h2></div><span className="model-caption">{snapshot.forecast?.model_version ?? 'Model unavailable'}<br />{sim.mode === 'mock' ? 'Deterministic development model' : 'Backend forecasting model'}</span></div>
      <div className="dashboard-grid"><div className="dashboard-charts">
        <Panel title={chartView === 'flows' ? 'Cash-flow activity' : chartView === 'reserve' ? 'Liquidity & required reserve' : 'Realized yield history'} subtitle="Recorded simulation activity · USD" action={<div className="segmented" aria-label="History time window">{[1, 6, 24].map((hours) => <button key={hours} onClick={() => setWindowHours(hours)} className={windowHours === hours ? 'active' : ''} aria-pressed={windowHours === hours}>{hours}H</button>)}</div>}>
          <div className="chart-tabs">{[['flows', 'Cash flows'], ['reserve', 'Reserve coverage'], ['yield', 'Earned yield']].map(([key, label]) => <button key={key} onClick={() => setChartView(key)} className={chartView === key ? 'active' : ''}>{label}</button>)}</div>
          <TimeChart data={chartData} series={chartView === 'flows' ? [{ key: 'inflow_cents', name: 'Inflow', color: '#0071e3' }, { key: 'outflow_cents', name: 'Outflow', color: '#9b9ba1' }, { key: 'net_flow_cents', name: 'Net flow', color: '#bfc0c6', dashed: true }] : chartView === 'reserve' ? [{ key: 'checking_cents', name: 'Checking', color: '#0071e3' }, { key: 'required_reserve_cents', name: 'Reserve', color: '#c68b41', dashed: true }] : [{ key: 'realized_interest_cents', name: 'Realized yield', color: '#4c9185' }]} summary={chartView === 'flows' ? 'Actual inflows, funded outflows, and net external cash flow for the selected period.' : chartView === 'reserve' ? 'Confirmed checking compared with the required reserve at each step.' : 'Interest credited at maturity; accrued interest is excluded.'} />
          <div className="chart-legend">{(chartView === 'flows' ? [['#0071e3', 'Inflow'], ['#9b9ba1', 'Outflow'], ['#bfc0c6', 'Net flow']] : chartView === 'reserve' ? [['#0071e3', 'Checking'], ['#c68b41', 'Reserve']] : [['#4c9185', 'Realized yield']]).map(([color, label]) => <span key={label}><i style={{ background: color }} />{label}</span>)}</div>
        </Panel>
        <Panel title="Cash-flow outlook" subtitle={`${sim.forecast?.method ?? 'Unavailable'} · Forecast as of ${utc(sim.forecast?.as_of)} UTC`} action={<select className="compact-select" aria-label="Forecast horizon" value={horizon} onChange={(e) => setHorizon(Number(e.target.value))}><option value={15}>15 minutes</option><option value={30}>30 minutes</option><option value={60}>60 minutes</option><option value={1440}>24 hours</option></select>}>
          {!sim.forecast?.points?.length ? <Empty title="Forecast not available yet" /> : <TimeChart data={forecastData} forecast currentTime={snapshot.timestamp} height={205} series={[{ key: 'actual', name: 'Actual net flow', color: '#9da8b8' }, { key: 'predicted', name: 'Forecast net flow', color: '#0071e3', dashed: true }]} summary="Solid: observed net cash flow. Dashed: mock future net flow. Shaded: heuristic uncertainty interval, not a calibrated probability guarantee." />}
        </Panel>
      </div><div className="dashboard-aside"><DecisionCard snapshot={snapshot} /></div></div>
      </div></section>
      <section id="activity" className="story-section" aria-label="Treasury activity"><div data-story-reveal>
      <div className="section-intro activity-intro"><div><span className="eyebrow">03 / Activity</span><h2>The complete record.</h2></div><span className="model-caption">Confirmed transactions & position terms</span></div>
      <TransactionFeed transactions={sim.transactions} />
      <VaultPositions positions={snapshot.positions} />
      <AuditLog decisions={sim.decisions} />
      <div className="next-step"><div><span className="eyebrow">Built to be challenged</span><strong>Ready for the unexpected?</strong><span>Find out how your treasury responds under pressure.</span></div><Link to="/shock-lab">Explore Shock Lab <ChevronRight size={17} /></Link></div>
      </div></section>
      </ScrollStory>
    </>}
  </div>;
}
