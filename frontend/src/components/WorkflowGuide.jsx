import { Link, useLocation } from 'react-router-dom';
import { Upload } from 'lucide-react';
import { useSimulation } from '../context/SimulationContext';
import './WorkflowGuide.css';

const screens = [
  { to: '/command-center', title: 'Command Center', detail: 'Monitor cash & reserves' },
  { to: '/shock-lab', title: 'Liquidity Shock Lab', detail: 'Test a cash-flow shock' },
  { to: '/strategy-arena', title: 'Strategy Arena', detail: 'Compare the outcomes' },
];

export default function WorkflowGuide() {
  const { snapshot, busy, openImport, mode } = useSimulation();
  const { pathname } = useLocation();
  return <nav className="workflow-guide" aria-label="Workspace taskbar">
    <ol>
      <li><button type="button" className="workflow-upload" aria-label="Import cash flows" aria-current={!snapshot ? 'step' : undefined} onClick={openImport} disabled={busy}>
        <Upload size={19} aria-hidden="true" /><span><strong>Upload CSV</strong><small>{snapshot ? snapshot.input_source?.type === 'CSV' ? 'CSV loaded · change input' : 'Demo data · change input' : '1 · Connect your data'}</small></span>
      </button></li>
      {screens.map(({ to, title, detail }, index) => <li key={to}><Link to={to} aria-label={title} className={`workflow-step ${pathname === to ? 'is-current' : ''}`} aria-current={pathname === to ? 'page' : undefined}>
        <span className="workflow-number" aria-hidden="true">{index + 2}</span><span><strong>{title}</strong><small>{detail}</small></span>
      </Link></li>)}
    </ol>
    <p><span className="workflow-hint-label">{!snapshot ? 'Start here' : 'Next action'}</span>{!snapshot ? mode === 'mock' ? 'Upload a CSV above, or choose Use demo data below. Then monitor, test, and compare.' : 'Upload a CSV to preview it, or create a backend simulation.' : pathname === '/shock-lab' ? 'Choose a shock → Trigger scenario → Step to observe its effect.' : pathname === '/strategy-arena' ? 'Choose strategies → Run comparison → Review and export the results.' : 'Step advances 15 minutes. Play runs automatically. Use the tabs below to inspect your treasury.'}</p>
  </nav>;
}
