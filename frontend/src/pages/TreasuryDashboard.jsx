import { useMemo, useRef, useState } from 'react';
import { ArrowDownToLine, ChevronRight } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useSimulation } from '../context/SimulationContext';
import { Alert, Button, Empty, Loading, Metric, Panel } from '../components/ui';
import { Allocation, AuditLog, DecisionCard, TransactionFeed, VaultPositions } from '../components/Treasury';
import { TimeChart } from '../components/Charts';
import FourTierPortfolio from '../components/FourTierPortfolio';
import SimulationStart from '../components/SimulationStart';
import { exportCsv, money, utc } from '../utils/format';
import '../components/DashboardTabs.css';

const DASHBOARD_TABS = [
  { id: 'overview', label: 'Overview', description: 'Your cash position and reserve at the current step.' },
  { id: 'portfolio', label: 'Portfolio', description: 'Inspect capital allocations, positions, and proposed orders.' },
  { id: 'forecasts', label: 'Forecasts', description: 'Review recorded cash flows and the available forecast.' },
  { id: 'activity', label: 'Activity', description: 'Check confirmed transactions and the decision record.' },
];

export function StartState() {
  return <SimulationStart />;
}

export default function TreasuryDashboard() {
  const sim = useSimulation(); const snapshot = sim.snapshot;
  const [windowHours, setWindowHours] = useState(6);
  const [chartView, setChartView] = useState('flows');
  const [horizon, setHorizon] = useState(1440);
  const [activeTab, setActiveTab] = useState('overview');
  const tabRefs = useRef([]);
  const handleTabKey = (event, index) => {
    const direction = event.key === 'ArrowRight' ? 1 : event.key === 'ArrowLeft' ? -1 : 0;
    if (!direction && event.key !== 'Home' && event.key !== 'End') return;
    event.preventDefault();
    const next = event.key === 'Home' ? 0 : event.key === 'End' ? DASHBOARD_TABS.length - 1 : (index + direction + DASHBOARD_TABS.length) % DASHBOARD_TABS.length;
    setActiveTab(DASHBOARD_TABS[next].id);
    tabRefs.current[next]?.focus();
  };
  const chartData = useMemo(() => sim.history.slice(-windowHours * 4 - 1), [sim.history, windowHours]);
  const forecastData = useMemo(() => [
    ...sim.history.slice(-8).map((p) => ({ timestamp: p.timestamp, actual: p.net_flow_cents })),
    ...(sim.forecast?.points ?? []).slice(0, horizon / 15).map((p) => ({ timestamp: p.timestamp, predicted: p.predicted_net_cents, band: [p.lower_cents, p.upper_cents] })),
  ], [sim.history, sim.forecast, horizon]);
  const exportReport = () => exportCsv('reserve-juggler-snapshot.csv', ['source', 'run_id', 'seed', 'step', 'timestamp_utc', 'checking_cents', 'vault_locked_cents', 'vault_redeemable_cents', 'reserve_cents', 'realized_interest_cents', 'net_benefit_cents'], [[sim.mode, snapshot.run_id, snapshot.seed, snapshot.step, snapshot.timestamp, snapshot.checking_cents, snapshot.vault_locked_cents, snapshot.vault_redeemable_cents, snapshot.required_reserve_cents, snapshot.realized_interest_cents, snapshot.net_benefit_cents]]);
  return <div className="page-content command-workspace">
    <div className="page-heading"><div><span className="eyebrow">Monitor your treasury</span><h1>Treasury Command Center<span className="heading-period">.</span></h1><p>{snapshot ? 'Review cash, reserves, and the latest simulation results.' : 'Choose your data to begin monitoring liquidity.'}</p></div>{snapshot && <Button variant="quiet" onClick={exportReport}><ArrowDownToLine size={15} />Export snapshot</Button>}</div>
    {!snapshot ? sim.busy ? <Loading /> : <StartState /> : <>
      {snapshot.alerts?.map((alert, index) => <Alert key={`${snapshot.step}-${index}`} tone={alert.severity === 'CRITICAL' ? 'danger' : alert.severity === 'WARNING' ? 'warning' : 'info'}>{alert.severity} — {alert.message}</Alert>)}
      <div className="dashboard-view-switcher">
        <div className="dashboard-tabs" role="tablist" aria-label="Command Center views">{DASHBOARD_TABS.map((tab, index) => <button key={tab.id} ref={(node) => { tabRefs.current[index] = node; }} id={`command-tab-${tab.id}`} type="button" role="tab" aria-selected={activeTab === tab.id} aria-controls={`command-panel-${tab.id}`} tabIndex={activeTab === tab.id ? 0 : -1} onClick={() => setActiveTab(tab.id)} onKeyDown={(event) => handleTabKey(event, index)}>{tab.label}</button>)}</div>
        <p className="dashboard-view-hint">{DASHBOARD_TABS.find((tab) => tab.id === activeTab).description}</p>
      </div>
      <section id="command-panel-overview" className="dashboard-tab-panel" role="tabpanel" aria-labelledby="command-tab-overview" tabIndex={0} hidden={activeTab !== 'overview'}>{activeTab === 'overview' && <div id="position">
      <div className="treasury-hero"><div className="hero-liquidity"><div className="hero-topline"><span>Checking balance (Instant Cash)</span><span className="snapshot-time"><span className="status-dot dot-green" />Confirmed {utc(snapshot.timestamp)} UTC</span></div><div className="hero-balance" title={money(snapshot.checking_cents)}>{money(snapshot.checking_cents, true)}</div><p className="hero-description">Instant cash ready for daily payouts and operations.</p><div className="hero-reserve-metrics"><Metric label="Required reserve" value={snapshot.required_reserve_cents} note={`${snapshot.policy?.risk_percentile ?? snapshot.forecast?.risk_percentile ?? '—'}% safety buffer against shocks`} /><Metric label="Deployable surplus" value={snapshot.deployable_surplus_cents ?? '—'} note="Extra cash automatically swept into yield" /></div></div><Allocation snapshot={snapshot} hero /></div>
      <div className="metrics-grid supporting-metrics"><Metric label="Yield vault principal" value={snapshot.vault_locked_cents + snapshot.vault_redeemable_cents} note={`${money(snapshot.vault_locked_cents, true)} locked earning interest`} /><Metric label="Realized interest" value={snapshot.realized_interest_cents ?? '—'} note={`${money(snapshot.accrued_interest_cents)} accrued · Ready at maturity`} /><Metric label="Net financial benefit" value={snapshot.net_benefit_cents ?? '—'} note="Total net profit after subtracting all costs" /></div>
      <div className="dashboard-panel-next"><span>Ready to test this position?</span><Link to="/shock-lab">Open Liquidity Shock Lab <ChevronRight size={16} aria-hidden="true" /></Link></div>
      </div>}</section>
      <section id="command-panel-portfolio" className="dashboard-tab-panel" role="tabpanel" aria-labelledby="command-tab-portfolio" tabIndex={0} hidden={activeTab !== 'portfolio'}>{activeTab === 'portfolio' && <div id="four-tier-section">
      <div className="dashboard-panel-heading"><h2>Capital allocation</h2><p>Cash, repo, bonds, and equities.</p></div>
      <FourTierPortfolio snapshot={snapshot} mode={sim.mode} />
      </div>}</section>
      <section id="command-panel-forecasts" className="dashboard-tab-panel" role="tabpanel" aria-labelledby="command-tab-forecasts" tabIndex={0} hidden={activeTab !== 'forecasts'}>{activeTab === 'forecasts' && <div id="intelligence">
      <div className="dashboard-panel-heading"><h2>Cash flows & forecasts</h2><p>{snapshot.forecast?.model_version ?? 'Model unavailable'} · {sim.mode === 'mock' ? 'Deterministic development model' : 'Backend forecasting model'}</p></div>
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
      </div>}</section>
      <section id="command-panel-activity" className="dashboard-tab-panel" role="tabpanel" aria-labelledby="command-tab-activity" tabIndex={0} hidden={activeTab !== 'activity'}>{activeTab === 'activity' && <div id="activity">
      <div className="dashboard-panel-heading"><h2>Transactions & decisions</h2><p>Recorded activity and the terms of each position.</p></div>
      <TransactionFeed transactions={sim.transactions} />
      <VaultPositions positions={snapshot.positions} />
      <AuditLog decisions={sim.decisions} />
      </div>}</section>
    </>}
  </div>;
}
