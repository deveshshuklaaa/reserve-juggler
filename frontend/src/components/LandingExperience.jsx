import { useEffect, useRef, useState } from 'react';
import { ArrowDown, ArrowRight, MoveUpRight } from 'lucide-react';
import { useSimulation } from '../context/SimulationContext';
import { Button } from './ui';

const story = [
  { number: '01', label: 'See ahead', title: <>Know where cash<br /><em>is heading.</em></>, note: 'A clearer view of incoming flows, reserve needs, and available capital.' },
  { number: '02', label: 'Test the edge', title: <>Pressure-test<br /><em>every move.</em></>, note: 'Explore liquidity shocks before they reach the balance sheet.' },
  { number: '03', label: 'Choose well', title: <>Compare the paths.<br /><em>Keep the proof.</em></>, note: 'Put strategies through the same conditions and inspect the result.' },
];

function FlowScene() {
  return <div className="landing-scene landing-flow-scene" aria-hidden="true">
    <div className="scene-header"><span>Liquidity outlook</span><span className="scene-live"><i /> SIMULATED</span></div>
    <div className="scene-stat"><small>Available capital</small><strong>$20.00M</strong><span>Illustrative starting balance</span></div>
    <svg className="scene-flow-chart" viewBox="0 0 700 260" preserveAspectRatio="none">
      <defs><linearGradient id="flow-fill" x1="0" y1="0" x2="0" y2="1"><stop stopColor="#1576e8" stopOpacity=".24" /><stop offset="1" stopColor="#1576e8" stopOpacity="0" /></linearGradient></defs>
      <path className="scene-grid-line" d="M0 42H700M0 104H700M0 166H700M0 228H700" />
      <path className="scene-flow-fill" d="M0 181 C75 170 93 194 150 153 S228 144 284 127 S350 150 416 113 S502 121 558 81 S633 96 700 42 L700 260H0Z" />
      <path className="scene-flow-path" d="M0 181 C75 170 93 194 150 153 S228 144 284 127 S350 150 416 113 S502 121 558 81 S633 96 700 42" />
      <circle className="scene-flow-dot" cx="558" cy="81" r="8" />
    </svg>
    <div className="scene-axis"><span>Now</span><span>Next horizon</span></div>
  </div>;
}

function ShockScene() {
  return <div className="landing-scene landing-shock-scene" aria-hidden="true">
    <div className="scene-header"><span>Liquidity Shock Lab</span><span className="scene-live"><i /> SIMULATED</span></div>
    <div className="shock-visual"><div className="shock-ripple ripple-a" /><div className="shock-ripple ripple-b" /><div className="shock-ripple ripple-c" /><div className="shock-core"><span>LIQUIDITY</span><strong>Resilient<br />by design.</strong></div></div>
    <div className="shock-tags"><span>Withdrawal spike</span><span>Settlement delay</span><span>Reserve response</span></div>
  </div>;
}

function ArenaScene() {
  return <div className="landing-scene landing-arena-scene" aria-hidden="true">
    <div className="scene-header"><span>Treasury Strategy Arena</span><span className="scene-live"><i /> SIMULATED</span></div>
    <div className="arena-lines"><div className="arena-line"><span>01</span><strong>All cash</strong><i className="arena-bar bar-one" /></div><div className="arena-line"><span>02</span><strong>Cash + yield</strong><i className="arena-bar bar-two" /></div><div className="arena-line"><span>03</span><strong>Reserve Juggler</strong><i className="arena-bar bar-three" /></div></div>
    <div className="arena-note"><span>Same conditions.</span><span>No preset winner.</span></div>
  </div>;
}

const scenes = [FlowScene, ShockScene, ArenaScene];

export default function LandingExperience() {
  const { createRun, busy } = useSimulation();
  const root = useRef(null);
  const [active, setActive] = useState(0);

  useEffect(() => {
    const element = root.current;
    if (!element || !('IntersectionObserver' in window)) return undefined;
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          setActive(Number(entry.target.dataset.scene));
          entry.target.classList.add('landing-visible');
        }
      });
    }, { rootMargin: '-32% 0px -32% 0px' });
    element.querySelectorAll('[data-scene]').forEach((scene) => observer.observe(scene));
    return () => observer.disconnect();
  }, []);

  return <div className="landing-experience" ref={root}>
    <section className="landing-opening" aria-labelledby="landing-title">
      <div className="landing-opening-copy"><span className="landing-eyebrow">RESERVE JUGGLER <i /> TREASURY AUTOPILOT</span><h1 id="landing-title">Treasury,<br /><span>in motion.</span></h1><p>Clarity for every cash decision.</p><div className="landing-opening-actions"><Button variant="primary" busy={busy} onClick={() => createRun()}>Open Command Center <ArrowRight size={17} /></Button><a href="#landing-story" className="landing-text-link">Explore the experience <ArrowDown size={16} /></a></div></div>
      <div className="landing-hero-art" aria-hidden="true"><div className="hero-art-glow" /><div className="hero-art-orbit orbit-outer" /><div className="hero-art-orbit orbit-middle" /><div className="hero-art-orbit orbit-inner" /><div className="hero-art-center"><span>RJ</span><small>CAPITAL IN BALANCE</small></div><div className="hero-art-chip chip-cash"><i /> CASH</div><div className="hero-art-chip chip-reserve"><i /> RESERVE</div><div className="hero-art-chip chip-yield"><i /> YIELD</div></div>
      <div className="landing-scroll-note"><span>Scroll to explore</span><ArrowDown size={15} /></div>
    </section>

    <section className="landing-narrative" id="landing-story" aria-label="Explore Reserve Juggler">
      <div className="landing-narrative-track"><div className="landing-narrative-inner"><div className="landing-stage-top"><span>ONE CONNECTED VIEW</span><span>0{active + 1} / 03</span></div><div className="landing-stage-visual">{scenes.map((Scene, index) => <div key={index} className={`landing-visual-layer ${active === index ? 'is-active' : ''}`}><Scene /></div>)}</div><div className="landing-stage-dots" aria-hidden="true">{story.map((item, index) => <i key={item.number} className={active === index ? 'is-active' : ''} />)}</div></div></div>
      <div className="landing-narrative-copy">{story.map((item, index) => <div key={item.number} className={`landing-story-step ${active === index ? 'is-active' : ''}`} data-scene={index}><span className="landing-step-label">{item.number} / {item.label}</span><h2>{item.title}</h2><p>{item.note}</p></div>)}</div>
    </section>

    <section className="landing-finale"><span className="landing-eyebrow">READY WHEN YOU ARE</span><h2>See the whole picture.<br /><span>Then make your move.</span></h2><p>Start a deterministic demo and explore the Command Center, Shock Lab, and Strategy Arena.</p><Button variant="primary" busy={busy} onClick={() => createRun()}>Create simulation <MoveUpRight size={18} /></Button><span className="landing-demo-note">Simulated data · No real funds</span></section>
  </div>;
}
