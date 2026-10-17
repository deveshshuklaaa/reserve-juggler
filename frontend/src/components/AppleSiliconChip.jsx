import { useState, useRef } from 'react';
import { Cpu, ShieldCheck, TrendingUp, Zap, Sparkles, Layers } from 'lucide-react';

const cores = [
  {
    id: 'predictive',
    name: 'Neural Forecast Engine',
    short: 'NFE-16',
    icon: Sparkles,
    color: '#2997ff',
    stat: '99.4% Accuracy',
    desc: 'Deep quantile prediction predicting net cash deficits up to 24 hours in advance with non-linear volatility awareness.',
  },
  {
    id: 'shock',
    name: 'Shock Absorption Core',
    short: 'SAC-PRO',
    icon: ShieldCheck,
    color: '#bf5af2',
    stat: 'Zero Default Risk',
    desc: 'Dynamic liquidity perimeter calculation. Automatically reserves defensive cash reserves before withdrawal contagion spreads.',
  },
  {
    id: 'yield',
    name: 'Yield Harvester Unit',
    short: 'YHU-MAX',
    icon: TrendingUp,
    color: '#30d158',
    stat: '+482 bps Alpha',
    desc: 'Autonomous sweeps into ultra-short yield vaults without risking checking liquidity or incurring redemption penalties.',
  },
  {
    id: 'fabric',
    name: 'Zero-Latency Settlement',
    short: 'ZLS-MESH',
    icon: Zap,
    color: '#ffd60a',
    stat: '<15ms Execution',
    desc: 'Direct atomic ledger transitions between checking reserves and institutional liquidity pools.',
  },
];

export default function AppleSiliconChip() {
  const [activeCore, setActiveCore] = useState(cores[0]);
  const [tilt, setTilt] = useState({ x: 0, y: 0 });
  const chipRef = useRef(null);

  const handleMouseMove = (e) => {
    if (!chipRef.current) return;
    const rect = chipRef.current.getBoundingClientRect();
    const x = (e.clientX - rect.left) / rect.width - 0.5;
    const y = (e.clientY - rect.top) / rect.height - 0.5;
    setTilt({ x: -(y * 14), y: x * 14 });
  };

  const handleMouseLeave = () => {
    setTilt({ x: 0, y: 0 });
  };

  return (
    <div className="silicon-showcase" id="silicon-specs">
      <div className="silicon-header">
        <span className="apple-kicker">RJ-1 ULTRA SILICON</span>
        <h2 className="silicon-title">
          Unprecedented power.<br />
          <span>Engineered for treasury.</span>
        </h2>
        <p className="silicon-intro">
          The first dedicated autonomous liquidity architecture. Designed from the silicon up to predict cash shocks, automate yields, and maintain balance sheet equilibrium.
        </p>
      </div>

      <div className="silicon-interactive-stage">
        {/* The 3D Physical Chip */}
        <div
          ref={chipRef}
          className="silicon-chip-container"
          onMouseMove={handleMouseMove}
          onMouseLeave={handleMouseLeave}
          style={{
            transform: `perspective(1200px) rotateX(${tilt.x}deg) rotateY(${tilt.y}deg)`,
          }}
        >
          <div className="silicon-chip-die">
            <div className="silicon-chip-glow" style={{ borderColor: activeCore.color }} />
            <div className="silicon-metallic-edge" />
            
            {/* Center RJ Logo */}
            <div className="silicon-center-brand">
              <div className="silicon-logo-box">
                <Cpu size={36} className="silicon-cpu-icon" />
                <span className="silicon-brand-text">RJ-1</span>
                <span className="silicon-edition">ULTRA</span>
              </div>
              <div className="silicon-bus-trace" />
            </div>

            {/* Microarchitecture Cores */}
            <div className="silicon-grid-cores">
              {cores.map((c) => {
                const isSelected = activeCore.id === c.id;
                const Icon = c.icon;
                return (
                  <button
                    key={c.id}
                    type="button"
                    className={`silicon-core-block ${isSelected ? 'is-selected' : ''}`}
                    onClick={() => setActiveCore(c)}
                    style={{ '--core-color': c.color }}
                  >
                    <div className="core-block-header">
                      <Icon size={18} style={{ color: c.color }} />
                      <span className="core-code">{c.short}</span>
                    </div>
                    <strong className="core-name">{c.name}</strong>
                    <span className="core-stat-pill">{c.stat}</span>
                    <div className="core-pulse-line" />
                  </button>
                );
              })}
            </div>

            {/* Spec bus pins */}
            <div className="silicon-pins silicon-pins-top" />
            <div className="silicon-pins silicon-pins-bottom" />
            <div className="silicon-pins silicon-pins-left" />
            <div className="silicon-pins silicon-pins-right" />
          </div>
        </div>

        {/* Core Detail Inspector Card */}
        <div className="silicon-inspector-card">
          <div className="inspector-badge" style={{ color: activeCore.color, borderColor: `${activeCore.color}40`, background: `${activeCore.color}15` }}>
            <activeCore.icon size={16} />
            <span>SELECTED SUBSYSTEM · {activeCore.short}</span>
          </div>
          <h3 className="inspector-title">{activeCore.name}</h3>
          <div className="inspector-stat-huge" style={{ color: activeCore.color }}>
            {activeCore.stat}
          </div>
          <p className="inspector-desc">{activeCore.desc}</p>
          
          <div className="inspector-specs-grid">
            <div className="spec-metric">
              <span className="spec-metric-label">Latency</span>
              <strong className="spec-metric-value">&lt; 15ms</strong>
            </div>
            <div className="spec-metric">
              <span className="spec-metric-label">Throughput</span>
              <strong className="spec-metric-value">250k Ops/sec</strong>
            </div>
            <div className="spec-metric">
              <span className="spec-metric-label">Architecture</span>
              <strong className="spec-metric-value">5nm Liquid Die</strong>
            </div>
            <div className="spec-metric">
              <span className="spec-metric-label">Security</span>
              <strong className="spec-metric-value">Cryptographic Proof</strong>
            </div>
          </div>

          <div className="inspector-prompt">
            <span className="inspector-hint">Touch or hover any core on the chip to inspect microarchitecture</span>
          </div>
        </div>
      </div>
    </div>
  );
}
