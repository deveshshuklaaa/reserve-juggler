import { Panel, Metric } from './ui';
import { STRATEGIES } from '../mocks/constants';

export default function ArenaAnalytics({ results = [] }) {
  if (!results.length) return null;
  return <Panel title="Strategy diagnostics" subtitle="Computed only from the completed comparison. No assumed winner or fabricated risk ratios.">
    <div className="scorecard-grid">{results.map((result) => {
      const info = STRATEGIES.find((strategy) => strategy.id === result.strategy);
      return <article className="scorecard-card" key={result.strategy} style={{ '--card-accent': info?.color ?? '#0071e3' }}><div className="scorecard-header"><strong>{info?.name ?? result.strategy}</strong></div><div className="scorecard-kpis"><Metric label="Net benefit" value={result.net_benefit_cents ?? '—'} /><Metric label="Average idle cash" value={result.average_checking_cents ?? '—'} /><Metric label="Borrowing costs" value={result.borrowing_costs_cents ?? '—'} /><div className="metric"><div className="metric-label">Failed payouts</div><div className="metric-value">{result.failed_payouts ?? '—'}</div></div></div><p className="portfolio-footnote">Sharpe ratio, market drawdown, and four-tier allocation history are unavailable unless supplied by the comparison service.</p></article>;
    })}</div>
  </Panel>;
}
