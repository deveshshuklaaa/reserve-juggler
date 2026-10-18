import { formatSourceTimestamp } from '../utils/precision';
import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { ArrowUpRight, Menu, Pause, Play, RotateCcw, SkipForward, Upload, X } from 'lucide-react';
import { useSimulation } from '../context/SimulationContext';
import { utc } from '../utils/format';
import { Alert, Button } from './ui';
import InteractiveBackgroundCanvas from './InteractiveBackgroundCanvas';
import './motion.css';
import CashflowImport from './CashflowImport';
import WorkflowGuide from './WorkflowGuide';
import './WorkspaceShell.css';

const navigation = [
  { to: '/command-center', label: 'Command Center' },
  { to: '/shock-lab', label: 'Liquidity Shock Lab' },
  { to: '/strategy-arena', label: 'Strategy Arena' },
];

export function Layout() {
  const sim = useSimulation();
  const location = useLocation();
  const navigate = useNavigate();
  const retryStart = async () => { if (await sim.retryInitialization() && location.pathname === '/') navigate('/command-center'); };
  const [menu, setMenu] = useState(false);
  const menuButton = useRef(null);
  const navigationRef = useRef(null);
  const mainRef = useRef(null);
  const isLanding = location.pathname === '/';

  useLayoutEffect(() => {
    setMenu(false); window.scrollTo?.({ top: 0, behavior: 'instant' });
    mainRef.current?.scrollTo?.({ top: 0, behavior: 'instant' });
    if (location.pathname !== '/') mainRef.current?.focus({ preventScroll: true });
  }, [location.pathname]);
  useEffect(() => {
    if (!menu) return;
    const prior = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    navigationRef.current?.querySelector('a')?.focus();
    const close = (event) => {
      if (event.key === 'Escape') { setMenu(false); menuButton.current?.focus(); }
      if (event.key === 'Tab') {
        const links = [...navigationRef.current.querySelectorAll('a'), menuButton.current];
        const first = links[0]; const last = links.at(-1);
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
      }
    };
    const desktop = window.matchMedia('(min-width: 761px)');
    const onResize = () => { if (desktop.matches) setMenu(false); };
    desktop.addEventListener('change', onResize);
    document.addEventListener('keydown', close);
    return () => { document.body.style.overflow = prior; document.removeEventListener('keydown', close); desktop.removeEventListener('change', onResize); };
  }, [menu]);

  return <div className={`app-shell ${isLanding ? 'landing-mode' : 'workspace-mode'}`}>
    {isLanding && <InteractiveBackgroundCanvas />}
    <a className="skip-link" href="#main">Skip to content</a>
    <header className="global-header" inert={sim.importOpen || undefined}>
      <div className="global-header-inner">
        <Link to="/" className="brand" aria-label="Reserve Juggler home">
          <svg className="brand-symbol" viewBox="0 0 32 32" fill="none" aria-hidden="true"><path d="M9 24V9h9a6 6 0 0 1 0 12H9m9-6 7 9" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" /><path d="M5 6h10M5 6v15" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" opacity=".35" /></svg>
          <span>Reserve Juggler<span className="brand-edition">Treasury intelligence</span></span>
        </Link>
        {isLanding ? <nav ref={navigationRef} className={`global-navigation ${menu ? 'navigation-open' : ''}`} aria-label="Primary navigation" id="primary-navigation">
          {navigation.map(({ to, label }) => <NavLink key={to} to={to} end={to === '/'}>{label}<ArrowUpRight size={17} className="nav-arrow" aria-hidden="true" /></NavLink>)}
          <span className="mobile-nav-note">Intelligent Treasury Autopilot<br />Simulated environment. No real funds.</span>
        </nav> : <Link to="/" className="workspace-overview-link">Product overview <ArrowUpRight size={14} aria-hidden="true" /></Link>}
        <div className="header-status"><span className={`status-dot ${sim.mode === 'real' && sim.error ? 'dot-red' : ''}`} /><span>{sim.mode === 'mock' ? 'Mock environment' : sim.error ? 'Backend disconnected' : 'FastAPI mode'}</span></div>
        {isLanding && <Button variant="primary" className="landing-upload-button" aria-label="Import cash flows" onClick={sim.openImport} disabled={sim.busy}><Upload size={15} aria-hidden="true" />Upload CSV</Button>}
        {isLanding && <button ref={menuButton} className="icon-button mobile-menu" aria-label={menu ? 'Close navigation' : 'Open navigation'} aria-expanded={menu} aria-controls="primary-navigation" onClick={() => setMenu(!menu)}>{menu ? <X size={22} /> : <Menu size={22} />}</button>}
      </div>
    </header>
    {sim.importOpen && <CashflowImport />}
    <div className="workspace-main" inert={menu || sim.importOpen || undefined}>
      {!isLanding && <WorkflowGuide />}
      {!isLanding && sim.snapshot && (
        <div className="control-bar"><div className="control-bar-inner">
          <div className="simulation-clock"><span className={`status-dot ${sim.playing ? 'dot-green' : ''}`} /><strong>{sim.status === 'RUNNING' ? 'Simulation running' : `Simulation ${sim.status.toLowerCase()}`}</strong><span className="clock-details">{sim.mode === 'real' ? `${formatSourceTimestamp(sim.snapshot.source_timestamp)} - UNSPECIFIED` : `${utc(sim.snapshot.timestamp, true)} UTC`}</span><span className="step-label">Step {sim.snapshot.step} / {sim.snapshot.duration_steps ?? '—'}</span></div>
          <div className="toolbar-actions">
            <Button variant={sim.playing ? 'primary' : 'secondary'} onClick={sim.playing ? sim.pause : sim.play} disabled={(!sim.playing && sim.busy) || sim.status === 'COMPLETED'} aria-label={sim.playing ? 'Pause simulation' : 'Play simulation'}>{sim.playing ? <Pause size={14} /> : <Play size={14} />}{sim.playing ? 'Pause' : 'Play'}</Button>
            <Button onClick={sim.advance} disabled={sim.busy || sim.playing || sim.status === 'COMPLETED'} aria-label="Advance one step"><SkipForward size={14} />Step</Button>
            <Button variant="quiet" onClick={sim.resetRun} disabled={sim.busy} aria-label="Reset simulation"><RotateCcw size={14} /><span className="hide-small">Reset</span></Button>
          </div>
        </div></div>
      )}
      <main id="main" tabIndex={-1} ref={mainRef} aria-label={isLanding ? 'Product overview' : 'Treasury workspace content'}>
        {!isLanding && sim.snapshot?.input_source?.type === 'CSV' && <div className="input-source-strip"><span className="status-dot dot-green" /><strong>CSV replay</strong><span>{sim.snapshot.input_source.row_count} observations · {sim.snapshot.input_source.interval_minutes}-minute source · USD · {sim.mode === 'real' ? 'source time (UNSPECIFIED)' : 'UTC'}</span><span>Local mock engine</span></div>}
        {sim.error && <Alert tone="danger" action={<Button onClick={sim.initializationFailed ? retryStart : sim.snapshot ? sim.refresh : () => sim.createRun()} disabled={sim.busy}>{sim.initializationFailed ? 'Retry initialization' : 'Retry / refresh'}</Button>}>{sim.error} {sim.snapshot && 'Displayed figures are the last confirmed snapshot.'}</Alert>}
        {sim.notice && <Alert>{sim.notice}</Alert>}
        <Outlet />
      </main>
      {isLanding && <footer className="page-footer"><div><span className="footer-brand">Reserve Juggler</span><span>Intelligent Treasury Autopilot.</span></div><div><span>HackForge 2026</span><span>Simulated data. No real funds.</span><span>USD · {sim.mode === 'real' ? 'source time (UNSPECIFIED)' : 'UTC'}</span></div></footer>}
    </div>
  </div>;
}
