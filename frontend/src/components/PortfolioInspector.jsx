import { useState } from 'react';
import { ArrowRight, Coins, LockKeyhole, Scale, TrendingUp, Zap } from 'lucide-react';
import { Alert, Badge, Empty, Metric, Panel } from './ui';
import { canonicalOptimizer, canonicalPortfolio } from '../models/canonical';
import { money } from '../utils/format';
import { formatDecimal, formatRateDecimal, formatSourceTimestamp } from '../utils/precision';
import './portfolio.css';

const names = ['Operating cash', 'Overnight repo', 'Sovereign bonds', 'Growth equities'];
const icons = [Coins, Zap, Scale, TrendingUp];
const colors = ['#0071e3', '#23866d', '#6d5ec0', '#b07b29'];
const number = (value) => value == null ? '—' : formatDecimal(value, 4);
const percent = (value) => formatRateDecimal(value, 3);

function Recommendation({ result }) {
  if (!result) return <Panel title="Allocation recommendations" subtitle="Recommendations and booked trades are separate records."><Empty title="No recommendation supplied" detail="The engine's proposed orders will appear here. Execution requires a separate backend receipt." /></Panel>;
  const decision = result.decision;
  return <Panel title="Allocation recommendations" subtitle={`${result.model_version} · Policy ${result.policy_version}`} action={<Badge tone="warning">Proposed · Not executed</Badge>}>
    <div className="recommendation-summary"><strong>{result.summary_action.replaceAll('_', ' ')}</strong><Badge tone={decision.feasible ? 'good' : 'danger'}>{decision.feasible ? 'Within supplied policy' : 'Policy constraints unmet'}</Badge><p>{decision.reason}</p></div>
    {result.search_truncated && <Alert>Candidate search was truncated. This is the best generated feasible candidate, without a guarantee of global optimality.</Alert>}
    {decision.targets && <div className="target-grid">{['tier0_target_cents', 'tier1_allocation_cents', 'tier2_allocation_cents', 'tier3_allocation_cents'].map((key, i) => <Metric key={key} label={`Target · ${names[i]}`} value={decision.targets[key]} />)}</div>}
    <div className="portfolio-estimates"><Metric label="Estimated income" value={result.estimated_income_cents} note="Modeled, not realized interest" /><Metric label="Estimated price change" value={result.estimated_price_change_cents} note="Uncertain market return" /><Metric label="Modeled financing cost" value={result.modeled_financing_cost_cents} note="Separate from booked financing" /></div>
    {decision.orders.map((order) => <article className="proposed-order" key={order.id}>
      <div className="order-title"><span className="tier-index" style={{ '--tier-accent': colors[order.tier] }}>T{order.tier}</span><strong>{order.action.replaceAll('_', ' ')}</strong><strong>{money(order.amount_cents)}</strong><Badge tone="warning">NOT EXECUTED</Badge></div>
      <p>{order.reason}</p>
      <dl className="order-terms"><div><dt>Position</dt><dd>{order.position_id ?? 'New position'}</dd></div><div><dt>Quantity</dt><dd>{number(order.quantity)}</dd></div><div><dt>Expected settlement</dt><dd>{formatSourceTimestamp(order.expected_settlement_at)}</dd></div><div><dt>Expected maturity</dt><dd>{formatSourceTimestamp(order.expected_maturity_at)}</dd></div></dl>
      {order.expected_costs && <dl className="order-terms">{Object.entries(order.expected_costs).map(([key, value]) => <div key={key}><dt>{key.replace('_cents', '').replaceAll('_', ' ')}</dt><dd>{money(value)}</dd></div>)}</dl>}
    </article>)}
    <ul className="recommendation-explanations">{decision.explanations?.map((text) => <li key={text}>{text}</li>)}</ul>
    <p className="portfolio-footnote">Orders preserve engine sequence. Only backend execution receipts establish fills and ledger movements.</p>
    <div className="portfolio-estimates"><Metric label="Baseline funding shortfall" value={result.risk?.funding_shortfall_before_liquidation_cents ?? '—'} note="Before hypothetical liquidation" /><Metric label="Selected plan funding gap" value={result.projected_nominal_funding_gap_cents ?? '—'} note="Optimizer projection" /><Metric label="Actual payout failure" value="Unknown" note="The recommendation engine does not execute" /></div>
  </Panel>;
}

