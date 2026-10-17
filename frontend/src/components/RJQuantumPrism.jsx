import { useState, useRef } from 'react';
import { Activity, Shield, Zap, TrendingUp, CheckCircle2 } from 'lucide-react';

export default function RJQuantumPrism() {
  const [tilt, setTilt] = useState({ x: 0, y: 0 });
  const prismRef = useRef(null);

  const handleMouseMove = (e) => {
    if (!prismRef.current) return;
    const rect = prismRef.current.getBoundingClientRect();
    const x = (e.clientX - rect.left) / rect.width - 0.5;
    const y = (e.clientY - rect.top) / rect.height - 0.5;
    setTilt({ x: -(y * 14), y: x * 14 });
  };

  const handleMouseLeave = () => {
    setTilt({ x: 0, y: 0 });
  };

  return (
    <div
      ref={prismRef}
      className="rj-prism-stage"
      onMouseMove={handleMouseMove}
      onMouseLeave={handleMouseLeave}
      aria-hidden="true"
    >
      <div
        className="rj-prism-monolith"
        style={{
          transform: `perspective(1200px) rotateX(${tilt.x}deg) rotateY(${tilt.y}deg)`,
        }}
      >
        {/* Luminous soft ambient backlight (no elliptical rings) */}
        <div className="prism-ambient-halo" />

        {/* Dynamic Multi-Wave Kinetic Stream Canvas/SVG */}
        <svg className="prism-wave-engine" viewBox="0 0 900 360" preserveAspectRatio="none">
          <defs>
            <linearGradient id="streamGradBlue" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stopColor="#0071e3" stopOpacity="0.05" />
              <stop offset="35%" stopColor="#0071e3" stopOpacity="0.8" />
              <stop offset="65%" stopColor="#2997ff" stopOpacity="0.9" />
              <stop offset="100%" stopColor="#0071e3" stopOpacity="0.05" />
            </linearGradient>
            <linearGradient id="streamGradViolet" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stopColor="#bf5af2" stopOpacity="0.05" />
              <stop offset="40%" stopColor="#af52de" stopOpacity="0.75" />
              <stop offset="60%" stopColor="#bf5af2" stopOpacity="0.85" />
              <stop offset="100%" stopColor="#bf5af2" stopOpacity="0.05" />
            </linearGradient>
            <linearGradient id="streamGradGreen" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stopColor="#30d158" stopOpacity="0.05" />
              <stop offset="45%" stopColor="#34c759" stopOpacity="0.8" />
              <stop offset="55%" stopColor="#30d158" stopOpacity="0.9" />
              <stop offset="100%" stopColor="#30d158" stopOpacity="0.05" />
            </linearGradient>
            <filter id="streamGlow" x="-20%" y="-20%" width="140%" height="140%">
              <feGaussianBlur stdDeviation="3" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          </defs>

          {/* Precision Micro-Lattice Grid Lines */}
          <line x1="80" y1="90" x2="820" y2="90" stroke="rgba(0,113,227,0.08)" strokeDasharray="3 5" />
          <line x1="40" y1="180" x2="860" y2="180" stroke="rgba(0,113,227,0.14)" strokeDasharray="4 6" />
          <line x1="80" y1="270" x2="820" y2="270" stroke="rgba(0,113,227,0.08)" strokeDasharray="3 5" />

          {/* Fluid Laser Waveform Streams */}
          <path
            className="prism-stream stream-cash"
            d="M 40 180 C 220 90, 260 270, 450 180 C 640 90, 680 270, 860 180"
            stroke="url(#streamGradBlue)"
            filter="url(#streamGlow)"
          />
          <path
            className="prism-stream stream-reserve"
            d="M 40 180 C 200 250, 300 110, 450 180 C 600 250, 700 110, 860 180"
            stroke="url(#streamGradViolet)"
            filter="url(#streamGlow)"
          />
          <path
            className="prism-stream stream-yield"
            d="M 40 180 C 240 140, 280 220, 450 180 C 620 140, 660 220, 860 180"
            stroke="url(#streamGradGreen)"
            filter="url(#streamGlow)"
          />

          {/* Animated photon particles gliding along the streams */}
          <circle className="prism-photon photon-blue" r="4.5" />
          <circle className="prism-photon photon-violet" r="4" />
          <circle className="prism-photon photon-green" r="4" />
        </svg>

        {/* Central Precision-Machined Sapphire Glass Core */}
        <div className="prism-sapphire-core">
          <div className="sapphire-reflection-sheen" />
          <div className="sapphire-inner-bezel">
            <span className="sapphire-brand">RJ</span>
            <div className="sapphire-status">
              <span className="sapphire-dot" />
              <small>CAPITAL IN BALANCE</small>
            </div>
          </div>
          <div className="sapphire-micro-spec">
            <span>AUTONOMOUS TREASURY ENGINE</span>
          </div>
        </div>

        {/* Floating Glassmorphic Telemetry Capsules with Micro-Sparklines */}
        <div className="prism-pod pod-cash">
          <div className="pod-icon icon-blue">
            <Activity size={15} />
          </div>
          <div className="pod-body">
            <span className="pod-label">Instant Cash</span>
            <strong className="pod-val">$20.0M</strong>
            <small className="pod-meta">Ready to use anytime</small>
          </div>
        </div>

        <div className="prism-pod pod-reserve">
          <div className="pod-icon icon-violet">
            <Shield size={15} />
          </div>
          <div className="pod-body">
            <span className="pod-label">Safety Buffer</span>
            <strong className="pod-val">99.4%</strong>
            <small className="pod-meta">Emergency money protected</small>
          </div>
        </div>

        <div className="prism-pod pod-yield">
          <div className="pod-icon icon-green">
            <TrendingUp size={15} />
          </div>
          <div className="pod-body">
            <span className="pod-label">Annual Return</span>
            <strong className="pod-val">5.20%</strong>
            <small className="pod-meta">Earned automatically</small>
          </div>
        </div>
      </div>
    </div>
  );
}
