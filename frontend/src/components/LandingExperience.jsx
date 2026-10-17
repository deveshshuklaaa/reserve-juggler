import { useEffect, useRef, useState } from 'react';
import { ArrowDown, ArrowRight, MoveUpRight, Sparkles, Shield, Cpu, Activity, Zap } from 'lucide-react';
import { useSimulation } from '../context/SimulationContext';
import { Button } from './ui';
import RJQuantumPrism from './RJQuantumPrism';
import AppleSiliconChip from './AppleSiliconChip';
import InteractiveSandbox from './InteractiveSandbox';
import AppleBentoGrid from './AppleBentoGrid';

const story = [
  {
    number: '01',
    label: 'See ahead',
    title: (
      <>
        Know where cash<br />
        <em>is heading.</em>
      </>
    ),
    note: 'A clearer view of incoming flows, reserve needs, and available capital before shocks materialize.',
  },
  {
    number: '02',
    label: 'Test the edge',
    title: (
      <>
        Pressure-test<br />
        <em>every move.</em>
      </>
    ),
    note: 'Explore liquidity shocks before they reach the balance sheet. Stress testing engineered for certainty.',
  },
  {
    number: '03',
    label: 'Choose well',
    title: (
      <>
        Compare the paths.<br />
        <em>Keep the proof.</em>
      </>
    ),
    note: 'Put strategies through the same conditions and inspect the deterministic result with full cryptographic audit.',
  },
];

function FlowScene() {
  return (
    <div className="landing-scene landing-flow-scene" aria-hidden="true">
      <div className="scene-header">
        <div className="scene-header-brand">
          <Activity size={18} className="text-blue" />
          <span>Liquidity outlook</span>
        </div>
        <span className="scene-live">
          <i /> SIMULATED · 24H HORIZON
        </span>
      </div>
      <div className="scene-stat">
        <small>Available capital</small>
        <strong>$20.00M</strong>
        <span>Illustrative starting balance · Zero idle cash</span>
      </div>
      <svg className="scene-flow-chart" viewBox="0 0 700 260" preserveAspectRatio="none">
        <defs>
          <linearGradient id="flow-fill" x1="0" y1="0" x2="0" y2="1">
            <stop stopColor="#2997ff" stopOpacity=".38" />
            <stop offset="1" stopColor="#2997ff" stopOpacity="0" />
          </linearGradient>
          <linearGradient id="flow-stroke" x1="0" y1="0" x2="1" y2="0">
            <stop stopColor="#2997ff" />
            <stop offset="50%" stopColor="#bf5af2" />
            <stop offset="100%" stopColor="#30d158" />
          </linearGradient>
        </defs>
        <path className="scene-grid-line" d="M0 42H700M0 104H700M0 166H700M0 228H700" />
        <path
          className="scene-flow-fill"
          d="M0 181 C75 170 93 194 150 153 S228 144 284 127 S350 150 416 113 S502 121 558 81 S633 96 700 42 L700 260H0Z"
        />
        <path
          className="scene-flow-path"
          d="M0 181 C75 170 93 194 150 153 S228 144 284 127 S350 150 416 113 S502 121 558 81 S633 96 700 42"
          stroke="url(#flow-stroke)"
        />
        <circle className="scene-flow-dot" cx="558" cy="81" r="9" />
        <circle className="scene-flow-pulse" cx="558" cy="81" r="18" />
      </svg>
      <div className="scene-axis">
        <span>Now (Confirmed)</span>
        <span>Confidence Interval: 99.4%</span>
        <span>Next horizon (+24h)</span>
      </div>
    </div>
  );
}

function ShockScene() {
  return (
    <div className="landing-scene landing-shock-scene" aria-hidden="true">
      <div className="scene-header">
        <div className="scene-header-brand">
          <Shield size={18} className="text-violet" />
          <span>Liquidity Shock Lab</span>
        </div>
        <span className="scene-live">
          <i /> MONTE CARLO STRESS
        </span>
      </div>
      <div className="shock-visual">
        <div className="shock-ripple ripple-a" />
        <div className="shock-ripple ripple-b" />
        <div className="shock-ripple ripple-c" />
        <div className="shock-ripple ripple-d" />
        <div className="shock-core">
          <span className="shock-kicker">AUTONOMOUS SHOCK DAMPENER</span>
          <strong>
            Resilient<br />
            by design.
          </strong>
        </div>
      </div>
      <div className="shock-tags">
        <span>Withdrawal surge 500%</span>
        <span>Counterparty freeze</span>
        <span>Sub-second reserve sweep</span>
      </div>
    </div>
  );
}