export default function PortfolioInspector({ snapshot, mode = 'real' }) {
  const [filter, setFilter] = useState(null);
  let portfolio; let result;
  try {
    if (snapshot?.portfolio) {
      portfolio = canonicalPortfolio(snapshot.portfolio);
      if (snapshot.optimizer_result) result = canonicalOptimizer(snapshot.optimizer_result, portfolio);
    }
  } catch (error) { return <Alert tone="danger">{error.message}</Alert>; }

  // The real v1 API supplies an explicit projection, not the canonical engine object.
  if (!portfolio && mode === 'real' && snapshot?.four_tier?.tier0 && snapshot.four_tier?.tier1 && snapshot.four_tier?.tier2 && snapshot.four_tier?.tier3 && snapshot.four_tier?.overdraft && snapshot.four_tier?.aggregates) {
    const data = snapshot.four_tier;
    const tiers = [data.tier0.checking_cents, data.tier1.principal_cents,
      data.tier2.market_value_cents, data.tier3.market_value_cents];
    return <div className="portfolio-inspector">
      <Panel title="Four-tier portfolio" subtitle={`${data.timestamp ?? snapshot.timestamp} - source time UNSPECIFIED`}>
        <Badge>Live backend projection - persisted holdings</Badge>
        <div className="tier-cards-grid">{tiers.map((value, tier) => <Metric key={tier} label={`Tier ${tier} - ${names[tier]}`} value={value} />)}</div>
        <div className="portfolio-summary-grid">
          <Metric label="Required reserve" value={data.aggregates.required_reserve_cents} />
          <Metric label="Immediately available" value={data.aggregates.total_immediate_liquidity_cents} />
          <Metric label="Gross assets" value={data.aggregates.gross_assets_cents} />
          <Metric label="Liabilities" value={data.aggregates.total_liabilities_cents} />
          <Metric label="Net portfolio value" value={data.aggregates.net_portfolio_value_cents} />
          <Metric label="Unpaid financing" value={data.overdraft.financing_cost_cents} />
        </div>
        <p>Repo entry 17:00 - maturity 08:00 - locked principal is not available cash.</p>
        <p>Market observation: {data.market_observation_timestamp ?? 'Unavailable'} - publication delay {data.publication_delay_seconds} seconds.</p>
      </Panel>
      <Panel title="Recommendations and execution"><p>The Activity tab contains persisted decisions and executed transactions. This projection does not supply canonical proposed-order details.</p></Panel>
    </div>;
  }

  // Compatibility data is explicitly confined to MOCK mode; never invent LIVE positions.
  const mock = !portfolio && mode === 'mock' ? snapshot?.four_tier : null;
  if (!portfolio && !mock) return <Panel title="Four-tier portfolio"><Empty title="Awaiting canonical portfolio data" detail="The current backend contract has no confirmed four-tier response mapping. Live balances and trades will appear when supplied by the backend." /></Panel>;

  const valuation = portfolio?.valuation;
  const groups = portfolio ? [[portfolio.cash], portfolio.repo_positions, portfolio.bond_positions, portfolio.equity_positions] : [[], [], [], []];
  const values = portfolio ? [valuation.tier0_cash_cents, valuation.tier1_value_cents, valuation.tier2_market_value_cents, valuation.tier3_market_value_cents] : [mock.tier0.checking_cents, mock.tier1.principal_cents, mock.tier2.market_value_cents, mock.tier3.market_value_cents];
  const gross = portfolio ? valuation.total_portfolio_value_cents : mock.aggregates.gross_assets_cents;
  const reserve = result?.decision.reserve.required_reserve_cents ?? (mock ? mock.tier0.required_reserve_cents : null);
  const liabilities = portfolio ? valuation.liabilities_cents : mock.overdraft.borrowing_outstanding_cents;
  return <div className="portfolio-inspector">
    <div className="portfolio-source"><Badge tone={portfolio ? 'neutral' : 'warning'}>{portfolio ? 'Canonical portfolio' : 'Mock · Compatibility model'}</Badge><span>{portfolio ? `${formatSourceTimestamp(portfolio.as_of)} · ${portfolio.time_basis}` : 'Demo vault simulation · bonds and equities have no booked positions'}</span></div>
    <div className="portfolio-summary-grid"><Metric label="Immediately available" value={portfolio ? valuation.immediately_available_cents : mock.tier0.checking_cents} note="Cash available for payouts" /><Metric label="Required reserve" value={reserve ?? '—'} note={result ? 'Supplied engine requirement' : 'Compatibility reserve estimate'} /><Metric label="Restricted liquidity" value={portfolio ? valuation.restricted_value_cents : snapshot.vault_locked_cents} note="Excluded from available cash" /><Metric label="Liabilities" value={liabilities} note="Borrowing and unpaid financing where supplied" /></div>
    <Panel title="Capital across four tiers" subtitle="Holdings and liquidity access" action={<div className="tier-filter-segmented" aria-label="Portfolio tier filter">{[null, 0, 1, 2, 3].map((tier) => <button key={tier ?? 'all'} aria-pressed={filter === tier} className={filter === tier ? 'active' : ''} onClick={() => setFilter(tier)}>{tier == null ? 'All tiers' : `T${tier}`}</button>)}</div>}>
      <div className="portfolio-allocation-track" aria-label="Current tier allocation">{values.map((value, i) => value > 0 && <span key={i} title={`${names[i]}: ${money(value)}`} style={{ flex: value, background: colors[i] }} />)}</div>
      <div className="tier-cards-grid">{values.map((value, tier) => {
        if (filter !== null && tier !== filter) return null;
        const Icon = icons[tier];
        const positions = groups[tier];
        return <article className="tier-card" key={tier} style={{ '--tier-accent': colors[tier] }}><div className="tier-card-header"><span className="tier-icon-box" style={{ color: colors[tier], background: `${colors[tier]}12` }}><Icon size={19} /></span><div><small>Tier {tier}</small><h3>{names[tier]}</h3></div></div><div className="tier-balance-row"><strong className="tier-amount">{money(value, true)}</strong><span>{gross ? `${formatDecimal(value / gross * 100, 1)}%` : '0.0%'}</span></div>
          <p className="tier-card-desc">{['Immediate operating liquidity. Zero modeled yield.', 'Contractual maturity and redemption restrictions apply.', 'Quoted YTM is not a cash coupon. Market and duration risks apply.', 'Market value can change. Equity returns remain uncertain.'][tier]}</p>
          {portfolio ? positions.map((position) => <div className="canonical-position" key={position.id}><span className="position-id" title={position.id}>{position.id}</span><Badge>{position.status ?? position.liquidity?.classification}</Badge><dl className="position-terms">
            {tier === 1 && <><div><dt>Principal</dt><dd>{money(position.principal_cents)}</dd></div><div><dt>APY quote</dt><dd>{percent(position.applicable_apy_pct)}</dd></div><div><dt>Maturity</dt><dd>{formatSourceTimestamp(position.scheduled_maturity_at)}</dd></div><div><dt>Early redemption haircut</dt><dd>{percent(position.early_redemption_haircut_pct)}</dd></div><div><dt>Early redemption allowed</dt><dd>{position.early_redemption_allowed == null ? 'Unspecified' : position.early_redemption_allowed ? 'Yes' : 'No'}</dd></div></>}
            {tier >= 2 && <><div><dt>Quantity</dt><dd>{number(position.quantity)}</dd></div><div><dt>Price index</dt><dd>{number(position.current_market_price_index)}</dd></div><div><dt>Unrealized P&L</dt><dd>{money(position.unrealized_pnl_cents)}</dd></div><div><dt>{tier === 2 ? 'Quoted YTM' : 'Volatility'}</dt><dd>{percent(tier === 2 ? position.supplied_yield_pct : position.supplied_volatility_pct)}</dd></div>{tier === 2 && <div><dt>Modified duration</dt><dd>{number(position.modified_duration)}</dd></div>}</>}
            <div><dt>Available cash</dt><dd>{money(position.liquidity?.available_cents)}</dd></div><div><dt>Hypothetical liquidatable value</dt><dd>{money(position.liquidity?.liquidatable_value_cents)}</dd></div>
          </dl></div>) : <p className="portfolio-footnote">{tier === 1 ? `Demo vault principal · ${money(value)}. This compatibility model does not enforce the canonical 17:00–08:00 repo session.` : tier > 1 ? 'No positions booked by the compatibility simulator.' : 'Balance follows the current mock simulation.'}</p>}
          {portfolio && !positions.length && <p className="portfolio-footnote">No open positions.</p>}
        </article>;
      })}</div>
      <div className="portfolio-totals"><span>Gross assets <strong>{money(gross)}</strong></span><ArrowRight size={16} /><span>Net portfolio value <strong>{money(portfolio ? valuation.net_portfolio_value_cents : gross - liabilities)}</strong></span></div>
      {portfolio?.overdrafts.map((debt) => <div className="overdraft-strip is-drawing" key={debt.id}><LockKeyhole size={19} /><div><strong>Overdraft liability · {money(debt.outstanding_principal_cents)}</strong><p>{percent(debt.apr_pct)} APR · Unpaid financing {money(debt.outstanding_financing_cost_cents)}</p></div></div>)}
    </Panel>
    <Recommendation result={result} />
  </div>;
}
