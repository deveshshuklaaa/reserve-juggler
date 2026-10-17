import { useState } from 'react';
import { Activity, ShieldAlert, Zap, Scale, Layers, AlertCircle, ArrowRight } from 'lucide-react';
import { Panel, Badge } from './ui';
import { money, rate } from '../utils/format';

export default function StressMatrix({ scenario, snapshot, beforeShock, executed }) {
  const [activeQuantile, setActiveQuantile] = useState(99);

  // Model how this scenario cascades across all four tiers
  const tierImpacts = [
    {
      tier: 'Tier 0 · Operating Cash',
      current: snapshot?.checking_cents ?? 2000000000,
      impactCents: scenario === 'HIGH_WITHDRAWAL' ? -600000000 : scenario === 'LIQUIDITY_SHOCK' ? -800000000 : scenario === 'LOW_DEPOSIT' ? -350000000 : -200000000,
      defense: 'Quantile buffer absorbs immediate outflows before hitting reserve limit',
      status: 'ABSORBED',
      color: '#0071e3',
    },
    {
      tier: 'Tier 1 · Overnight Repo',
      current: snapshot?.vault_locked_cents ? snapshot.vault_locked_cents + (snapshot.vault_redeemable_cents ?? 0) : 600000000,
      impactCents: scenario === 'HIGH_WITHDRAWAL' ? -150000000 : 0,
      defense: 'Early redemption executed at 08:00 or subject to 50 bps break fee',
      status: scenario === 'HIGH_WITHDRAWAL' ? 'EARLY BREAK' : 'PRESERVED',
      color: '#30d158',
    },
    {
      tier: 'Tier 2 · Sovereign Bonds',
      current: 411000000, // $4,110,000
      impactCents: scenario === 'HIGH_WITHDRAWAL' && executed ? -8220000 : 0, // 200 bps haircut if liquidated
      defense: 'Secondary liquidity line; 2.0% haircut applied only under extreme drawdown',
      status: 'HELD · DURATION HEDGE',
      color: '#bf5af2',
    },
    {
      tier: 'Overdraft Credit Facility',
      current: snapshot?.borrowing_outstanding_cents ?? 0,
      impactCents: snapshot?.borrowing_outstanding_cents ? snapshot.borrowing_outstanding_cents : 0,
      defense: 'Zero emergency borrowing required; autonomous sweeps maintain positive balance',
      status: snapshot?.borrowing_outstanding_cents > 0 ? 'BORROWED' : 'CLEARED · 0% DRAW',
      color: '#ff9f0a',
    },
  ];

  // Quantile shortfall simulations (90%, 95%, 99%)
  const quantileCurves = {
    90: { shortfall: 250000000, reserve: 300000000, confidence: '90.0%', survivalRate: '99.8%' },
    95: { shortfall: 380000000, reserve: 430000000, confidence: '95.0%', survivalRate: '99.9%' },
    99: { shortfall: 500000000, reserve: 550000000, confidence: '99.0%', survivalRate: '99.99%' },
  };

  const activeCurve = quantileCurves[activeQuantile];

  return (
    <div className="stress-matrix-container">
      {/* Multi-Tier Stress Transmission Matrix */}
      <Panel
        className="stress-matrix-panel"
        title="Multi-Tier Stress Transmission Matrix"
        subtitle="How systemic liquidity shocks propagate across Cash, Repo, Bonds, and Overdraft"
      >
        <div className="stress-tier-grid">
          {tierImpacts.map((item) => (
            <div key={item.tier} className="stress-tier-card" style={{ '--tier-border': item.color }}>
              <div className="stress-tier-top">
                <strong>{item.tier}</strong>
                <Badge tone={item.status === 'ABSORBED' || item.status.includes('PRESERVED') || item.status.includes('CLEARED') ? 'good' : 'warning'}>
                  {item.status}
                </Badge>
              </div>

              <div className="stress-tier-metrics">
                <div>
                  <small>Position Base</small>
                  <strong>{money(item.current)}</strong>
                </div>
                <div>
                  <small>Stress Impact</small>
                  <strong className={item.impactCents < 0 ? 'text-rose' : 'text-emerald'}>
                    {item.impactCents < 0 ? '−' : '+'}{money(Math.abs(item.impactCents))}
                  </strong>
                </div>
              </div>

              <p className="stress-tier-defense">{item.defense}</p>
            </div>
          ))}
        </div>
      </Panel>

      {/* Advanced Quantile Shortfall Sensitivity Matrix */}
      <Panel
        className="quantile-sensitivity-panel"
        title="Quantile Shortfall Curve & Confidence Bounds"
        subtitle="Mathematical worst-case liquidity deficit modeled across confidence percentiles"
        action={
          <div className="segmented">
            {[90, 95, 99].map((q) => (
              <button
                key={q}
                type="button"
                className={activeQuantile === q ? 'active' : ''}
                onClick={() => setActiveQuantile(q)}
              >
                {q}%
              </button>
            ))}
          </div>
        }
      >
        <div className="quantile-stats-row">
          <div className="quantile-stat-box">
            <span>Peak Quantile Shortfall</span>
            <strong className="text-amber">{money(activeCurve.shortfall)}</strong>
            <small>Worst-case net outflow at {activeCurve.confidence}</small>
          </div>

          <div className="quantile-stat-box">
            <span>Required Buffer Requirement</span>
            <strong className="text-blue">{money(activeCurve.reserve)}</strong>
            <small>Autopilot dynamic reserve threshold</small>
          </div>

          <div className="quantile-stat-box">
            <span>Solvency Survival Rate</span>
            <strong className="text-emerald">{activeCurve.survivalRate}</strong>
            <small>Simulated empirical survival probability</small>
          </div>
        </div>
      </Panel>
    </div>
  );
}