function ArenaScene() {
  return (
    <div className="landing-scene landing-arena-scene" aria-hidden="true">
      <div className="scene-header">
        <div className="scene-header-brand">
          <Zap size={18} className="text-amber" />
          <span>Treasury Strategy Arena</span>
        </div>
        <span className="scene-live">
          <i /> MULTI-STRATEGY BACKTEST
        </span>
      </div>
      <div className="arena-lines">
        <div className="arena-line">
          <span>01</span>
          <strong>All cash</strong>
          <i className="arena-bar bar-one" />
          <span className="arena-stat-note">0.0% Yield · 100% Drag</span>
        </div>
        <div className="arena-line">
          <span>02</span>
          <strong>Static yield</strong>
          <i className="arena-bar bar-two" />
          <span className="arena-stat-note">2.4% Yield · Early Penalty Risk</span>
        </div>
        <div className="arena-line is-champion">
          <span>03</span>
          <strong>Reserve Juggler Pro</strong>
          <i className="arena-bar bar-three" />
          <span className="arena-stat-note highlight-stat">5.2% Yield · 0% Default Risk</span>
        </div>
      </div>
      <div className="arena-note">
        <span>Same conditions. Identical market seed.</span>
        <strong>Deterministic Outcome: +$482k Net Benefit</strong>
      </div>
    </div>
  );
}

const scenes = [FlowScene, ShockScene, ArenaScene];

const windows = [
  { id: 'window-hero', num: '01', label: 'Overview' },
  { id: 'silicon-specs', num: '02', label: 'RJ-1 Silicon' },
  { id: 'interactive-lab', num: '03', label: 'Interactive Lab' },
  { id: 'landing-story', num: '04', label: 'Strategy Arena' },
  { id: 'window-bento', num: '05', label: 'Architecture' },
];

