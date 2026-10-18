import { ArrowDownLeft, ArrowUpRight, Check, ChevronDown, LockKeyhole, ShieldCheck } from 'lucide-react';
import { Badge, Direction, Empty, Panel } from './ui';
import { money, rate, utc } from '../utils/format';
import { useState } from 'react';

export const actionTone = { HOLD: 'blue', SWEEP: 'good', WITHDRAW: 'warning', LIQUIDITY_WARNING: 'danger' };
export function DecisionCard({ snapshot }) {
  const decision = snapshot.decision;
  const [expanded, setExpanded] = useState(true);
  if (!decision) return <Panel title="Treasury decision"><Empty title="Ready for the first decision" detail="Advance one step to evaluate the reserve and eligible capital." /></Panel>;
  const title = { HOLD: 'Maintain current liquidity', SWEEP: 'Put surplus cash to work', WITHDRAW: 'Replenish operating liquidity', LIQUIDITY_WARNING: 'Liquidity needs attention' }[decision.action];
  const risk = decision.risk_method ?? snapshot.forecast?.risk_method;
  const components = risk === 'SCENARIO_QUANTILE' ? [
    ['Scenario percentile shortfall', decision.quantile_shortfall_cents ?? snapshot.forecast?.quantile_shortfall_cents],
    ['Operational buffer', decision.operational_buffer_cents],
  ] : [['Peak cash shortfall', decision.peak_shortfall_cents], ['Uncertainty buffer', decision.uncertainty_buffer_cents], ['Operational buffer', decision.operational_buffer_cents]];
  return <Panel className="decision-panel" title="Current treasury decision" action={<Badge tone={actionTone[decision.action]}>{decision.action.replaceAll('_', ' ')}</Badge>}>
    <div className={`decision-icon decision-${actionTone[decision.action]}`}>{decision.action === 'SWEEP' ? <ArrowUpRight size={24} /> : decision.action === 'WITHDRAW' ? <ArrowDownLeft size={24} /> : <ShieldCheck size={24} />}</div>
    <h3 className="decision-title">{title}</h3><div className="decision-amount">{money(decision.amount_cents)}</div>
    <div className="execution"><Badge tone={decision.executed ? 'good' : decision.action === 'HOLD' ? 'neutral' : 'warning'}>{decision.executed && <Check size={11} />}{decision.executed ? 'Executed' : decision.execution_status === 'NOT_REQUIRED' ? 'No transfer required' : 'Recommended · not executed'}</Badge><span>{utc(decision.timestamp)} UTC</span></div>
    {decision.penalty_cents > 0 && <p className="penalty-note">Redemption penalty: {money(decision.penalty_cents)}</p>}
    <button className="explanation-toggle" onClick={() => setExpanded(!expanded)} aria-expanded={expanded}>WHY THIS DECISION?<ChevronDown size={14} className={expanded ? 'rotate' : ''} /></button>
    {expanded && <div className="explanation"><div className="formula-rows">{components.map(([label, value]) => <div key={label}><span>{label}</span><strong>{money(value)}</strong></div>)}<div className="formula-total"><span>Required reserve</span><strong>{money(decision.required_reserve_cents)}</strong></div></div><div className="decision-balances"><span>Checking before<strong>{money(decision.pre_checking_cents)}</strong></span><span>Checking after<strong>{money(decision.post_checking_cents)}</strong></span></div><ul>{decision.explanation?.map((line, index) => <li key={index}>{line}</li>)}</ul></div>}
  </Panel>;
}

export function Allocation({ snapshot, hero = false }) {
  const values = [['Checking', snapshot.checking_cents, '#315efb'], ['Locked vault', snapshot.vault_locked_cents, '#91a5d6'], ['Redeemable vault', snapshot.vault_redeemable_cents, '#4c9185']];
  const total = values.reduce((sum, item) => sum + item[1], 0);
  const circumference = 2 * Math.PI * 92;
  let offset = 0;
  if (hero) return <div className="hero-allocation">
    <div className="allocation-orbit" role="img" aria-label={values.map(([label, value]) => `${label}: ${money(value)}`).join(', ')}>
      <svg viewBox="0 0 224 224" aria-hidden="true"><circle cx="112" cy="112" r="92" fill="none" stroke="#eceef1" strokeWidth="15" />{values.map(([label, value], index) => {
        const length = total ? value / total * circumference : 0;
        const currentOffset = offset; offset += length;
        return <circle key={label} cx="112" cy="112" r="92" fill="none" stroke={['#1d1d1f', '#0071e3', '#75b8eb'][index]} strokeWidth="15" strokeDasharray={`${Math.max(0, length - (length > 0 ? 5 : 0))} ${circumference}`} strokeDashoffset={-currentOffset} transform="rotate(-90 112 112)" />;
      })}</svg>
      <div className="orbit-label"><span>Total principal</span><strong>{money(total, true)}</strong><small>Checking + vault</small></div>
    </div>
    <div className="orbit-legend">{values.map(([label, value], index) => <div key={label}><span><i style={{ background: ['#1d1d1f', '#0071e3', '#75b8eb'][index] }} />{label}</span><strong>{money(value, true)}</strong></div>)}</div>
    <p className="orbit-note"><LockKeyhole size={11} />Locked capital is excluded from available cash.</p>
    {snapshot.borrowing_outstanding_cents > 0 && <p className="penalty-note">Outstanding borrowing: {money(snapshot.borrowing_outstanding_cents)}</p>}
  </div>;
  return <Panel title="Capital allocation" subtitle="Checking and vault principal">
    <div className="allocation-total"><span>Combined principal</span><strong>{money(total, true)}</strong></div>
    <div className="allocation-bar" role="img" aria-label={values.map(([name, value]) => `${name}: ${money(value)}`).join(', ')}>{values.map(([label, value, color]) => <span key={label} style={{ width: `${total ? value / total * 100 : 0}%`, background: color }} />)}</div>
    <div className="allocation-legend">{values.map(([label, value, color]) => <div key={label}><span><i style={{ background: color }} />{label}</span><strong>{money(value, true)}</strong><small>{total ? (value / total * 100).toFixed(1) : '0.0'}%</small></div>)}</div>
    <div className="allocation-foot"><LockKeyhole size={13} />Locked capital is excluded from available cash.</div>
    {snapshot.borrowing_outstanding_cents > 0 && <p className="penalty-note">Outstanding borrowing: {money(snapshot.borrowing_outstanding_cents)}</p>}
  </Panel>;
}

