import { Panel, Badge, Empty, Metric } from './ui';
import { money } from '../utils/format';

const values = (snapshot) => snapshot?.portfolio ? [
  snapshot.portfolio.cash.balance_cents, snapshot.portfolio.valuation.tier1_value_cents,
  snapshot.portfolio.valuation.tier2_market_value_cents, snapshot.portfolio.valuation.tier3_market_value_cents,
  snapshot.portfolio.valuation.liabilities_cents,
] : snapshot ? [snapshot.checking_cents, snapshot.vault_locked_cents + snapshot.vault_redeemable_cents, null, null, snapshot.borrowing_outstanding_cents ?? null] : [];
const labels = ['Operating cash', 'Repo / demo vault', 'Sovereign bonds', 'Growth equities', 'Borrowing liabilities'];
const colors = ['#0071e3', '#23866d', '#6d5ec0', '#b07b29', '#b94848'];

export default function StressMatrix({ snapshot, beforeShock, executed }) {
  const before = values(beforeShock); const after = values(snapshot);
  const risk = snapshot?.optimizer_result?.risk;
  return <div className="stress-matrix-container">
    <Panel title="Stress transmission" subtitle="Observed snapshot changes. Missing positions remain unavailable." action={<Badge tone={executed ? 'blue' : 'neutral'}>{executed ? 'Snapshots compared' : 'Awaiting event'}</Badge>}>
      <div className="stress-tier-grid">{labels.map((label, index) => {
        const baseline = before[index]; const current = after[index];
        const change = executed && baseline != null && current != null ? current - baseline : null;
        return <article className="stress-tier-card" key={label} style={{ '--tier-border': colors[index] }}><div className="stress-tier-top"><strong>{label}</strong></div><div className="stress-tier-metrics"><div><small>Before event</small><strong>{money(baseline)}</strong></div><div><small>Current snapshot</small><strong>{money(current)}</strong></div></div><p className="portfolio-footnote">{change == null ? 'No observed change available.' : `Observed change: ${money(change)}. Includes all activity between these snapshots.`}</p></article>;
      })}</div>
    </Panel>
    <Panel title="Modeled liquidity risk" subtitle="Baseline engine risk is separate from executed cash movements.">
      {!risk ? <Empty title="Risk result not supplied" detail="Scenario quantiles, tail shortfall, and model probability estimates will appear when the backend supplies a risk result." /> : <>
        <div className="portfolio-estimates"><Metric label="Available cash" value={risk.available_cash_cents} /><Metric label="Restricted liquidity" value={risk.restricted_liquidity_cents} /><Metric label="Hypothetical sale proceeds" value={risk.permitted_stress_liquidation_cents} note="Stress analysis, not executed sales" /></div>
        <div className="portfolio-estimates"><Metric label="Peak nominal requirement" value={risk.nominal_peak_requirement_cents} /><Metric label="Tail expected shortfall" value={risk.tail_expected_shortfall_cents ?? '—'} /><Metric label="Actual payout failure" value="Unknown" /></div>
        <p className="portfolio-footnote">{risk.uncertainty_mode === 'scenario_quantile' ? 'Scenario-quantile reserve includes uncertainty; no second uncertainty allowance is added.' : 'Uses the supplied uncertainty allowance.'} Model probabilities do not guarantee future liquidity coverage.</p>
        <ul className="recommendation-explanations">{risk.explanations?.map((text) => <li key={text}>{text}</li>)}</ul>
      </>}
    </Panel>
  </div>;
}
