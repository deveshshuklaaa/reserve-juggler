import { useState } from 'react';
import { ArrowDownToLine, BarChart3, Check, FlaskConical, Trophy } from 'lucide-react';
import { useSimulation } from '../context/SimulationContext';
import { SCENARIOS, STRATEGIES } from '../mocks/constants';
import { exportCsv, money } from '../utils/format';
import { Alert, Badge, Button, Empty, Field, Loading, Panel } from '../components/ui';
import { ComparisonBars, TimeChart } from '../components/Charts';
import { StartState } from './TreasuryDashboard';
import ModelEvaluation from '../components/ModelEvaluation';
import ArenaAnalytics from '../components/ArenaAnalytics';

const metrics = [
  ['Realized interest', 'realized_interest_cents', true], ['Average checking / idle cash', 'average_checking_cents', true],
  ['Early redemption penalties', 'penalties_cents', true], ['Emergency borrowing costs', 'borrowing_costs_cents', true],
  ['Outstanding borrowing', 'borrowing_outstanding_cents', true], ['Reserve breaches', 'reserve_breaches', false],
  ['Emergency funding events', 'emergency_events', false], ['Failed payouts', 'failed_payouts', false],
  ['Vault sweeps', 'sweeps', false], ['Net financial benefit', 'net_benefit_cents', true],
];

