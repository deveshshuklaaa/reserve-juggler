import { useEffect, useRef, useState } from 'react';
import { Check, Download, FileSpreadsheet, Upload, X } from 'lucide-react';
import { useSimulation } from '../context/SimulationContext';
import { parseCashflowCsv, parseCsvRecords } from '../utils/cashflowCsv';
import { parseOrganizerCsv } from '../utils/organizerCsv';
import { exportCsv, money } from '../utils/format';
import { Alert, Button } from './ui';
import './CashflowImport.css';
import { useLocation, useNavigate } from 'react-router-dom';

const headers = ['timestamp', 'inflow_cents', 'outflow_cents'];
const sample = [
  ['2026-10-17T08:00:00Z', 280000000, 220000000],
  ['2026-10-17T08:15:00Z', 240000000, 310000000],
  ['2026-10-17T08:30:00Z', 190000000, 420000000],
  ['2026-10-17T08:45:00Z', 310000000, 180000000],
];
const readText = (file) => new Promise((resolve, reject) => {
  const reader = new FileReader();
  reader.onload = () => resolve(String(reader.result));
  reader.onerror = () => reject(new Error('The file could not be read. Choose it again.'));
  reader.readAsText(file, 'UTF-8');
});

export default function CashflowImport() {
  const sim = useSimulation();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const [preview, setPreview] = useState(null);
  const [error, setError] = useState('');
  const [reading, setReading] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [name, setName] = useState('');
  const dialog = useRef(null);
  const picker = useRef(null);
  const request = useRef(0);

  useEffect(() => {
    const previous = document.activeElement;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    dialog.current.focus();
    const keyboard = (event) => {
      if (event.key === 'Escape') { event.preventDefault(); sim.closeImport(); }
      if (event.key !== 'Tab') return;
      const controls = [...dialog.current.querySelectorAll('button:not(:disabled),input:not(:disabled),a[href]')].filter((element) => !element.hidden && element.getAttribute('type') !== 'file');
      const first = controls[0]; const last = controls.at(-1);
      if (!dialog.current.contains(document.activeElement)) { event.preventDefault(); (event.shiftKey ? last : first)?.focus(); return; }
      if (event.shiftKey && (document.activeElement === first || document.activeElement === dialog.current)) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && (document.activeElement === last || document.activeElement === dialog.current)) { event.preventDefault(); first?.focus(); }
    };
    document.addEventListener('keydown', keyboard);
    return () => {
      request.current += 1;
      document.body.style.overflow = overflow;
      document.removeEventListener('keydown', keyboard);
      if (previous?.isConnected) previous.focus();
    };
  }, [sim.closeImport]);

  const choose = async (files) => {
    const token = ++request.current;
    setError(''); setPreview(null); setName(''); setReading(false);
    if (files.length !== 1) return setError('Choose one CSV file at a time.');
    const file = files[0];
    if (!/\.csv$/i.test(file.name)) return setError('Choose a .csv file. Download the template below to get started.');
    if (file.size > 2 * 1024 * 1024) return setError('This file is too large. The limit is 2 MB.');
    setReading(true);
    try {
      const text = await readText(file);
      if (request.current !== token) return;
      if (text.includes('\uFFFD')) throw new Error('Save the CSV with UTF-8 encoding and choose it again.');
      const columns = parseCsvRecords(text)[0]?.cells ?? [];
      const organizer = columns.includes('deposits_usd');
      const dataset = organizer ? parseOrganizerCsv(text) : parseCashflowCsv(text);
      if (!organizer) {
        const steps = (Date.parse(dataset.end_time) - Date.parse(dataset.start_time)) / 900000 + 1;
        if (steps > 2880) throw new Error('Local replay supports up to 30 days. Choose a shorter cash-flow period.');
        if (dataset.rows.some((row) => row.inflow_cents > 100000000000 || row.outflow_cents > 100000000000) || dataset.total_inflow_cents > 1000000000000 || dataset.total_outflow_cents > 1000000000000) throw new Error('Local replay supports up to $1B per flow and $10B total in each direction.');
      }
      setPreview({ ...dataset, format: organizer ? 'organizer' : 'cashflows' }); setName(file.name);
    } catch (failure) { if (request.current === token) setError(failure.message); }
    finally { if (request.current === token) setReading(false); }
  };

  const launch = async () => {
    setError('');
    try { const result = await sim.importCashflows(preview); if (!result) setError('The simulation could not start. Close this preview to see the connection details, then retry.'); else if (pathname === '/') navigate('/command-center'); }
    catch (failure) { setError(failure.message); }
  };
  const organizer = preview?.format === 'organizer';
  return <div className="cashflow-backdrop" onClick={(event) => { if (event.target === event.currentTarget) sim.closeImport(); }}>
    <section className="cashflow-dialog" role="dialog" aria-modal="true" aria-labelledby="csv-title" aria-describedby="csv-description" ref={dialog} tabIndex={-1}>
      <header className="cashflow-heading"><div><span className="eyebrow">YOUR DATA</span><h2 id="csv-title">Bring your cash flows.</h2><p id="csv-description">Validate a CSV, inspect the numbers, then choose your next step.</p></div><button type="button" className="icon-button" aria-label="Close CSV import" onClick={sim.closeImport}><X size={20} /></button></header>
      <div className={`cashflow-drop ${dragging ? 'is-dragging' : ''}`} onDragOver={(event) => { event.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={(event) => { event.preventDefault(); setDragging(false); if (!sim.busy) choose(event.dataTransfer.files); }}>
        <FileSpreadsheet size={30} strokeWidth={1.3} aria-hidden="true" /><strong>{reading ? 'Checking your file…' : 'Drop your CSV here'}</strong><span>UTF-8 · Up to 2 MB · 5,000 rows</span>
        <input ref={picker} type="file" accept=".csv,text/csv" hidden aria-label="Cash flow CSV file" disabled={sim.busy} onChange={(event) => { choose(event.target.files); event.target.value = ''; }} />
        <Button onClick={() => picker.current.click()} disabled={sim.busy || reading}><Upload size={14} />Choose CSV</Button>
      </div>
      <div className="cashflow-template"><p><strong>Local replay template</strong><span>timestamp, inflow_cents, outflow_cents · USD cents · UTC · 15 or 60 minutes</span></p><Button variant="quiet" onClick={() => exportCsv('reserve-juggler-cashflows.csv', headers, sample)}><Download size={14} />Download template</Button></div>
      {error && <Alert tone="danger">{error}</Alert>}
      {preview && <div className="cashflow-preview">
        <div className="cashflow-file"><Check size={17} /><strong>{name}</strong><span>{organizer ? 'Organizer dataset' : 'Cash-flow replay'} · Validated</span></div>
        <div className="cashflow-summary"><div><span>OBSERVATIONS</span><strong>{preview.rows.length.toLocaleString('en-US')}</strong></div><div><span>INTERVAL</span><strong>{preview.interval_minutes} min</strong></div><div><span>TIME BASIS</span><strong>{organizer ? 'Unspecified' : 'UTC'}</strong></div>{!organizer && <><div><span>TOTAL INFLOW</span><strong>{money(preview.total_inflow_cents, true)}</strong></div><div><span>TOTAL OUTFLOW</span><strong>{money(preview.total_outflow_cents, true)}</strong></div></>}</div>
        <p className="cashflow-range">{preview.start_time} → {preview.end_time}{!organizer && ' · UTC'}</p>
        <div className="table-scroll"><table><caption>First {Math.min(5, preview.rows.length)} observations · {organizer ? 'source USD values' : 'formatted USD values'}</caption><thead><tr><th>Timestamp</th><th className="numeric">{organizer ? 'Deposits' : 'Inflow'}</th><th className="numeric">{organizer ? 'Withdrawals' : 'Outflow'}</th>{organizer && <th className="numeric">Source net flow</th>}</tr></thead><tbody>{preview.rows.slice(0, 5).map((row) => <tr key={row.timestamp}><td>{row.timestamp}</td><td className="numeric">{organizer ? row.deposits_usd : money(row.inflow_cents)}</td><td className="numeric">{organizer ? row.withdrawals_usd : money(row.outflow_cents)}</td>{organizer && <td className="numeric">{row.net_flow_usd}</td>}</tr>)}</tbody></table></div>
        {organizer ? <><Alert>All market fields and source timestamps are preserved. Backend ingestion is required to run this organizer dataset. Preview only.</Alert>{preview.reconciliation_warnings?.length > 0 && <Alert>{preview.reconciliation_warnings.length} source net-flow differences found. Values are preserved. {preview.reconciliation_warnings[0].message}</Alert>}</> : <Alert>Local mock replay uses these cash flows with $20M checking and $6M opening vault principal. Hourly rows post at their recorded time; intervening 15-minute steps have zero flow. Forecasts use observed history.</Alert>}
      </div>}
      <footer className="cashflow-actions"><p>Files stay on this device. {sim.mode === 'real' ? 'Live upload awaits the backend contract.' : 'Local replay uses the frontend mock engine.'}</p><Button variant="primary" disabled={!preview || organizer || reading || sim.mode !== 'mock'} busy={sim.busy} onClick={launch}>Start CSV simulation</Button></footer>
    </section>
  </div>;
}
