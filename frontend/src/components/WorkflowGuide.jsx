import { Link, useLocation } from 'react-router-dom';
import { Upload } from 'lucide-react';
import { useSimulation } from '../context/SimulationContext';
import './WorkflowGuide.css';

const screens = [
  { to: '/', title: 'Monitor', detail: 'Command Center' },
  { to: '/shock-lab', title: 'Stress test', detail: 'Shock Lab' },
  { to: '/strategy-arena', title: 'Compare', detail: 'Strategy Arena' },
];

export default function WorkflowGuide() {
  const { snapshot, busy, openImport, mode } = useSimulation();
  const { pathname } = useLocation();
  return <nav className="workflow-guide" aria-label="Treasury workflow">
    <ol>
      <li><button type="button" className="workflow-upload" aria-label="Import cash flows" aria-current={!snapshot ? 'step' : undefined} onClick={openImport} disabled={busy}>
        <Upload size={19} aria-hidden="true" /><span><strong>Upload CSV</strong><small>{snapshot ? 'Change your input' : '1 · Validate & preview'}</small></span>
      </button></li>
      {screens.map(({ to, title, detail }, index) => <li key={to}><Link to={to} className={`workflow-step ${snapshot && pathname === to ? 'is-current' : ''}`} aria-current={snapshot && pathname === to ? 'step' : undefined}>
        <span className="workflow-number" aria-hidden="true">{index + 2}</span><span><strong>{title}</strong><small>{detail}</small></span>
      </Link></li>)}
    </ol>
    <p>{!snapshot ? mode === 'mock' ? 'Start with your CSV, or use demo data to explore.' : 'Upload a CSV to preview it, or create a backend simulation.' : pathname === '/shock-lab' ? 'Choose a shock, then advance a step to see its effect.' : pathname === '/strategy-arena' ? 'Select strategies and run a comparison on the same cash flows.' : 'Use Step or Play to advance, then explore stress tests and comparisons.'}</p>
  </nav>;
}
