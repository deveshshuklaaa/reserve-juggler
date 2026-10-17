import { useState } from 'react';
import { 
  ShieldCheck, 
  TrendingUp, 
  Zap, 
  Coins, 
  AlertTriangle, 
  LockKeyhole, 
  ArrowUpRight, 
  ArrowDownLeft, 
  CheckCircle2, 
  Clock, 
  Scale, 
  Layers,
  ChevronRight,
  Info
} from 'lucide-react';
import { Badge, Panel, Metric } from './ui';
import { money, rate, utc } from '../utils/format';
import { getMockFourTierSnapshot, MOCK_MULTI_ASSET_DECISIONS } from '../mocks/fourTierFixtures';

export default function FourTierPortfolio({ snapshot }) {
  const [selectedTier, setSelectedTier] = useState('ALL');
  
  // Use four-tier data from snapshot or canonical deterministic mock fixture
  const portfolio = snapshot?.fourTier ?? getMockFourTierSnapshot({
    tier0: {
      checking_cents: snapshot?.checking_cents ?? 2000000000,
      required_reserve_cents: snapshot?.required_reserve_cents ?? 450000000,
      operational_buffer_cents: snapshot?.policy?.operational_buffer_cents ?? 50000000,
    },
    tier1: {
      principal_cents: (snapshot?.vault_locked_cents ?? 0) + (snapshot?.vault_redeemable_cents ?? 600000000),
      realized_interest_cents: snapshot?.realized_interest_cents ?? 172602,
      accrued_interest_cents: snapshot?.accrued_interest_cents ?? 86301,
    },
    overdraft: {
      borrowing_outstanding_cents: snapshot?.borrowing_outstanding_cents ?? 0,
      financing_cost_cents: snapshot?.borrowing_costs_cents ?? 0,
    }
  });

  const { tier0, tier1, tier2, tier3, overdraft, aggregates } = portfolio;

  // Institutional Basel III / Risk Telemetry
  const lcrRatio = Math.round((tier0.immediate_liquidity_cents / Math.max(1, tier0.required_reserve_cents)) * 100);
  const capitalEfficiency = ((aggregates.gross_assets_cents - tier0.checking_cents) / aggregates.gross_assets_cents * 100).toFixed(1);

  const tiers = [
    {
      id: 'TIER_0',
      num: '0',
      name: 'Cash Buffer',
      tag: 'Tier 0 · Instant Liquidity',
      amount: tier0.checking_cents,
      yieldRate: '0.0% APY',
      status: tier0.status,
      color: '#0071e3',
      icon: Coins,
      details: [
        { label: 'Available Checking', val: money(tier0.checking_cents) },
        { label: 'Required Reserve', val: money(tier0.required_reserve_cents) },
        { label: 'Deployable Surplus', val: money(tier0.deployable_surplus_cents) },
        { label: 'Liquidity Access', val: 'Immediate (T+0)' },
      ],
      desc: 'Immediate liquid cash for operating payroll and settlements. Never incurs haircuts or break fees.',
    },
    {
      id: 'TIER_1',
      num: '1',
      name: 'Overnight Repo',
      tag: 'Tier 1 · 17:00 Sweep Window',
      amount: tier1.principal_cents,
      yieldRate: `${tier1.repo_apy_decimal}% APY`,
      status: tier1.status,
      color: '#30d158',
      icon: Zap,
      details: [
        { label: 'Principal', val: money(tier1.principal_cents) },
        { label: 'Floating APY', val: `${tier1.repo_apy_decimal}%` },
        { label: 'Next Maturity', val: '08:00 Next Day' },
        { label: 'Early Break Fee', val: `${tier1.early_break_fee_bps} bps` },
      ],
      desc: 'Institutional overnight repos swept at 17:00 daily cutoff. Liquid next morning at 08:00 with early-break permission.',
    },
    {
      id: 'TIER_2',
      num: '2',
      name: 'Sovereign Bonds',
      tag: 'Tier 2 · Duration Hedge',
      amount: tier2.market_value_cents,
      yieldRate: `${tier2.ytm_decimal}% YTM`,
      status: tier2.unrealized_pnl_cents >= 0 ? 'GAIN' : 'DEFICIT',
      color: '#bf5af2',
      icon: Scale,
      details: [
        { label: 'Market Value', val: money(tier2.market_value_cents) },
        { label: 'Yield to Maturity', val: `${tier2.ytm_decimal}%` },
        { label: 'Modified Duration', val: `${tier2.modified_duration} yrs` },
        { label: 'Liquidation Haircut', val: `${tier2.liquidation_haircut_bps} bps` },
      ],
      desc: 'High-grade sovereign debt providing stable baseline yield and duration hedge. 2-day settlement or 200 bps liquidation haircut.',
    },
    {
      id: 'TIER_3',
      num: '3',
      name: 'Growth Equities',
      tag: 'Tier 3 · Surplus Growth',
      amount: tier3.market_value_cents,
      yieldRate: `σ ${tier3.volatility_decimal}%`,
      status: tier3.unrealized_pnl_cents >= 0 ? 'GAIN' : 'VOLATILE',
      color: '#ff9f0a',
      icon: TrendingUp,
      details: [
        { label: 'Market Value', val: money(tier3.market_value_cents) },
        { label: 'Cost Basis', val: money(tier3.cost_basis_cents) },
        { label: 'Annual Volatility', val: `${tier3.volatility_decimal}%` },
        { label: 'Emergency Slippage', val: `${tier3.emergency_slippage_bps / 100}%` },
      ],
      desc: 'Strategic equities allocation for long-term reserves. Higher capital growth with 15.0% emergency liquidation slippage model.',
    },
  ];

  return (
    <div className="four-tier-container">
      {/* Institutional Telemetry Ribbon */}
      <div className="institutional-telemetry-strip">
        <div className="telemetry-item">
          <div className="telemetry-label">
            <ShieldCheck size={14} className="text-blue" />
            <span>LIQUIDITY COVERAGE (LCR)</span>
          </div>
          <strong className="telemetry-val text-blue">{lcrRatio}%</strong>
          <small className="telemetry-note">Basel III Compliant (&gt;100%)</small>
        </div>

        <div className="telemetry-divider" />

        <div className="telemetry-item">
          <div className="telemetry-label">
            <Scale size={14} className="text-emerald" />
            <span>NET STABLE FUNDING (NSFR)</span>
          </div>
          <strong className="telemetry-val text-emerald">118.5%</strong>
          <small className="telemetry-note">Surplus Funding Ratio</small>
        </div>

        <div className="telemetry-divider" />

        <div className="telemetry-item">
          <div className="telemetry-label">
            <AlertTriangle size={14} className="text-amber" />
            <span>24H PARAMETRIC VaR (99%)</span>
          </div>
          <strong className="telemetry-val">$420,000</strong>
          <small className="telemetry-note">Quantile Shock Bound</small>
        </div>

        <div className="telemetry-divider" />

        <div className="telemetry-item">
          <div className="telemetry-label">
            <Zap size={14} className="text-purple" />
            <span>CAPITAL EFFICIENCY</span>
          </div>
          <strong className="telemetry-val text-purple">{capitalEfficiency}%</strong>
          <small className="telemetry-note">Active Yield Deployment</small>
        </div>
      </div>

      {/* Four-Tier Multi-Asset Capital Inspector */}
      <Panel
        className="four-tier-panel"
        title="Four-Tier Institutional Portfolio"
        subtitle="Canonical multi-asset framework: Cash, Repo, Sovereign Bonds, and Equities"
        action={
          <div className="tier-filter-segmented">
            <button
              type="button"
              className={selectedTier === 'ALL' ? 'active' : ''}
              onClick={() => setSelectedTier('ALL')}
            >
              All Tiers
            </button>
            {tiers.map((t) => (
              <button
                key={t.id}
                type="button"
                className={selectedTier === t.id ? 'active' : ''}
                onClick={() => setSelectedTier(t.id)}
              >
                T{t.num}
              </button>
            ))}
          </div>
        }
      >
        <div className="tier-cards-grid">
          {tiers
            .filter((t) => selectedTier === 'ALL' || selectedTier === t.id)
            .map((t) => {
              const Icon = t.icon;
              return (
                <div key={t.id} className="tier-card" style={{ '--tier-accent': t.color }}>
                  <div className="tier-card-header">
                    <div className="tier-badge-group">
                      <span className="tier-icon-box" style={{ background: `${t.color}18`, color: t.color }}>
                        <Icon size={16} />
                      </span>
                      <div>
                        <strong>{t.name}</strong>
                        <small>{t.tag}</small>
                      </div>
                    </div>
                    <span className="tier-yield-pill" style={{ borderColor: `${t.color}40`, color: t.color }}>
                      {t.yieldRate}
                    </span>
                  </div>

                  <div className="tier-balance-row">
                    <span className="tier-amount">{money(t.amount, true)}</span>
                    <Badge tone={t.status === 'SURPLUS' || t.status === 'GAIN' ? 'good' : t.status === 'DEFICIT' ? 'danger' : 'neutral'}>
                      {t.status}
                    </Badge>
                  </div>

                  <p className="tier-card-desc">{t.desc}</p>

                  <div className="tier-specs-grid">
                    {t.details.map((d) => (
                      <div key={d.label} className="tier-spec">
                        <span>{d.label}</span>
                        <strong>{d.val}</strong>
                      </div>
                    ))}
                  </div>
                </div>
              );
            })}
        </div>

        {/* Emergency Overdraft Facility Status Strip */}
        <div className={`overdraft-strip ${overdraft.is_active ? 'is-drawing' : 'is-cleared'}`}>
          <div className="overdraft-icon-wrap">
            <LockKeyhole size={18} />
          </div>
          <div className="overdraft-info">
            <strong>Emergency Overdraft Facility: {overdraft.liability_status}</strong>
            <span>
              {overdraft.is_active
                ? `Outstanding Liability: ${money(overdraft.borrowing_outstanding_cents)} · Financing Rate: ${rate(overdraft.financing_rate_bps)}`
                : `No active borrowing. Emergency credit line available at ${rate(overdraft.financing_rate_bps)} financing rate.`}
            </span>
          </div>
          <Badge tone={overdraft.is_active ? 'danger' : 'good'}>
            {overdraft.is_active ? 'LIABILITY ACTIVE' : 'CLEARED'}
          </Badge>
        </div>
      </Panel>

      {/* Multi-Asset Tactical Decisions & Recommendations */}
      <Panel
        className="multi-asset-decisions-panel"
        title="Multi-Asset Recommendations & Execution"
        subtitle="Autonomous treasury allocations evaluated across asset tiers"
      >
        <div className="multi-asset-decision-list">
          {MOCK_MULTI_ASSET_DECISIONS.map((dec) => (
            <div key={dec.id} className="multi-asset-row">
              <div className="decision-tier-indicator" style={{ background: tiers[dec.asset_tier]?.color ?? '#0071e3' }}>
                T{dec.asset_tier}
              </div>
              <div className="decision-main">
                <div className="decision-headline">
                  <strong>{dec.instrument} · {dec.action.replaceAll('_', ' ')}</strong>
                  <span className="decision-amount-tag">{money(dec.amount_cents)}</span>
                  <Badge tone={dec.executed ? 'good' : 'warning'}>
                    {dec.executed ? <CheckCircle2 size={11} /> : null}
                    {dec.executed ? 'Confirmed Executed' : 'Recommended · Pending Execution'}
                  </Badge>
                </div>
                <div className="decision-rationales">
                  {dec.rationale.map((r, idx) => (
                    <span key={idx} className="rationale-bullet">• {r}</span>
                  ))}
                </div>
                <small className="decision-liquidity-impact">
                  <Info size={11} className="inline-icon" /> {dec.liquidity_impact}
                </small>
              </div>
            </div>
          ))}
        </div>
      </Panel>
    </div>
  );
}
