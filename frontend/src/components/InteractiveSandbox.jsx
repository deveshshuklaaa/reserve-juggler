import { useState, useMemo } from 'react';
import { Sliders, Shield, Zap, TrendingUp, AlertTriangle, CheckCircle2, RotateCcw } from 'lucide-react';
import { money } from '../utils/format';

export default function InteractiveSandbox() {
  const [shockValue, setShockValue] = useState(-5000000); // -$5M default shock
  const [autopilot, setAutopilot] = useState(true);
  const [preset, setPreset] = useState('moderate');

  // Interactive calculations
  const state = useMemo(() => {
    const baseChecking = 20000000; // $20M base
    const baseReserve = 4500000;   // $4.5M required reserve
    const baseVault = 12000000;    // $12M invested in yield vault

    if (autopilot) {
      // RJ Autopilot: absorbs shocks, pulls from vault if needed without penalty, keeps reserves safe
      const netChecking = Math.max(2000000, baseChecking + shockValue);
      const dynamicReserve = Math.max(3000000, baseReserve + Math.abs(shockValue) * 0.25);
      const dynamicVault = shockValue < -8000000 ? baseVault - 3000000 : baseVault;
      const yieldEarned = Math.round((dynamicVault * 0.052) / 365 * 30);
      const isDefended = netChecking >= dynamicReserve * 0.8;

      return {
        checking: netChecking,
        reserve: dynamicReserve,
        vault: dynamicVault,
        yieldEarned,
        status: isDefended ? 'OPTIMIZED' : 'DEFENDING',
        statusText: isDefended ? 'Resilient & Protected' : 'Autonomous Defense Engaged',
        healthScore: Math.min(100, Math.round((netChecking / dynamicReserve) * 85)),
        overdraftRisk: '0.00%',
        color: '#2997ff',
      };
    } else {
      // Manual Legacy: fixed reserves, checking gets crushed, zero dynamic rebalance
      const netChecking = baseChecking + shockValue;
      const dynamicReserve = baseReserve;
      const dynamicVault = baseVault;
      const yieldEarned = Math.round((dynamicVault * 0.02) / 365 * 30);
      const isDefended = netChecking > dynamicReserve;

      return {
        checking: Math.max(0, netChecking),
        reserve: dynamicReserve,
        vault: dynamicVault,
        yieldEarned,
        status: isDefended ? 'STABLE' : 'CRITICAL DEFICIT',
        statusText: isDefended ? 'Static Allocation' : 'Overdraft Warning!',
        healthScore: Math.max(10, Math.min(100, Math.round((netChecking / dynamicReserve) * 50))),
        overdraftRisk: netChecking < dynamicReserve ? '42.8%' : '3.2%',
        color: isDefended ? '#eab308' : '#ef4444',
      };
    }
  }, [shockValue, autopilot]);

  const applyPreset = (type, val) => {
    setPreset(type);
    setShockValue(val);
  };

  return (
    <div className="sandbox-showcase">
      <div className="sandbox-header">
        <span className="apple-kicker">HANDS-ON SIMULATOR</span>
        <h2 className="sandbox-title">
          Test it live.<br />
          <span>Feel the control.</span>
        </h2>
        <p className="sandbox-subtitle">
          Drag the stress slider to simulate extreme liquidity shocks and watch how Reserve Juggler dynamically stabilizes checking reserves compared to legacy static rules.
        </p>
      </div>

      <div className="sandbox-card">
        {/* Top Controls Toolbar */}
        <div className="sandbox-toolbar">
          <div className="sandbox-mode-toggle">
            <span className="mode-label">TREASURY ENGINE</span>
            <div className="mode-buttons">
              <button
                type="button"
                className={`mode-btn ${autopilot ? 'active' : ''}`}
                onClick={() => setAutopilot(true)}
              >
                <Zap size={15} /> Reserve Juggler Autopilot
              </button>
              <button
                type="button"
                className={`mode-btn ${!autopilot ? 'active' : ''}`}
                onClick={() => setAutopilot(false)}
              >
                Legacy Static Rules
              </button>
            </div>
          </div>

          <div className="sandbox-presets">
            <span className="mode-label">QUICK SCENARIOS</span>
            <div className="preset-chips">
              <button
                type="button"
                className={`preset-chip ${preset === 'mild' ? 'active' : ''}`}
                onClick={() => applyPreset('mild', -2000000)}
              >
                -$2M Routine Outflow
              </button>
              <button
                type="button"
                className={`preset-chip ${preset === 'moderate' ? 'active' : ''}`}
                onClick={() => applyPreset('moderate', -6000000)}
              >
                -$6M Spike
              </button>
              <button
                type="button"
                className={`preset-chip ${preset === 'extreme' ? 'active' : ''}`}
                onClick={() => applyPreset('extreme', -12000000)}
              >
                -$12M Bank Run Surge
              </button>
              <button
                type="button"
                className={`preset-chip ${preset === 'inflow' ? 'active' : ''}`}
                onClick={() => applyPreset('inflow', 8000000)}
              >
                +$8M Capital Deposit
              </button>
            </div>
          </div>
        </div>

        {/* Dynamic Interactive Slider */}
        <div className="sandbox-slider-box">
          <div className="slider-header">
            <div className="slider-label-group">
              <Sliders size={18} className="slider-icon" />
              <strong>Simulated Cash Flow Shock</strong>
            </div>
            <span className={`slider-value-display ${shockValue < 0 ? 'is-negative' : 'is-positive'}`}>
              {shockValue >= 0 ? `+${money(shockValue * 100, true)}` : money(shockValue * 100, true)}
            </span>
          </div>
          <input
            type="range"
            min="-15000000"
            max="15000000"
            step="500000"
            value={shockValue}
            onChange={(e) => {
              setShockValue(Number(e.target.value));
              setPreset('custom');
            }}
            className="apple-range-slider"
            aria-label="Simulated cash flow shock slider"
          />
          <div className="slider-ticks">
            <span>-$15M Shock</span>
            <span>$0 Neutral</span>
            <span>+$15M Surge</span>
          </div>
        </div>

        {/* Real-time Dynamic Visual Fluid Wave & Meters */}
        <div className="sandbox-display-grid">
          <div className="sandbox-meter checking-meter">
            <div className="meter-header">
              <span>CHECKING CASH</span>
              <Shield size={16} />
            </div>
            <div className="meter-value" title={money(state.checking * 100)}>
              {money(state.checking * 100, true)}
            </div>
            <div className="meter-bar-track">
              <div
                className="meter-bar-fill"
                style={{
                  width: `${Math.min(100, (state.checking / 25000000) * 100)}%`,
                  background: state.checking < state.reserve ? '#ef4444' : '#2997ff',
                }}
              />
            </div>
            <span className="meter-footnote">
              {state.checking < state.reserve ? 'Reserve Breached!' : 'Fully Liquid & Deployable'}
            </span>
          </div>

          <div className="sandbox-meter reserve-meter">
            <div className="meter-header">
              <span>REQUIRED RESERVE</span>
              <AlertTriangle size={16} />
            </div>
            <div className="meter-value" title={money(state.reserve * 100)}>
              {money(state.reserve * 100, true)}
            </div>
            <div className="meter-bar-track">
              <div
                className="meter-bar-fill"
                style={{
                  width: `${Math.min(100, (state.reserve / 15000000) * 100)}%`,
                  background: '#bf5af2',
                }}
              />
            </div>
            <span className="meter-footnote">
              {autopilot ? 'Dynamic Quantile Buffer' : 'Fixed Static Limit'}
            </span>
          </div>

          <div className="sandbox-meter yield-meter">
            <div className="meter-header">
              <span>MONTHLY ESTIMATED YIELD</span>
              <TrendingUp size={16} />
            </div>
            <div className="meter-value" title={money(state.yieldEarned * 100)}>
              +{money(state.yieldEarned * 100, true)}
            </div>
            <div className="meter-bar-track">
              <div
                className="meter-bar-fill"
                style={{
                  width: `${Math.min(100, (state.yieldEarned / 60000) * 100)}%`,
                  background: '#30d158',
                }}
              />
            </div>
            <span className="meter-footnote">
              {autopilot ? '5.2% APY Swept Overnight' : '2.0% Stagnant Cash Yield'}
            </span>
          </div>
        </div>

        {/* Dynamic Status Banner */}
        <div className={`sandbox-status-strip ${autopilot ? 'autopilot-active' : 'legacy-active'}`}>
          <div className="status-indicator-ring">
            {autopilot ? <CheckCircle2 size={24} className="text-emerald" /> : <AlertTriangle size={24} className="text-amber" />}
          </div>
          <div className="status-copy">
            <strong>{state.statusText}</strong>
            <span>
              {autopilot
                ? `System automatically balanced reserves. Risk of overdraft: ${state.overdraftRisk}. Treasury Health Score: ${state.healthScore}%.`
                : `Legacy rules caused rigid cash immobilization. Risk of overdraft: ${state.overdraftRisk}. Treasury Health Score: ${state.healthScore}%.`}
            </span>
          </div>
          <button
            type="button"
            className="sandbox-reset-btn"
            onClick={() => {
              setShockValue(-5000000);
              setAutopilot(true);
              setPreset('moderate');
            }}
          >
            <RotateCcw size={14} /> Reset
          </button>
        </div>
      </div>
    </div>
  );
}
