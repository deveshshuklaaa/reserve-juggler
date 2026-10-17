import { useState } from 'react';
import { Coins, LockKeyhole, Landmark, TrendingUp } from 'lucide-react';

const tiers = [
  { name: 'Cash', icon: Coins, color: '#0071e3', detail: 'Available for operating payments. The reserve starts here.' },
  { name: 'Repo', icon: LockKeyhole, color: '#278975', detail: 'Overnight allocation with explicit maturity and redemption terms.' },
  { name: 'Bonds', icon: Landmark, color: '#7563b6', detail: 'Market value, duration, and settlement timing in one view.' },
  { name: 'Equities', icon: TrendingUp, color: '#a87d39', detail: 'Longer-term exposure with visible price and liquidity risk.' },
];

export default function CapitalFlow() {
  const [selected, setSelected] = useState(0);
  return <div className="capital-flow" style={{ '--flow-color': tiers[selected].color }}>
    <div className="capital-flow-visual" aria-hidden="true">
      <svg viewBox="0 0 800 130" preserveAspectRatio="none"><path className="flow-track" d="M40 65H760" /><path className="flow-current" d="M40 65H760" />{[100, 300, 500, 700].map((x, index) => <g key={x} className={selected === index ? 'flow-node selected' : 'flow-node'}><circle cx={x} cy="65" r="25" /><circle cx={x} cy="65" r="7" /></g>)}</svg>
      <div className="capital-flow-scan" />
    </div>
    <div className="capital-flow-controls" role="group" aria-label="Explore the capital tiers">{tiers.map((tier, index) => {
      const Icon = tier.icon;
      return <button key={tier.name} type="button" aria-pressed={selected === index} aria-controls="capital-flow-description" onClick={() => setSelected(index)} className={selected === index ? 'selected' : ''}><Icon size={19} /><span><small>0{index}</small>{tier.name}</span></button>;
    })}</div>
    <p id="capital-flow-description" className="capital-flow-description" aria-live="polite" aria-atomic="true">{tiers[selected].detail}</p>
  </div>;
}
