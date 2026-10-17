import { useState } from 'react';
import { Activity, ArrowDownRight, ArrowRight, Check, Clock3, FlaskConical, LockKeyhole, ShieldCheck, Zap } from 'lucide-react';
import { useSimulation } from '../context/SimulationContext';
import { SCENARIOS } from '../mocks/constants';
import { money, dollarsToCents, rate, utc } from '../utils/format';
import { Alert, Badge, Button, Empty, Field, Panel } from '../components/ui';
import { TimeChart } from '../components/Charts';
import { DecisionCard } from '../components/Treasury';
import { StartState } from './TreasuryDashboard';

function PolicyControls() {
  const { snapshot, updatePolicy, busy, playing } = useSimulation();
  const [policy, setPolicy] = useState({ ...snapshot.policy });
  const [error, setError] = useState('');
  const set = (key, value) => setPolicy((current) => ({ ...current, [key]: value }));
  const submit = async (event) => {
    event.preventDefault(); setError('');
    try { await updatePolicy(policy); } catch (err) { setError(err.message); }
  };
  if (!snapshot.policy) return <Panel title="Reserve policy"><Empty title="Policy controls unavailable" detail="This backend snapshot does not advertise a supported policy schema." /></Panel>;
  return <Panel title="Reserve policy" subtitle="Apply changes explicitly; original vault terms remain fixed." action={<ShieldCheck size={18} className="muted" />}>
    <form onSubmit={submit} className="policy-form">
      <div className="form-grid"><Field label="Risk percentile"><select value={policy.risk_percentile} onChange={(e) => set('risk_percentile', Number(e.target.value))}>{[90, 95, 99].map((value) => <option key={value} value={value}>{value}%</option>)}</select></Field>
      <Field label="Safety buffer (USD)"><input type="number" min="0" max="50000000" step="0.01" required value={policy.operational_buffer_cents / 100} onChange={(e) => set('operational_buffer_cents', Math.round(Number(e.target.value) * 100))} /></Field>
      <Field label="Minimum sweep (USD)"><input type="number" min="0" max="50000000" step="0.01" required value={policy.min_sweep_cents / 100} onChange={(e) => set('min_sweep_cents', Math.round(Number(e.target.value) * 100))} /></Field>
      <Field label="Vault annual rate (bps)" hint={`Currently ${rate(snapshot.policy?.vault_rate_bps)}`}><input type="number" min="0" max="2000" step="1" required value={policy.vault_rate_bps} onChange={(e) => set('vault_rate_bps', Number(e.target.value))} /></Field>
      <Field label="Lock duration (steps)"><input type="number" min="1" max="384" step="1" required value={policy.lock_steps} onChange={(e) => set('lock_steps', Number(e.target.value))} /></Field>
      <Field label="Early exit penalty (bps)"><input type="number" min="0" max="2000" step="1" required value={policy.early_redemption_penalty_bps} onChange={(e) => set('early_redemption_penalty_bps', Number(e.target.value))} /></Field></div>
      <label className="check-field"><input type="checkbox" checked={policy.allow_early_redemption} onChange={(e) => set('allow_early_redemption', e.target.checked)} /><span>Allow early redemption for new vault positions</span></label>
      {error && <Alert tone="danger">{error}</Alert>}
      <div className="form-footer"><span>Active confidence: {snapshot.policy?.risk_percentile}%</span><Button type="submit" disabled={busy || playing || !snapshot.policy}>Apply policy <Check size={14} /></Button></div>
    </form>
  </Panel>;
}