function ArenaContent() {
  const sim = useSimulation();
  const imported = sim.snapshot.input_source?.type === 'CSV';
  const [scenario, setScenario] = useState('HIGH_WITHDRAWAL');
  const [days, setDays] = useState(7); const [seed, setSeed] = useState(2026);
  const [strategies, setStrategies] = useState(STRATEGIES.map((item) => item.id));
  const [pending, setPending] = useState(false);
  const [error, setError] = useState(''); const [criterion, setCriterion] = useState('net_benefit_cents');
  const comparison = sim.comparison; const results = comparison?.status === 'COMPLETED' ? comparison.results ?? [] : [];
  const submit = async (event) => {
    event.preventDefault(); setError('');
    if (!strategies.length) return setError('Select at least one strategy.');
    setPending(true);
    try { await sim.runComparison({ scenario, days, seed, strategies }); } finally { setPending(false); }
  };
  const ranked = [...results].sort((a, b) => criterion === 'net_benefit_cents' ? b[criterion] - a[criterion] : a[criterion] - b[criterion]);
  const leaders = ranked.length ? ranked.filter((item) => item[criterion] === ranked[0][criterion]) : [];
  const chartData = results.map((item) => ({ ...item, name: STRATEGIES.find((s) => s.id === item.strategy)?.name ?? item.strategy }));
  const timeline = results[0]?.history?.map((point, index) => ({ timestamp: point.timestamp,
    ...Object.fromEntries(results.map((item) => [item.strategy, item.history?.[index]?.checking_cents])),
  })) ?? [];
  const exportResults = () => exportCsv('reserve-juggler-strategies.csv', ['source', 'run_id', 'scenario', 'seed', 'days', 'duration_steps', 'input_type', 'strategy', ...metrics.map((item) => item[1])], results.map((result) => [sim.mode, sim.snapshot.run_id, comparison.scenario, comparison.seed, comparison.days, result.duration_steps, comparison.input_source?.type ?? 'GENERATED', result.strategy, ...metrics.map(([, key]) => result[key])]));
  return <>
    <Panel className="arena-config" title="Design a fair comparison" subtitle={imported ? 'Replay the complete imported dataset with identical opening capital and policy for every strategy. Shock Lab overlays are excluded.' : 'Compare strategies under identical seeded cash flows and starting capital.'}>
      <form onSubmit={submit}><div className="arena-form-grid">{imported ? <><Field label="Cash-flow source"><input readOnly value="Imported CSV · original flows" /></Field><Field label="Replay horizon"><input readOnly value={`${sim.snapshot.input_source.row_count} observations · ${sim.snapshot.duration_steps} steps`} /></Field><Field label="Random seed"><input readOnly value={sim.snapshot.seed} /></Field></> : <><Field label="Stress scenario"><select value={scenario} onChange={(e) => setScenario(e.target.value)}>{SCENARIOS.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></Field><Field label="Simulation duration"><select value={days} onChange={(e) => setDays(Number(e.target.value))}>{[7, 14, 30].map((value) => <option key={value} value={value}>{value} days</option>)}</select></Field><Field label="Random seed"><input type="number" min="0" max="4294967295" step="1" required value={seed} onChange={(e) => setSeed(Number(e.target.value))} /></Field></>}<Button variant="primary" type="submit" busy={pending} disabled={sim.busy || sim.playing}><BarChart3 size={15} />Run strategy comparison</Button></div>
      <div className="strategy-options">{STRATEGIES.map((strategy) => <label key={strategy.id} className={`strategy-option ${strategies.includes(strategy.id) ? 'selected' : ''}`}><input type="checkbox" checked={strategies.includes(strategy.id)} onChange={(e) => setStrategies(e.target.checked ? [...strategies, strategy.id] : strategies.filter((id) => id !== strategy.id))} /><span className="strategy-option-dot" style={{ background: strategy.color }} /><span><strong>{strategy.name}</strong><small>{strategy.description}</small></span>{strategies.includes(strategy.id) && <Check size={13} />}</label>)}</div>
      {error && <Alert tone="danger">{error}</Alert>}
      </form>
    </Panel>
    {sim.mode === 'mock' && <Alert><FlaskConical size={13} className="inline-icon" />Mock-engine comparison. These are reproducible development results, not measured project or ML performance.</Alert>}
    {pending ? <Loading /> : !results.length ? <Panel><Empty title={comparison && comparison.status !== 'COMPLETED' ? 'Comparison is still processing' : 'Let the results make the case.'} detail={comparison && comparison.status !== 'COMPLETED' ? 'The backend has accepted this comparison. Refresh to retrieve confirmed results.' : 'Run a strategy comparison to view performance across yield, idle cash, and liquidity risk.'}>{comparison && <Button onClick={sim.refreshComparison} disabled={sim.busy}>Refresh results</Button>}</Empty></Panel> : <>
      <div className="results-heading"><div><span className="eyebrow">COMPARISON COMPLETE</span><h2>{comparison.input_source ? 'Imported cash-flow outcomes' : `${comparison.days}-day treasury outcomes`}</h2><p>Seed {comparison.seed} · {comparison.input_source ? `${comparison.duration_steps} steps · CSV replay` : SCENARIOS.find((s) => s.id === comparison.scenario)?.name} · {results.length} strategies</p></div><Button onClick={exportResults}><ArrowDownToLine size={15} />Export comparison</Button></div>
      <div className="ranking-strip"><Trophy size={19} /><div><strong>{leaders.length > 1 ? `${leaders.length} strategies tied` : STRATEGIES.find((s) => s.id === leaders[0]?.strategy)?.name}</strong><span>{criterion === 'net_benefit_cents' ? 'Highest net financial benefit' : criterion === 'reserve_breaches' ? 'Fewest reserve breaches' : 'Fewest failed payouts'} · Results depend on the selected criterion.</span></div><select className="compact-select" aria-label="Ranking criterion" value={criterion} onChange={(e) => setCriterion(e.target.value)}><option value="net_benefit_cents">Highest net benefit</option><option value="reserve_breaches">Fewest reserve breaches</option><option value="failed_payouts">Fewest failed payouts</option></select></div>
      <Panel title="The complete financial picture" subtitle="All monetary figures in USD. A breach counts each interval below the reserve.">
        <div className="table-scroll"><table className="strategy-table"><thead><tr><th>Performance metric</th>{results.map((result) => <th className={`numeric ${result.strategy === 'RESERVE_JUGGLER' ? 'highlight-column' : ''}`} key={result.strategy}><span className="strategy-table-dot" style={{ background: STRATEGIES.find((s) => s.id === result.strategy)?.color }} />{STRATEGIES.find((s) => s.id === result.strategy)?.name ?? result.strategy}</th>)}</tr></thead><tbody>{metrics.map(([label, key, monetary]) => <tr key={key} className={key === 'net_benefit_cents' ? 'total-row' : ''}><td>{label}</td>{results.map((result) => <td className={`numeric ${result.strategy === 'RESERVE_JUGGLER' ? 'highlight-column' : ''}`} key={result.strategy}>{monetary ? money(result[key]) : result[key] ?? '—'}</td>)}</tr>)}</tbody></table></div>
      </Panel>
      <ArenaAnalytics results={results} />
      <div className="two-column"><Panel title="Net financial benefit" subtitle="Realized interest less penalties and borrowing costs"><ComparisonBars data={chartData} fields={[{ key: 'net_benefit_cents', name: 'Net benefit', color: '#0071e3' }]} summary="Computed net benefit for each mock strategy. Negative values represent a net cost." /></Panel><Panel title="Yield & financial costs" subtitle="Earnings and the cost of liquidity"><ComparisonBars data={chartData} fields={[{ key: 'realized_interest_cents', name: 'Interest', color: '#4c9185' }, { key: 'penalties_cents', name: 'Penalties', color: '#c28a47' }, { key: 'borrowing_costs_cents', name: 'Borrowing costs', color: '#c76767' }]} summary="Realized interest, early redemption penalties, and borrowing costs by strategy." /></Panel></div>
      <div className="two-column"><Panel title="Liquidity risk" subtitle="Recorded events throughout the comparison"><ComparisonBars data={chartData} fields={[{ key: 'reserve_breaches', name: 'Reserve breaches', color: '#c28a47' }, { key: 'failed_payouts', name: 'Failed payouts', color: '#c76767' }]} count summary="Counts of reserve-breach intervals and failed payout intervals." /></Panel><Panel title="Average idle cash" subtitle="Average checking across recorded simulation steps"><ComparisonBars data={chartData} fields={[{ key: 'average_checking_cents', name: 'Average checking', color: '#91a5d6' }]} summary="Average checking balance for each strategy." /></Panel></div>
      {timeline.length > 0 && <Panel title="Checking balance over time" subtitle="Retrospective backtest history · sampled every four simulated hours"><TimeChart data={timeline} series={STRATEGIES.filter((s) => results.some((r) => r.strategy === s.id)).map((s) => ({ key: s.id, name: s.name, color: s.color }))} summary="Recorded checking balances from completed backtests, not live future values." /><div className="chart-legend">{results.map((result) => <span key={result.strategy}><i style={{ background: STRATEGIES.find((s) => s.id === result.strategy)?.color }} />{STRATEGIES.find((s) => s.id === result.strategy)?.name}</span>)}</div></Panel>}
    </>}
    <ModelEvaluation evaluation={comparison?.model_evaluation} />
  </>;
}

export default function StrategyArena() {
  const { snapshot, mode } = useSimulation();
  return <div className="page-content"><div className="page-heading"><div><span className="eyebrow">Strategy comparison</span><h1>Treasury Strategy Arena</h1><p>Three approaches. The same cash flows. A measurable difference.</p></div><Badge tone="blue">{mode === 'mock' ? 'Deterministic mock backtesting' : 'Backend backtesting'}</Badge></div>{snapshot ? <ArenaContent key={snapshot.run_id} /> : <StartState />}</div>;
}
