import { useId } from 'react';
import { ArrowRight, Clock3, FileUp, Layers3 } from 'lucide-react';
import { useSimulation } from '../context/SimulationContext';
import { Button } from './ui';
import './SimulationStart.css';

function CapitalRoutes() {
  const gradientId = useId();
  return <div className="simulation-start-visual" aria-hidden="true">
    <div className="simulation-start-visual-label"><span />Capital, connected.</div>
    <svg viewBox="0 0 460 280" fill="none" className="simulation-start-routes">
      <defs><linearGradient id={gradientId} x1="110" y1="140" x2="350" y2="140" gradientUnits="userSpaceOnUse"><stop stopColor="#c2d9f3" /><stop offset="1" stopColor="#0071e3" /></linearGradient></defs>
      <g className="simulation-start-grid" stroke="#e8edf3"><path d="M0 70H460M0 140H460M0 210H460M115 0V280M230 0V280M345 0V280" /></g>
      <g stroke={`url(#${gradientId})`} strokeWidth="1.5"><path d="M130 140H192C224 140 218 50 250 50H310" /><path d="M130 140H310" /><path d="M130 140H192C224 140 218 230 250 230H310" /></g>
      <g className="simulation-start-route-pulse" stroke="#0071e3" strokeWidth="2.5" strokeLinecap="round" strokeDasharray="4 160"><path d="M130 140H192C224 140 218 50 250 50H310" /><path d="M130 140H310" /><path d="M130 140H192C224 140 218 230 250 230H310" /></g>
      <rect x="34" y="96" width="96" height="88" rx="22" fill="white" stroke="#dbe7f4" />
      <path d="M66 144V123H95V144M62 151H100M73 130V141M81 130V141M89 130V141" stroke="#0071e3" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      <text x="82" y="169" textAnchor="middle" fill="#475569" fontSize="10" fontWeight="600">CASH</text>
      {[{ y: 26, name: 'Repo', color: '#278975' }, { y: 116, name: 'Bonds', color: '#7563b6' }, { y: 206, name: 'Equities', color: '#a87d39' }].map(({ y, name, color }) => <g key={name}>
        <rect x="310" y={y} width="120" height="48" rx="14" fill="white" stroke="#e1e7ef" />
        <circle cx="332" cy={y + 24} r="4" fill={color} />
        <text x="346" y={y + 28} fill="#475569" fontSize="12" fontWeight="500">{name}</text>
      </g>)}
      <circle cx="167" cy="140" r="4" fill="#0071e3" stroke="white" strokeWidth="3" />
    </svg>
    <p className="simulation-start-visual-caption">A clear view across four capital tiers.</p>
  </div>;
}

export default function SimulationStart({ children, onImport }) {
  const { createRun, busy, mode } = useSimulation();
  const headingId = useId();
  const isMock = mode === 'mock';
  return <div className="simulation-start">
    <section className="simulation-start-card" aria-labelledby={headingId}>
      <div className="simulation-start-copy">
        <span className="simulation-start-eyebrow">Your treasury workspace</span>
        <h2 id={headingId}>Put your cash<br /><span>in perspective.</span></h2>
        <p>{isMock ? 'Start with a repeatable sample, or bring your cash-flow history. Explore liquidity and compare strategies in one place.' : 'Create a backend simulation to explore liquidity and compare treasury strategies.'}</p>
        <div className="simulation-start-actions">
          <Button variant="primary" busy={busy} onClick={() => createRun()}>Create simulation <ArrowRight size={16} aria-hidden="true" /></Button>
          {onImport && <button type="button" className="simulation-start-import" onClick={onImport} disabled={busy}><FileUp size={16} aria-hidden="true" />Import cash flows</button>}
        </div>
        <div className="simulation-start-meta"><span><Clock3 size={14} aria-hidden="true" />15-minute steps</span><span><Layers3 size={14} aria-hidden="true" />{isMock ? 'Deterministic sample' : 'Backend simulation'}</span><span>USD</span></div>
      </div>
      <CapitalRoutes />
    </section>
    {children && <div className="simulation-start-input">{children}</div>}
  </div>;
}