function LabContent() {
  const sim = useSimulation(); const { snapshot, beforeShock, scheduled } = sim;
  const [scenario, setScenario] = useState('HIGH_WITHDRAWAL');
  const [duration, setDuration] = useState(8);
  const [offset, setOffset] = useState(1);
  const [multiplier, setMultiplier] = useState(3);
  const [reduction, setReduction] = useState(60);
  const [delay, setDelay] = useState(8);
  const [fraction, setFraction] = useState(75);
  const [amount, setAmount] = useState('8000000');
  const [error, setError] = useState('');
  const trigger = async (event) => {
    event.preventDefault(); setError('');
    try {
      if (snapshot.step + offset > snapshot.duration_steps) throw new Error('Schedule the event before the simulation ends.');
      await sim.applyScenario({ scenario, effective_step: snapshot.step + offset,
        parameters: { duration_steps: duration, multiplier_bps: Math.round(multiplier * 10000), reduction_bps: Math.round(reduction * 100),
          delay_steps: delay, fraction_bps: Math.round(fraction * 100), shock_cents: dollarsToCents(amount) } });
    } catch (err) { setError(err.message); }
  };
  const executed = scheduled && snapshot.step >= scheduled.effective_step;
  const fields = [['Checking cash', 'checking_cents'], ['Required reserve', 'required_reserve_cents'], ['Locked vault', 'vault_locked_cents'], ['Borrowing costs', 'borrowing_costs_cents']];
  return <>
    <div className="lab-grid"><div className="lab-controls"><Panel title="Choose your stress test" subtitle="Five controlled scenarios. One shared simulation.">
      <form onSubmit={trigger}>
        <div className="scenario-options" role="radiogroup" aria-label="Stress scenario">{SCENARIOS.map((item) => <button type="button" role="radio" aria-checked={scenario === item.id} key={item.id} className={`scenario-option ${scenario === item.id ? 'selected' : ''}`} onClick={() => setScenario(item.id)}><span className="scenario-symbol">{item.id === 'NORMAL' ? <Activity size={18} /> : item.id === 'SETTLEMENT_DELAY' ? <Clock3 size={18} /> : item.id === 'LIQUIDITY_SHOCK' ? <Zap size={18} /> : <ArrowDownRight size={18} />}</span><span><strong>{item.name}</strong><small>{item.detail}</small></span><span className="radio-indicator" /></button>)}</div>
        <div className="scenario-parameters"><div className="subsection-label">SCENARIO PARAMETERS</div>
          {scenario === 'HIGH_WITHDRAWAL' && <Field label={`Withdrawal multiplier · ${multiplier.toFixed(1)}×`} hint="1× preserves normal withdrawal volume."><input aria-label="Withdrawal multiplier" type="range" min="1" max="5" step="0.1" value={multiplier} onChange={(e) => setMultiplier(Number(e.target.value))} /><span className="range-labels"><span>1×</span><span>5×</span></span></Field>}
          {scenario === 'LOW_DEPOSIT' && <Field label={`Deposit reduction · ${reduction}%`}><input aria-label="Deposit reduction" type="range" min="0" max="100" step="1" value={reduction} onChange={(e) => setReduction(Number(e.target.value))} /><span className="range-labels"><span>0%</span><span>100%</span></span></Field>}
          {scenario === 'SETTLEMENT_DELAY' && <div className="form-grid"><Field label="Delay (15-min steps)"><input type="number" min="1" max="96" step="1" required value={delay} onChange={(e) => setDelay(Number(e.target.value))} /></Field><Field label="Receipts delayed (%)"><input type="number" min="0" max="100" step="1" required value={fraction} onChange={(e) => setFraction(Number(e.target.value))} /></Field></div>}
          {scenario === 'LIQUIDITY_SHOCK' && <Field label="Unexpected outflow (USD)" hint="One event at the effective step."><input type="number" min="0.01" max="100000000" step="0.01" required value={amount} onChange={(e) => setAmount(e.target.value)} /></Field>}
          {scenario === 'NORMAL' && <p className="muted small">Normal operations resume for future events. Recorded shocks and delayed receipts remain in history.</p>}
          <div className="form-grid"><Field label="Effective in (steps)"><input type="number" min="1" max="96" step="1" required value={offset} onChange={(e) => setOffset(Number(e.target.value))} /></Field><Field label="Duration (steps)" hint={`${duration * 15} simulated minutes`}><input type="number" min="1" max="96" step="1" required value={duration} onChange={(e) => setDuration(Number(e.target.value))} /></Field></div>
        </div>
        {error && <Alert tone="danger">{error}</Alert>}
        <Button type="submit" variant="primary" className="full-width" disabled={sim.busy || sim.playing || sim.status === 'COMPLETED'} busy={sim.busy}><FlaskConical size={15} />Trigger scenario</Button>
        <p className="form-footnote">Changes take effect only after confirmed simulation steps.</p>
      </form>
    </Panel><div className="lab-tip"><LockKeyhole size={17} /><div><strong>Locked means locked.</strong><p>{money(snapshot.vault_locked_cents, true)} of vault principal is currently locked. Emergency funding and payout failures are modeled explicitly.</p></div></div></div>
    <div className="lab-results">
      <Panel title="Stress response" subtitle="Checking liquidity against the changing reserve" action={<Badge tone={executed ? 'warning' : 'neutral'}>{scheduled ? executed ? 'Event observed' : 'Scheduled' : 'Awaiting scenario'}</Badge>}>
        <TimeChart data={sim.history} height={270} series={[{ key: 'checking_cents', name: 'Checking', color: '#0071e3' }, { key: 'required_reserve_cents', name: 'Required reserve', color: '#c28a47', dashed: true }]} summary="Confirmed checking and required reserve. Scenario submission alone does not move money." />
        <div className="chart-legend"><span><i style={{ background: '#0071e3' }} />Checking</span><span><i style={{ background: '#c28a47' }} />Required reserve</span></div>
      </Panel>
      <Panel title="Before & after" subtitle={scheduled ? `Captured before submission at step ${beforeShock?.step}; effective at step ${scheduled.effective_step}.` : 'A pre-shock snapshot is preserved when a scenario is accepted.'}>
        {scheduled && !executed && <Alert>Shock scheduled — advance simulation to observe results.</Alert>}
        <div className="table-scroll"><table className="comparison-table"><thead><tr><th>Financial position</th><th className="numeric">Before{beforeShock && <small>Step {beforeShock.step}</small>}</th><th className="numeric">After{executed && <small>Step {snapshot.step}</small>}</th><th className="numeric">Change</th></tr></thead><tbody>{fields.map(([label, key]) => <tr key={key}><td>{label}</td><td className="numeric">{money(beforeShock?.[key])}</td><td className="numeric">{executed ? money(snapshot[key]) : '—'}</td><td className="numeric">{executed && beforeShock?.[key] != null && snapshot[key] != null ? `${snapshot[key] - beforeShock[key] > 0 ? '+' : ''}${money(snapshot[key] - beforeShock[key])}` : '—'}</td></tr>)}</tbody></table></div>
        <div className="comparison-decision"><span>Before: <strong>{beforeShock?.decision?.action ?? '—'}</strong></span><ArrowRight size={15} /><span>After: <strong>{executed ? snapshot.decision?.action ?? '—' : 'Awaiting execution'}</strong></span></div>
      </Panel>
      <PolicyControls key={snapshot.run_id} />
    </div></div>
    {snapshot.alerts?.map((alert, index) => <Alert key={`${snapshot.step}-${index}`} tone={alert.severity === 'CRITICAL' ? 'danger' : 'warning'}>{alert.severity} — {alert.message}</Alert>)}
    <div className="lab-bottom"><DecisionCard snapshot={snapshot} /><Panel title="Scenario activity" subtitle="Scheduled and observed events belong to this run.">
      {!snapshot.scenarios?.length ? <p className="panel-copy">No scenarios have been submitted. Choose a stress test to begin.</p> : <div className="event-list">{snapshot.scenarios.slice().reverse().map((event) => <div key={event.id}><span className="event-node" /><div><strong>{SCENARIOS.find((s) => s.id === event.scenario)?.name ?? event.scenario}</strong><small>Effective step {event.effective_step} · Submitted at step {event.submitted_step}</small></div><Badge tone={event.status === 'ACTIVE' ? 'warning' : 'neutral'}>{event.status}</Badge></div>)}</div>}
    </Panel></div>
  </>;
}

export default function LiquidityShockLab() {
  const { snapshot } = useSimulation();
  return <div className="page-content"><div className="page-heading"><div><span className="eyebrow">Stress testing</span><h1>Liquidity Shock Lab</h1><p>Challenge your reserve. Understand how your treasury responds.</p></div><Badge tone="warning"><FlaskConical size={12} />Simulation sandbox</Badge></div>{snapshot ? <LabContent key={snapshot.run_id} /> : <StartState />}</div>;
}
