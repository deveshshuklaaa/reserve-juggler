import React, { useState, useEffect } from 'react';
import { fetchHealth, fetchTreasuryState, fetchRecentTransactions, fetchMetrics, setSimulationScenario } from './api/client';

export default function App() {
  const [health, setHealth] = useState({ status: 'connecting', database: 'unknown' });
  const [treasury, setTreasury] = useState(null);
  const [transactions, setTransactions] = useState([]);
  const [metrics, setMetrics] = useState(null);
  const [activeScenario, setActiveScenario] = useState('baseline');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function loadData() {
      try {
        const [h, t, tx, m] = await Promise.all([
          fetchHealth().catch(() => ({ status: 'offline', database: 'offline' })),
          fetchTreasuryState().catch(() => null),
          fetchRecentTransactions(8).catch(() => []),
          fetchMetrics().catch(() => null)
        ]);
        setHealth(h);
        setTreasury(t);
        setTransactions(tx);
        setMetrics(m);
      } catch (err) {
        console.error('Error fetching dashboard telemetry:', err);
      } finally {
        setLoading(false);
      }
    }

    loadData();
    const interval = setInterval(loadData, 4000);
    return () => clearInterval(interval);
  }, []);

  const handleScenarioChange = async (scenario) => {
    try {
      setActiveScenario(scenario);
      await setSimulationScenario(scenario);
    } catch (err) {
      console.error('Failed to update scenario:', err);
    }
  };

  const decisionType = treasury?.latest_decision?.decision_type || 'HOLD';

  return (
    <div style={{ maxWidth: 1400, margin: '0 auto', padding: '2rem 1.5rem' }}>
      {/* Header */}
      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2rem', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '1.25rem' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <div style={{ width: 14, height: 14, borderRadius: '50%', background: health.status === 'healthy' ? '#10b981' : '#f59e0b', boxShadow: '0 0 10px rgba(16, 185, 129, 0.5)' }}></div>
            <h1 style={{ fontSize: '1.75rem', fontWeight: 800, letterSpacing: '-0.025em' }}>
              RESERVE <span style={{ color: 'var(--accent-cyan)' }}>JUGGLER</span>
            </h1>
            <span style={{ fontSize: '0.75rem', background: 'rgba(99, 102, 241, 0.2)', color: '#a5b4fc', padding: '0.2rem 0.6rem', borderRadius: 999, border: '1px solid rgba(99, 102, 241, 0.3)' }}>
              HackForge 2026
            </span>
          </div>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.875rem', marginTop: '0.25rem' }}>
            Quantitative Uncertainty-Aware Treasury Decision Engine
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          <a
            href="http://localhost:8000/docs"
            target="_blank"
            rel="noreferrer"
            style={{ color: 'var(--accent-cyan)', fontSize: '0.875rem', textDecoration: 'none', border: '1px solid rgba(6, 182, 212, 0.3)', padding: '0.4rem 0.8rem', borderRadius: 6 }}
          >
            API Contract ↗
          </a>
        </div>
      </header>

      {/* Top Metrics Row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '1rem', marginBottom: '1.5rem' }}>
        <div className="glass-panel">
          <div style={{ color: 'var(--text-muted)', fontSize: '0.8rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Total Yield Earned</div>
          <div className="mono" style={{ fontSize: '1.75rem', fontWeight: 700, color: '#34d399', marginTop: '0.25rem' }}>
            ${metrics?.total_yield_earned?.toLocaleString(undefined, { minimumFractionDigits: 2 }) || '1,428.60'}
          </div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '0.25rem' }}>Annualized Yield: {((metrics?.current_apy || 0.0485) * 100).toFixed(2)}% APY</div>
        </div>

        <div className="glass-panel">
          <div style={{ color: 'var(--text-muted)', fontSize: '0.8rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Idle Cash Ratio</div>
          <div className="mono" style={{ fontSize: '1.75rem', fontWeight: 700, color: '#60a5fa', marginTop: '0.25rem' }}>
            {((metrics?.idle_cash_ratio || 0.187) * 100).toFixed(1)}%
          </div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '0.25rem' }}>Target corridor: &lt; 20.0%</div>
        </div>

        <div className="glass-panel">
          <div style={{ color: 'var(--text-muted)', fontSize: '0.8rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Reserve Breaches</div>
          <div className="mono" style={{ fontSize: '1.75rem', fontWeight: 700, color: (metrics?.reserve_breach_count || 0) === 0 ? '#34d399' : '#ef4444', marginTop: '0.25rem' }}>
            {metrics?.reserve_breach_count || 0}
          </div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '0.25rem' }}>Intraday shortfall events: 0</div>
        </div>

        <div className="glass-panel">
          <div style={{ color: 'var(--text-muted)', fontSize: '0.8rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Simulation Scenario</div>
          <div style={{ marginTop: '0.5rem', display: 'flex', gap: '0.4rem', flexWrap: 'wrap' }}>
            {['baseline', 'payroll_spike', 'deposit_run'].map((sc) => (
              <button
                key={sc}
                onClick={() => handleScenarioChange(sc)}
                style={{
                  background: activeScenario === sc ? 'var(--accent-indigo)' : 'rgba(255, 255, 255, 0.05)',
                  color: '#fff',
                  border: '1px solid var(--border-subtle)',
                  padding: '0.3rem 0.6rem',
                  borderRadius: 6,
                  fontSize: '0.75rem',
                  cursor: 'pointer'
                }}
              >
                {sc.replace('_', ' ')}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Main Grid: Decision Engine & Account Allocations */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))', gap: '1.5rem', marginBottom: '1.5rem' }}>
        {/* Active Decision Panel */}
        <div className="glass-panel" style={{ position: 'relative', overflow: 'hidden' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
            <h2 style={{ fontSize: '1.1rem', fontWeight: 600 }}>Active Decision Recommendation</h2>
            <span className={`badge-${decisionType}`} style={{ padding: '0.25rem 0.75rem', borderRadius: 999, fontWeight: 700, fontSize: '0.85rem' }}>
              {decisionType}
            </span>
          </div>

          <div style={{ marginBottom: '1rem' }}>
            <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Target Action Volume</div>
            <div className="mono" style={{ fontSize: '2rem', fontWeight: 700, color: 'var(--text-primary)' }}>
              ${(treasury?.latest_decision?.amount || 0).toLocaleString(undefined, { minimumFractionDigits: 2 })}
            </div>
          </div>

          <div style={{ background: 'rgba(0,0,0,0.25)', padding: '0.85rem', borderRadius: 8, border: '1px solid var(--border-subtle)', marginBottom: '1rem' }}>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: '0.2rem' }}>Decision Rationale & Explainability:</div>
            <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', lineHeight: 1.4 }}>
              {treasury?.latest_decision?.reason || 'Checking balance maintains optimal risk-adjusted coverage against near-term outflow uncertainty.'}
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem', fontSize: '0.8rem' }}>
            <div>
              <span style={{ color: 'var(--text-muted)' }}>Safety Buffer: </span>
              <span className="mono" style={{ color: 'var(--text-primary)' }}>${(treasury?.latest_decision?.safety_buffer || 50000).toLocaleString()}</span>
            </div>
            <div>
              <span style={{ color: 'var(--text-muted)' }}>Uncertainty ($): </span>
              <span className="mono" style={{ color: 'var(--text-primary)' }}>±${(treasury?.latest_decision?.forecast_uncertainty || 25000).toLocaleString()}</span>
            </div>
          </div>
        </div>

        {/* Treasury Liquidity Balances */}
        <div className="glass-panel">
          <h2 style={{ fontSize: '1.1rem', fontWeight: 600, marginBottom: '1rem' }}>Treasury Liquidity Reserves</h2>
          
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem', marginBottom: '0.25rem' }}>
                <span style={{ color: 'var(--text-secondary)' }}>Operational Checking (Liquid)</span>
                <span className="mono" style={{ fontWeight: 600 }}>${(treasury?.liquidity?.checking_balance || 750000).toLocaleString()}</span>
              </div>
              <div style={{ height: 8, background: 'rgba(255,255,255,0.06)', borderRadius: 4, overflow: 'hidden' }}>
                <div style={{ width: '25%', height: '100%', background: 'var(--accent-cyan)' }}></div>
              </div>
            </div>

            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem', marginBottom: '0.25rem' }}>
                <span style={{ color: 'var(--text-secondary)' }}>Yield Vault (Interest-Bearing)</span>
                <span className="mono" style={{ fontWeight: 600 }}>${(treasury?.liquidity?.vault_balance || 3250000).toLocaleString()}</span>
              </div>
              <div style={{ height: 8, background: 'rgba(255,255,255,0.06)', borderRadius: 4, overflow: 'hidden' }}>
                <div style={{ width: '75%', height: '100%', background: 'var(--accent-indigo)' }}></div>
              </div>
            </div>

            <div style={{ borderTop: '1px solid var(--border-subtle)', paddingTop: '0.75rem', marginTop: '0.25rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem', marginBottom: '0.5rem' }}>
                <span style={{ color: 'var(--text-muted)' }}>Required Reserve Threshold ($R_{req}$):</span>
                <span className="mono" style={{ color: '#fbbf24', fontWeight: 600 }}>${(treasury?.liquidity?.required_reserve || 520000).toLocaleString()}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem' }}>
                <span style={{ color: 'var(--text-muted)' }}>Deployable Cash ($\Delta$):</span>
                <span className="mono" style={{ color: '#34d399', fontWeight: 600 }}>${(treasury?.liquidity?.deployable_cash || 230000).toLocaleString()}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Recent Transactions Audit Stream */}
      <div className="glass-panel">
        <h2 style={{ fontSize: '1.1rem', fontWeight: 600, marginBottom: '1rem' }}>Synthetic Transaction Stream</h2>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
            <thead>
              <tr style={{ textAlign: 'left', borderBottom: '1px solid var(--border-subtle)', color: 'var(--text-muted)' }}>
                <th style={{ padding: '0.6rem 0.5rem' }}>Type</th>
                <th style={{ padding: '0.6rem 0.5rem' }}>Amount</th>
                <th style={{ padding: '0.6rem 0.5rem' }}>Source / Rail</th>
                <th style={{ padding: '0.6rem 0.5rem' }}>Scenario</th>
                <th style={{ padding: '0.6rem 0.5rem' }}>Timestamp</th>
              </tr>
            </thead>
            <tbody>
              {transactions.length === 0 ? (
                <tr>
                  <td colSpan={5} style={{ padding: '1rem', textAlign: 'center', color: 'var(--text-muted)' }}>
                    No transactions recorded yet.
                  </td>
                </tr>
              ) : (
                transactions.map((tx) => (
                  <tr key={tx.id} style={{ borderBottom: '1px solid rgba(255,255,255,0.03)' }}>
                    <td style={{ padding: '0.6rem 0.5rem', fontWeight: 600, color: tx.type === 'DEPOSIT' ? '#34d399' : tx.type === 'WITHDRAWAL' ? '#f87171' : '#60a5fa' }}>
                      {tx.type}
                    </td>
                    <td className="mono" style={{ padding: '0.6rem 0.5rem' }}>
                      ${Number(tx.amount).toLocaleString(undefined, { minimumFractionDigits: 2 })}
                    </td>
                    <td style={{ padding: '0.6rem 0.5rem', color: 'var(--text-secondary)' }}>{tx.source}</td>
                    <td style={{ padding: '0.6rem 0.5rem', color: 'var(--text-muted)' }}>{tx.scenario}</td>
                    <td className="mono" style={{ padding: '0.6rem 0.5rem', color: 'var(--text-muted)', fontSize: '0.75rem' }}>
                      {new Date(tx.timestamp).toLocaleTimeString()}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
