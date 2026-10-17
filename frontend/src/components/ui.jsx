import { ArrowDownLeft, ArrowUpRight, CircleAlert, Loader2, Inbox } from 'lucide-react';
import { money } from '../utils/format';

export function Button({ children, variant = 'secondary', busy = false, className = '', ...props }) {
  return <button className={`button button-${variant} ${className}`} {...props} disabled={props.disabled || busy}>
    {busy && <Loader2 size={15} className="spin" aria-hidden="true" />}{children}
  </button>;
}
export function Badge({ children, tone = 'neutral' }) { return <span className={`badge badge-${tone}`}>{children}</span>; }
export function Panel({ title, subtitle, action, children, className = '', id }) {
  return <section className={`panel ${className}`} id={id}>
    {(title || action) && <div className="panel-heading"><div><h2>{title}</h2>{subtitle && <p>{subtitle}</p>}</div>{action}</div>}
    {children}
  </section>;
}
export function Empty({ title, detail, children }) { return <div className="empty-state"><Inbox size={25} strokeWidth={1.4} aria-hidden="true" /><h3>{title}</h3>{detail && <p>{detail}</p>}{children}</div>; }
export function Alert({ tone = 'info', children, action }) { return <div role={tone === 'danger' ? 'alert' : 'status'} className={`alert alert-${tone}`}><CircleAlert size={17} aria-hidden="true" /><div>{children}</div>{action}</div>; }
export function Metric({ label, value, note, icon: Icon, accent = false }) {
  return <article className={`metric ${accent ? 'metric-accent' : ''}`}>
    <div className="metric-label">{label}{Icon && <Icon size={16} strokeWidth={1.5} aria-hidden="true" />}</div>
    <div className="metric-value" title={typeof value === 'number' ? money(value) : undefined}>{typeof value === 'number' ? money(value, Math.abs(value) >= 10000000) : value}</div>
    <div className="metric-note">{note}</div>
  </article>;
}
export function Field({ label, hint, children }) { return <label className="field"><span>{label}</span>{children}{hint && <small>{hint}</small>}</label>; }
export function Direction({ direction }) { return direction === 'INFLOW' ? <ArrowDownLeft size={15} aria-label="Incoming" /> : <ArrowUpRight size={15} aria-label="Outgoing" />; }
export function Loading() { return <div className="loading-block" role="status"><Loader2 className="spin" size={20} /> Loading confirmed simulation state…</div>; }
