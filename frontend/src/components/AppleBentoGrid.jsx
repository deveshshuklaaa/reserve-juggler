import { useState } from 'react';
import { Sparkles, ShieldCheck, Zap, BarChart3, Activity, ArrowUpRight } from 'lucide-react';

const bentoItems = [
  {
    id: 'forecasting',
    size: 'large',
    eyebrow: 'PREDICTIVE INTELLIGENCE',
    title: 'Look 24 hours into the future.',
    desc: 'Deep quantile simulation models incoming customer deposits and outgoing payroll batches before they arrive.',
    icon: Sparkles,
    glow: '#2997ff',
    badge: '99.4% Quantile Accuracy',
    visual: 'chart',
  },
  {
    id: 'sweeper',
    size: 'small',
    eyebrow: 'AUTONOMOUS SWEEPS',
    title: 'Zero idle cash. Ever.',
    desc: 'Surplus balances above your required reserve automatically sweep into short-term institutional yield.',
    icon: Zap,
    glow: '#30d158',
    badge: '+5.20% Active APY',
    visual: 'pulse',
  },
  {
    id: 'shock',
    size: 'small',
    eyebrow: 'STRESS LAB',
    title: 'Immune to shockwaves.',
    desc: 'Continuous real-time Monte Carlo testing against 500% withdrawal spikes and settlement delays.',
    icon: ShieldCheck,
    glow: '#bf5af2',
    badge: '100% Solvency Guard',
    visual: 'shield',
  },
  {
    id: 'arena',
    size: 'large',
    eyebrow: 'STRATEGY ARENA',
    title: 'Benchmark every alternative.',
    desc: 'Run multi-day tournament backtests across All Cash, Fixed Buffer, and Autonomous Autopilot strategies.',
    icon: BarChart3,
    glow: '#ffd60a',
    badge: '4.8x Capital Efficiency',
    visual: 'arena',
  },
];

export default function AppleBentoGrid() {
  const [hovered, setHovered] = useState(null);

  return (
    <div className="apple-bento-section">
      <div className="bento-header">
        <span className="apple-kicker">ARCHITECTURAL EXCELLENCE</span>
        <h2 className="bento-headline">
          Every capability.<br />
          <span>Polished to perfection.</span>
        </h2>
        <p className="bento-subtitle">
          Engineered for institutional finance teams who refuse to trade yield for liquidity safety.
        </p>
      </div>

      <div className="bento-grid">
        {bentoItems.map((item) => {
          const Icon = item.icon;
          const isHovered = hovered === item.id;
          return (
            <div
              key={item.id}
              className={`bento-card bento-${item.size} ${isHovered ? 'is-hovered' : ''}`}
              onMouseEnter={() => setHovered(item.id)}
              onMouseLeave={() => setHovered(null)}
              style={{ '--card-glow': item.glow }}
            >
              <div className="bento-card-bg-glow" />
              <div className="bento-card-header">
                <div className="bento-icon-wrapper" style={{ color: item.glow }}>
                  <Icon size={24} />
                </div>
                <span className="bento-badge" style={{ borderColor: `${item.glow}40`, color: item.glow }}>
                  {item.badge}
                </span>
              </div>

              <div className="bento-card-content">
                <span className="bento-eyebrow">{item.eyebrow}</span>
                <h3 className="bento-title">{item.title}</h3>
                <p className="bento-desc">{item.desc}</p>
              </div>

              {/* Card Visual Graphic */}
              <div className="bento-visual-container">
                {item.visual === 'chart' && (
                  <div className="bento-chart-art">
                    <svg viewBox="0 0 400 120" className="bento-svg-wave">
                      <defs>
                        <linearGradient id="bento-grad" x1="0" y1="0" x2="0" y2="1">
                          <stop stopColor="#2997ff" stopOpacity="0.4" />
                          <stop offset="100%" stopColor="#2997ff" stopOpacity="0" />
                        </linearGradient>
                      </defs>
                      <path d="M0,80 Q100,20 200,60 T400,20 L400,120 L0,120 Z" fill="url(#bento-grad)" />
                      <path d="M0,80 Q100,20 200,60 T400,20" fill="none" stroke="#2997ff" strokeWidth="3" />
                      <circle cx="200" cy="60" r="5" fill="#2997ff" stroke="#ffffff" strokeWidth="2" />
                    </svg>
                  </div>
                )}
                {item.visual === 'pulse' && (
                  <div className="bento-pulse-art">
                    <div className="pulse-ring ring-1" />
                    <div className="pulse-ring ring-2" />
                    <div className="pulse-center">
                      <Zap size={22} className="text-emerald" />
                    </div>
                  </div>
                )}
                {item.visual === 'shield' && (
                  <div className="bento-shield-art">
                    <div className="shield-hexagon">
                      <ShieldCheck size={32} className="text-violet" />
                    </div>
                  </div>
                )}
                {item.visual === 'arena' && (
                  <div className="bento-arena-art">
                    <div className="arena-mini-bars">
                      <div className="mini-bar bar-legacy">
                        <span>Static</span>
                        <div className="bar-track"><div className="bar-fill" style={{ width: '45%' }} /></div>
                      </div>
                      <div className="mini-bar bar-rj">
                        <span>RJ Pro</span>
                        <div className="bar-track"><div className="bar-fill" style={{ width: '94%', background: '#ffd60a' }} /></div>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
