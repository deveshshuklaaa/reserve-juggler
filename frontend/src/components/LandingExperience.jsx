import { useEffect, useRef, useState } from 'react';
import { ArrowDown, ArrowRight, CheckCircle2, Sparkles, TrendingUp, ShieldCheck, Banknote, Shield, Zap } from 'lucide-react';
import { useSimulation } from '../context/SimulationContext';
import { Button } from './ui';
import RJQuantumPrism from './RJQuantumPrism';
import InteractiveSandbox from './InteractiveSandbox';
import PresentationScene from './PresentationScene';
import CapitalFlow from './CapitalFlow';
import './presentation.css';

const windows = [
  { id: 'window-hero', num: '01', label: 'Overview' },
  { id: 'interactive-lab', num: '02', label: 'Interactive Lab' },
  { id: 'landing-story', num: '03', label: 'Strategy Arena' },
  { id: 'window-finale', num: '04', label: 'Launch Simulation' },
];

export default function LandingExperience() {
  const { createRun, busy } = useSimulation();
  const root = useRef(null);
  const [activeWindow, setActiveWindow] = useState('window-hero');
  const [motionPaused, setMotionPaused] = useState(false);

  useEffect(() => {
    document.documentElement.classList.toggle('treasury-motion-paused', motionPaused);
    window.dispatchEvent(new Event('treasury-motion-change'));
    return () => {
      document.documentElement.classList.remove('treasury-motion-paused');
      window.dispatchEvent(new Event('treasury-motion-change'));
    };
  }, [motionPaused]);

  useEffect(() => {
    const element = root.current;
    const sections = [...element.querySelectorAll('.apple-fullscreen-window')];
    const preference = window.matchMedia('(prefers-reduced-motion: reduce)');
    document.documentElement.classList.add('treasury-presentation');
    let frame = 0;
    const clamp = (value) => Math.max(0, Math.min(1, value));
    const update = () => {
      frame = 0;
      const height = window.innerHeight;
      const header = window.innerWidth <= 760 ? 64 : 124;
      let selected = sections[0];
      const available = Math.max(1, height - header);
      sections.forEach((section, index) => {
        const rect = section.getBoundingClientRect();
        const surface = section.querySelector('.presentation-surface');
        const nextTop = sections[index + 1]?.getBoundingClientRect().top ?? Infinity;
        const entering = clamp((rect.top - header) / available);
        const leaving = clamp((height - nextTop) / available);
        const still = preference.matches || motionPaused;
        section.style.setProperty('--scene-height', `${surface.offsetHeight}px`);
        // Tall scenes scroll through their full contents before pinning at the bottom.
        section.style.setProperty('--scene-pin', `${header - Math.max(0, surface.offsetHeight - available)}px`);
        section.style.setProperty('--scene-index', String(index + 1));
        section.style.setProperty('--scene-shift', `${still ? 0 : entering * 48}px`);
        section.style.setProperty('--scene-scale', still ? '1' : String(1 - entering * .045 - leaving * .06));
        section.style.setProperty('--scene-radius', `${still ? 0 : Math.max(entering, leaving) * 32}px`);
        section.style.setProperty('--scene-blur', `${still ? 0 : entering * 16 + leaving * 12}px`);
        section.style.setProperty('--scene-opacity', String(still ? 1 : 1 - entering * .25 - leaving * .3));
        const visible = rect.top < height * .8 && rect.bottom > header;
        section.classList.toggle('window-in-view', visible);
        if (rect.top <= height * .5) selected = section;
      });
      setActiveWindow(selected.id);
      const rect = element.getBoundingClientRect();
      const progress = clamp(-rect.top / Math.max(1, element.offsetHeight - height));
      element.style.setProperty('--presentation-progress', progress.toFixed(4));
    };
    const schedule = () => { if (!frame) frame = window.requestAnimationFrame(update); };
    window.addEventListener('scroll', schedule, { passive: true });
    window.addEventListener('resize', schedule);
    preference.addEventListener('change', schedule);
    update();
    return () => {
      window.removeEventListener('scroll', schedule);
      window.removeEventListener('resize', schedule);
      preference.removeEventListener('change', schedule);
      window.cancelAnimationFrame(frame);
      document.documentElement.classList.remove('treasury-presentation');
    };
  }, [motionPaused]);

  const scrollToWindow = (id) => {
    const target = document.getElementById(id);
    if (target) {
      target.scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start' });
    }
  };

  return (
    <div className={`landing-experience ${motionPaused ? 'presentation-paused' : ''}`} ref={root}>
      <div className="presentation-progress" aria-hidden="true" />
      <button type="button" className="presentation-motion-toggle" aria-pressed={motionPaused} onClick={() => setMotionPaused((paused) => !paused)}>{motionPaused ? 'Resume motion' : 'Pause motion'}<span aria-hidden="true">{motionPaused ? '▷' : 'Ⅱ'}</span></button>
      {/* Floating Apple Window Navigator (Desktop) */}
      <nav className="apple-scroll-tracker" aria-label="Page section navigation">
        <div className="tracker-rail">
          {windows.map((win) => {
            const isActive = activeWindow === win.id;
            return (
              <button
                key={win.id}
                type="button"
                className={`tracker-dot ${isActive ? 'is-active' : ''}`}
                onClick={() => scrollToWindow(win.id)}
                aria-label={`Jump to ${win.label}`}
                title={win.label}
                aria-current={isActive ? 'step' : undefined}
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
          <span className="subnav-title">Reserve Juggler</span>
          <div className="subnav-links">
            <a href="#window-hero" className={activeWindow === 'window-hero' ? 'active-link' : ''}>Overview</a>
            <a href="#interactive-lab" className={activeWindow === 'interactive-lab' ? 'active-link' : ''}>Interactive Lab</a>
            <a href="#landing-story" className={activeWindow === 'landing-story' ? 'active-link' : ''}>Compare Paths</a>
            <Button variant="primary" busy={busy} onClick={() => createRun()} className="subnav-cta">
              Create simulation <ArrowRight size={14} />
            </Button>
          </div>
        </div>
      </div>

      {/* Window 1: Full-Screen Hero Experience */}
      <PresentationScene number="01" className="landing-opening window-in-view" id="window-hero" aria-labelledby="landing-title">
        <div className="landing-opening-copy">
          <div className="hero-pill-badge">
            <Sparkles size={14} className="text-blue" />
            <span>INTELLIGENT TREASURY AUTOPILOT</span>
          </div>

          <h1 id="landing-title">
            Treasury,<br />
            <span>in motion.</span>
          </h1>

          <p className="hero-tagline">
            See your liquidity. Explore every trade-off. Put your treasury strategy to the test.
          </p>

          <div className="landing-opening-actions">
            <Button variant="primary" busy={busy} onClick={() => createRun()} className="apple-hero-btn">
              Open Command Center <ArrowRight size={18} />
            </Button>
            <a href="#landing-story" className="landing-text-link">
              Explore the experience <ArrowDown size={17} />
            </a>
          </div>

          {/* Clean, Simple Metrics Bar */}
          <div className="hero-stat-row">
            <div className="hero-stat-item">
              <span className="stat-label">Demo capital</span>
              <strong className="stat-num">$20.0M</strong>
              <small className="stat-caption">Simulated starting balance</small>
            </div>
            <div className="hero-stat-divider" />
            <div className="hero-stat-item">
              <span className="stat-label">Capital tiers</span>
              <strong className="stat-num">04</strong>
              <small className="stat-caption">Cash. Repo. Bonds. Equities.</small>
            </div>
            <div className="hero-stat-divider" />
            <div className="hero-stat-item">
              <span className="stat-label">One workspace</span>
              <strong className="stat-num">03</strong>
              <small className="stat-caption">Monitor. Stress. Compare.</small>
            </div>
          </div>
        </div>

        {/* 3D Sapphire Glass Monolith with Kinetic Wave Streams */}
        <RJQuantumPrism />

        {/* Smooth scroll prompt to Window 2 */}
        <div className="landing-scroll-cue">
          <a href="#interactive-lab" className="window-scroll-prompt">
            <span>Scroll to explore the mock simulator</span>
            <ArrowDown size={15} />
          </a>
        </div>
      </PresentationScene>

      {/* Window 2: Full-Screen Hands-On Simulator Playground */}
      <PresentationScene number="02" className="window-sandbox-section" id="interactive-lab" aria-label="Interactive Sandbox Simulator">
        <InteractiveSandbox />

        {/* Smooth scroll prompt to Window 3 */}
        <div className="landing-scroll-cue">
          <a href="#landing-story" className="window-scroll-prompt">
            <span>Scroll to compare strategy returns</span>
            <ArrowDown size={15} />
          </a>
        </div>
      </PresentationScene>

      {/* Window 3: Full-Screen Strategy Comparison Arena */}
      <PresentationScene number="03" className="landing-story-compact" id="landing-story" aria-label="Explore Reserve Juggler">
        <div className="story-compact-header">
          <span className="apple-kicker">ONE SCENARIO. THREE STRATEGIES.</span>
          <h2>
            Compare the paths.<br />
            <span>Let the results decide.</span>
          </h2>
          <p>
            Compare liquidity, estimated income, and funding costs on the same simulated cash flows.
          </p>
        </div>

        {/* Clean 3-Card Comparison Grid */}
        <div className="simple-comparison-grid">
          <div className="simple-card">
            <div className="simple-card-badge">Baseline 01</div>
            <div className="simple-card-icon icon-muted">
              <Banknote size={22} />
            </div>
            <h3>Static reserve</h3>
            <div className="simple-card-num">Fixed.</div>
            <p>A consistent cash buffer. A clear starting point for comparison.</p>
            <ul className="simple-card-bullets">
              <li><CheckCircle2 size={15} className="text-muted" /> Fixed reserve policy</li>
              <li><CheckCircle2 size={15} className="text-muted" /> Shared scenario and seed</li>
              <li><CheckCircle2 size={15} className="text-muted" /> Inspect the cost of idle cash</li>
            </ul>
          </div>

          <div className="simple-card">
            <div className="simple-card-badge">Baseline 02</div>
            <div className="simple-card-icon icon-amber">
              <ShieldCheck size={22} />
            </div>
            <h3>Reactive reserve</h3>
            <div className="simple-card-num">Respond.</div>
            <p>Adjust to observed cash movements as liquidity needs change.</p>
            <ul className="simple-card-bullets">
              <li><CheckCircle2 size={15} className="text-muted" /> Observed flow signals</li>
              <li><CheckCircle2 size={15} className="text-muted" /> Redemption costs included</li>
              <li><CheckCircle2 size={15} className="text-muted" /> Track reserve breaches</li>
            </ul>
          </div>

          <div className="simple-card is-highlight">
            <div className="simple-card-badge highlight-badge">Forecast-led strategy</div>
            <div className="simple-card-icon icon-blue">
              <TrendingUp size={22} />
            </div>
            <h3>Reserve Juggler</h3>
            <div className="simple-card-num highlight-num">Anticipate.</div>
            <p>Use forecasts and liquidity constraints to evaluate the next allocation.</p>
            <ul className="simple-card-bullets">
              <li><CheckCircle2 size={15} className="text-green" /> Explainable recommendations</li>
              <li><CheckCircle2 size={15} className="text-green" /> Liquidity and risk constraints</li>
              <li><CheckCircle2 size={15} className="text-green" /> No preset winning strategy</li>
            </ul>
          </div>
        </div>

        {/* Smooth scroll prompt to Window 4 */}
        <div className="landing-scroll-cue">
          <a href="#window-finale" className="window-scroll-prompt">
            <span>Scroll to start your simulation</span>
            <ArrowDown size={15} />
          </a>
        </div>
      </PresentationScene>

      {/* Window 4: Full-Screen Finale & One-Click Launch */}
      <PresentationScene number="04" className="landing-finale-screen" id="window-finale" aria-label="Launch Reserve Juggler Simulation">
        <div className="finale-content-box">
          <span className="apple-kicker">READY WHEN YOU ARE</span>
          <h2>
            Experience the future<br />
            <span>of cash management.</span>
          </h2>
          <p>
            Start with $20M in simulated cash. Explore the Command Center, Shock Lab, and Strategy Arena.
          </p>
          <CapitalFlow />

          <div className="finale-action-group">
            <Button variant="primary" busy={busy} onClick={() => createRun()} className="apple-hero-btn">
              Create simulation <ArrowRight size={18} />
            </Button>
          </div>

          <div className="finale-perks">
            <span><CheckCircle2 size={14} className="text-green" /> 100% Free Demo</span>
            <span><CheckCircle2 size={14} className="text-green" /> Zero Real Funds</span>
            <span><CheckCircle2 size={14} className="text-green" /> Reproducible Scenarios</span>
          </div>
        </div>
      </PresentationScene>
    </div>
  );
}
