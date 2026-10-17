import { useState, useMemo } from 'react';
import { Sliders, Shield, Zap, TrendingUp, AlertTriangle, CheckCircle2, RotateCcw } from 'lucide-react';
import { money } from '../utils/format';
import { previewLiquidityShock } from '../mocks/liquidityPreview';

export default function InteractiveSandbox() {
  const [shockValue, setShockValue] = useState(-6000000);
  const [autopilot, setAutopilot] = useState(true);
  const [preset, setPreset] = useState('moderate');

  // Frontend illustration only: no asset sales, invented cash, or execution.
  const state = useMemo(() => previewLiquidityShock(shockValue * 100, autopilot), [shockValue, autopilot]);
  const applyPreset = (type, val) => {
    setPreset(type);
    setShockValue(val);
  };

  return (
    <div className="sandbox-showcase">
      <div className="sandbox-header">
        <span className="apple-kicker">HANDS-ON SIMULATOR</span>
        <h2 className="sandbox-title">
          Move the liquidity.<br />
          <span>See the trade-off.</span>
        </h2>
        <p className="sandbox-subtitle">
          Illustrative mock: move cash flows and compare a fixed buffer with an adaptive buffer. Proposed allocations leave cash unchanged until execution.
        </p>
      </div>

      <div className="sandbox-card">
        {/* Top Controls Toolbar */}
        <div className="sandbox-toolbar">
          <div className="sandbox-mode-toggle">
            <span className="mode-label">PREVIEW POLICY</span>
            <div className="mode-buttons">
              <button
                type="button"
                className={`mode-btn ${autopilot ? 'active' : ''}`}
                onClick={() => setAutopilot(true)}
              >
                <Zap size={15} /> Adaptive buffer
              </button>
              <button
                type="button"
                className={`mode-btn ${!autopilot ? 'active' : ''}`}
                onClick={() => setAutopilot(false)}
              >
                Fixed buffer
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
            <div className="meter-value" title={money(state.checking_cents)}>
              {money(state.checking_cents, true)}
            </div>
            <div className="meter-bar-track">
              <div
                className="meter-bar-fill"
                style={{
                  width: `${Math.min(100, (state.checking_cents / 3500000000) * 100)}%`,
                  background: state.reserve_deficit_cents > 0 ? '#ef4444' : '#2997ff',
                }}
              />
            </div>
            <span className="meter-footnote">
              {state.reserve_deficit_cents > 0 ? 'Reserve Breached!' : 'Available cash after the illustrative flow'}
            </span>
          </div>

          <div className="sandbox-meter reserve-meter">
            <div className="meter-header">
              <span>REQUIRED RESERVE</span>
              <AlertTriangle size={16} />
            </div>
            <div className="meter-value" title={money(state.required_reserve_cents)}>
              {money(state.required_reserve_cents, true)}
            </div>
            <div className="meter-bar-track">
              <div
                className="meter-bar-fill"
                style={{
                  width: `${Math.min(100, (state.required_reserve_cents / 1500000000) * 100)}%`,
                  background: '#bf5af2',
                }}
              />
            </div>
            <span className="meter-footnote">
              {autopilot ? 'Illustrative adaptive buffer' : 'Fixed Static Limit'}
            </span>
          </div>

          <div className="sandbox-meter yield-meter">
            <div className="meter-header">
              <span>PROPOSED ALLOCATION</span>
              <TrendingUp size={16} />
            </div>
            <div className="meter-value" title={money(state.proposed_allocation_cents)}>
              {money(state.proposed_allocation_cents, true)}
            </div>
            <div className="meter-bar-track">
              <div
                className="meter-bar-fill"
                style={{
                  width: `${Math.min(100, (state.proposed_allocation_cents / 3500000000) * 100)}%`,
                  background: '#30d158',
                }}
              />
            </div>
            <span className="meter-footnote">
              {autopilot ? 'Unexecuted surplus proposal' : 'Fixed policy keeps cash unchanged'}
            </span>
          </div>
        </div>

        {/* Dynamic Status Banner */}
        <div className={`sandbox-status-strip ${autopilot ? 'autopilot-active' : 'legacy-active'}`}>
          <div className="status-indicator-ring">
            {autopilot ? <CheckCircle2 size={24} className="text-emerald" /> : <AlertTriangle size={24} className="text-amber" />}
          </div>
          <div className="status-copy">
            <strong>{state.reserve_deficit_cents > 0 ? 'Reserve shortfall' : 'Cash covers the preview reserve'}</strong>
            <span>
              {state.reserve_deficit_cents > 0
                ? `${money(state.reserve_deficit_cents)} below the preview reserve. No liquidation or borrowing has been executed.`
                : 'Frontend illustration only. The adaptive rule adds 25% of an outflow to the base buffer; it is not an engine forecast.'}
            </span>
          </div>
          <button
            type="button"
            className="sandbox-reset-btn"
            onClick={() => {
              setShockValue(-6000000);
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