export function TransactionFeed({ transactions }) {
  const [filter, setFilter] = useState('ALL');
  const filtered = transactions.filter((item) => filter === 'ALL' || item.type === filter).slice(0, 12);
  return <Panel title="Recent transactions" subtitle="Confirmed external cash movements" action={<select className="compact-select" aria-label="Filter transactions" value={filter} onChange={(event) => setFilter(event.target.value)}><option value="ALL">All transactions</option><option value="DEPOSIT">Deposits</option><option value="WITHDRAWAL">Withdrawals</option><option value="MERCHANT_SETTLEMENT">Settlements</option></select>}>
    {!filtered.length ? <Empty title="No transactions have been processed" detail="Advance the simulation to observe cash movements." /> : <div className="table-scroll transaction-scroll"><table><thead><tr><th>Transaction / source</th><th>Time · UTC</th><th>Direction</th><th className="numeric">Amount</th></tr></thead><tbody>{filtered.map((tx) => <tr key={tx.id}><td><div className="transaction-label"><span className={`tx-icon ${tx.direction === 'INFLOW' ? 'positive' : 'outgoing'}`}><Direction direction={tx.direction} /></span><span><strong>{tx.source}</strong><small>{tx.id} · {tx.type.replaceAll('_', ' ')}</small></span></div></td><td>{utc(tx.timestamp)}</td><td><Badge tone={tx.direction === 'INFLOW' ? 'good' : 'neutral'}>{tx.direction === 'INFLOW' ? 'Incoming' : 'Outgoing'}</Badge></td><td className={`numeric ${tx.direction === 'INFLOW' ? 'positive' : ''}`}>{tx.direction === 'INFLOW' ? '+' : '−'}{money(tx.amount_cents)}</td></tr>)}</tbody></table></div>}
  </Panel>;
}

export function VaultPositions({ positions = [] }) {
  return <Panel title="Vault positions" subtitle="Original terms are preserved for every position">
    {!positions.length ? <Empty title="No active vault positions" /> : <div className="table-scroll"><table><thead><tr><th>Position</th><th className="numeric">Principal</th><th>Annual rate</th><th>Maturity · UTC</th><th>Liquidity</th></tr></thead><tbody>{positions.map((position) => <tr key={position.id}><td><strong>{position.id}</strong><small>{position.early_redemption_allowed ? `Early exit: ${rate(position.penalty_bps)} penalty` : 'Early redemption unavailable'}</small></td><td className="numeric">{money(position.principal_cents)}</td><td>{rate(position.rate_bps)}</td><td>{utc(position.maturity_at, true)}</td><td><Badge tone={position.status === 'LOCKED' ? 'neutral' : 'good'}>{position.status === 'LOCKED' && <LockKeyhole size={10} />}{position.status}</Badge></td></tr>)}</tbody></table></div>}
  </Panel>;
}

export function AuditLog({ decisions }) {
  return <Panel title="Decision audit trail" subtitle="Latest confirmed recommendations and execution">
    {!decisions.length ? <Empty title="No decisions recorded yet" /> : <div className="table-scroll"><table><thead><tr><th>Time · UTC</th><th>Action</th><th className="numeric">Amount</th><th>Execution</th><th>Rationale</th></tr></thead><tbody>{decisions.slice(0, 8).map((decision) => <tr key={decision.id}><td>{utc(decision.timestamp)}</td><td><Badge tone={actionTone[decision.action]}>{decision.action.replaceAll('_', ' ')}</Badge></td><td className="numeric">{money(decision.amount_cents)}</td><td>{decision.executed ? 'Executed' : decision.action === 'HOLD' ? 'Not required' : 'Not executed'}</td><td className="rationale-cell">{decision.explanation?.[0]}</td></tr>)}</tbody></table></div>}
  </Panel>;
}