export default function LandingExperience() {
  const { createRun, busy } = useSimulation();
  const root = useRef(null);
  const [active, setActive] = useState(0);
  const [activeWindow, setActiveWindow] = useState('window-hero');

  useEffect(() => {
    const element = root.current;
    if (!element || typeof window === 'undefined' || !('IntersectionObserver' in window)) return undefined;

    // Window scroll transition observer
    const windowObserver = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          const id = entry.target.id;
          if (entry.isIntersecting) {
            entry.target.classList.add('window-in-view');
            entry.target.classList.remove('window-scrolled-past');
            setActiveWindow(id);
          } else if (entry.boundingClientRect.top < 0) {
            entry.target.classList.add('window-scrolled-past');
            entry.target.classList.remove('window-in-view');
          } else {
            entry.target.classList.remove('window-in-view', 'window-scrolled-past');
          }
        });
      },
      { threshold: 0.22 }
    );

    element.querySelectorAll('.apple-window').forEach((w) => windowObserver.observe(w));

    // Story step observer for the 3-scene arena
    const storyObserver = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            setActive(Number(entry.target.dataset.scene));
            entry.target.classList.add('landing-visible');
          }
        });
      },
      { rootMargin: '-32% 0px -32% 0px' }
    );

    element.querySelectorAll('[data-scene]').forEach((scene) => storyObserver.observe(scene));

    return () => {
      windowObserver.disconnect();
      storyObserver.disconnect();
    };
  }, []);

  const scrollToWindow = (id) => {
    const target = document.getElementById(id);
    if (target) {
      target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  };

  return (
    <div className="landing-experience" ref={root}>
      {/* Floating Vertical Apple Window Navigator (Desktop) */}
      <nav className="apple-scroll-tracker" aria-label="Page section navigation">
        <div className="tracker-rail">
          {windows.map((win) => {
            const isActive = activeWindow === win.id;
            return (
              <button
                key={win.id}
                className={`tracker-dot ${isActive ? 'is-active' : ''}`}
                onClick={() => scrollToWindow(win.id)}
                aria-label={`Jump to ${win.label}`}
                title={win.label}
              >
                <span className="tracker-dot-pip" />
                <span className="tracker-tooltip">
                  <small>{win.num}</small> {win.label}
                </span>
              </button>
            );
          })}
        </div>
      </nav>

      {/* Apple Sub-Navigation Bar Ribbon */}
      <div className="apple-subnav-ribbon">
        <div className="subnav-inner">
          <span className="subnav-title">Reserve Juggler Pro</span>
          <div className="subnav-links">
            <a href="#window-hero" className={activeWindow === 'window-hero' ? 'active-link' : ''}>Overview</a>
            <a href="#silicon-specs" className={activeWindow === 'silicon-specs' ? 'active-link' : ''}>RJ-1 Silicon</a>
            <a href="#interactive-lab" className={activeWindow === 'interactive-lab' ? 'active-link' : ''}>Interactive Lab</a>
            <a href="#landing-story" className={activeWindow === 'landing-story' ? 'active-link' : ''}>Strategy Arena</a>
            <Button variant="primary" busy={busy} onClick={() => createRun()} className="subnav-cta">
              Create simulation <ArrowRight size={14} />
            </Button>
          </div>
        </div>
      </div>

      {/* Window 0: Hero Section ("The RJ Part") */}
      <section className="apple-window landing-opening window-in-view" id="window-hero" aria-labelledby="landing-title">
        <div className="landing-opening-copy">
          <div className="hero-pill-badge">
            <Sparkles size={14} className="text-blue" />
            <span>INTRODUCING THE AUTONOMOUS TREASURY ENGINE</span>
          </div>

          <h1 id="landing-title">
            Treasury,<br />
            <span>in motion.</span>
          </h1>

          <p className="hero-tagline">
            Clarity for every cash decision. Pure mathematical precision for the institutional balance sheet.
          </p>

          <div className="landing-opening-actions">
            <Button variant="primary" busy={busy} onClick={() => createRun()} className="apple-hero-btn">
              Open Command Center <ArrowRight size={18} />
            </Button>
            <a href="#landing-story" className="landing-text-link">
              Explore the experience <ArrowDown size={17} />
            </a>
          </div>

          {/* Quick Metrics Bar */}
          <div className="hero-stat-row">
            <div className="hero-stat-item">
              <span className="stat-label">Deployable Capital</span>
              <strong className="stat-num">$20.0M</strong>
              <small className="stat-caption">Instant Availability</small>
            </div>
            <div className="hero-stat-divider" />
            <div className="hero-stat-item">
              <span className="stat-label">Annual Yield</span>
              <strong className="stat-num">5.20%</strong>
              <small className="stat-caption">Automated Sweeps</small>
            </div>
            <div className="hero-stat-divider" />
            <div className="hero-stat-item">
              <span className="stat-label">Model Confidence</span>
              <strong className="stat-num">99.4%</strong>
              <small className="stat-caption">Quantile Reserve Risk</small>
            </div>
          </div>
        </div>

        {/* Brand New 3D Sapphire Glass Monolith Core with Kinetic Wave Streams (Zero AI Orbit Rings) */}
        <RJQuantumPrism />

        {/* Transition cue to Window 1 */}
        <div className="landing-scroll-cue">
          <a href="#silicon-specs" className="window-scroll-prompt">
            <span>Scroll to explore RJ-1 Silicon</span>
            <ArrowDown size={15} />
          </a>
        </div>
      </section>

      {/* Window 1: Apple Silicon Hardware Showcase */}
      <AppleSiliconChip />

      {/* Window 2: Hands-On Interactive Sandbox Playground */}
      <InteractiveSandbox />

      {/* Window 3: Apple Sticky Scroll Narrative */}
      <section className="apple-window landing-narrative" id="landing-story" aria-label="Explore Reserve Juggler">
        <div className="landing-narrative-track">
          <div className="landing-narrative-inner">
            <div className="landing-stage-top">
              <span>ONE CONNECTED VIEW</span>
              <span className="stage-step-counter">0{active + 1} / 03</span>
            </div>

            <div className="landing-stage-visual">
              {scenes.map((Scene, index) => (
                <div key={index} className={`landing-visual-layer ${active === index ? 'is-active' : ''}`}>
                  <Scene />
                </div>
              ))}
            </div>

            <div className="landing-stage-dots" aria-hidden="true">
              {story.map((item, index) => (
                <i key={item.number} className={active === index ? 'is-active' : ''} />
              ))}
            </div>
          </div>
        </div>

        <div className="landing-narrative-copy">
          {story.map((item, index) => (
            <div
              key={item.number}
              className={`landing-story-step ${active === index ? 'is-active' : ''}`}
              data-scene={index}
            >
              <span className="landing-step-label">
                {item.number} / {item.label}
              </span>
              <h2>{item.title}</h2>
              <p>{item.note}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Window 4: Apple Bento Grid Section */}
      <AppleBentoGrid />

      {/* Window 5: Apple Keynote Finale CTA */}
      <section className="apple-window landing-finale" id="window-finale">
        <span className="landing-eyebrow">READY WHEN YOU ARE</span>
        <h2>
          See the whole picture.<br />
          <span>Then make your move.</span>
        </h2>
        <p>
          Start a deterministic simulation and explore the Command Center, Shock Lab, and Strategy Arena with zero risk to real capital.
        </p>
        <div className="finale-action-group">
          <Button variant="primary" busy={busy} onClick={() => createRun()} className="apple-hero-btn">
            Create simulation <MoveUpRight size={19} />
          </Button>
        </div>
        <span className="landing-demo-note">Simulated data · No real funds · USD · UTC</span>
      </section>
    </div>
  );
}
