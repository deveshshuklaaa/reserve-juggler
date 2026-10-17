import { useEffect, useRef, useState } from 'react';
import { ArrowDown, ArrowRight, CheckCircle2, Sparkles, TrendingUp, ShieldCheck, Banknote, Shield, Zap } from 'lucide-react';
import { useSimulation } from '../context/SimulationContext';
import { Button } from './ui';
import RJQuantumPrism from './RJQuantumPrism';
import InteractiveSandbox from './InteractiveSandbox';

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

  useEffect(() => {
    if (typeof window === 'undefined' || !('IntersectionObserver' in window)) return undefined;

    const observer = new IntersectionObserver(
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
      { threshold: 0.25 }
    );

    document.querySelectorAll('.apple-fullscreen-window').forEach((w) => observer.observe(w));

    return () => observer.disconnect();
  }, []);

  const scrollToWindow = (id) => {
    const target = document.getElementById(id);
    if (target) {
      target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  };

  return (
    <div className="landing-experience" ref={root}>
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
      <section className="apple-fullscreen-window landing-opening window-in-view" id="window-hero" aria-labelledby="landing-title">
        <div className="landing-opening-copy">
          <div className="hero-pill-badge">
            <Sparkles size={14} className="text-blue" />
            <span>SIMPLE AUTOMATED CASH AUTOPILOT</span>
          </div>

          <h1 id="landing-title">
            Treasury,<br />
            <span>in motion.</span>
          </h1>

          <p className="hero-tagline">
            Keep enough cash for daily needs, protect your emergency reserves, and automatically earn 5.2% on the rest. No spreadsheets. No idle cash.
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
              <span className="stat-label">Available Cash</span>
              <strong className="stat-num">$20.0M</strong>
              <small className="stat-caption">Ready to spend immediately</small>
            </div>
            <div className="hero-stat-divider" />
            <div className="hero-stat-item">
              <span className="stat-label">Annual Yield</span>
              <strong className="stat-num">5.20%</strong>
              <small className="stat-caption">Earned automatically</small>
            </div>
            <div className="hero-stat-divider" />
            <div className="hero-stat-item">
              <span className="stat-label">Safety Buffer</span>
              <strong className="stat-num">99.4%</strong>
              <small className="stat-caption">Protected from surprises</small>
            </div>
          </div>
        </div>

        {/* 3D Sapphire Glass Monolith with Kinetic Wave Streams */}
        <RJQuantumPrism />

        {/* Smooth scroll prompt to Window 2 */}
        <div className="landing-scroll-cue">
          <a href="#interactive-lab" className="window-scroll-prompt">
            <span>Scroll to test the live simulator</span>
            <ArrowDown size={15} />
          </a>
        </div>
      </section>

      {/* Window 2: Full-Screen Hands-On Simulator Playground */}
      <section className="apple-fullscreen-window window-sandbox-section" id="interactive-lab" aria-label="Interactive Sandbox Simulator">
        <InteractiveSandbox />

        {/* Smooth scroll prompt to Window 3 */}
        <div className="landing-scroll-cue">
          <a href="#landing-story" className="window-scroll-prompt">
            <span>Scroll to compare strategy returns</span>
            <ArrowDown size={15} />
          </a>
        </div>
      </section>

      {/* Window 3: Full-Screen Strategy Comparison Arena */}
      <section className="apple-fullscreen-window landing-story-compact" id="landing-story" aria-label="Explore Reserve Juggler">
        <div className="story-compact-header">
          <span className="apple-kicker">THREE SIMPLE CHOICES</span>
          <h2>
            Compare the paths.<br />
            <span>See how automated treasury puts idle cash to work.</span>
          </h2>
          <p>
            Traditional banks leave cash sitting idle or lock it up with early break penalties. Reserve Juggler balances both automatically.
          </p>
        </div>

        {/* Clean 3-Card Comparison Grid */}
        <div className="simple-comparison-grid">
          <div className="simple-card">
            <div className="simple-card-badge">Traditional Banking</div>
            <div className="simple-card-icon icon-muted">
              <Banknote size={22} />
            </div>
            <h3>1. All Cash</h3>
            <div className="simple-card-num">0.0% APY</div>
            <p>Your money sits in a basic checking account. 100% available, but loses value to inflation every single month.</p>
            <ul className="simple-card-bullets">
              <li><CheckCircle2 size={15} className="text-muted" /> Instant withdrawals</li>
              <li><span className="bullet-cross">✕</span> $0 annual interest earned</li>
              <li><span className="bullet-cross">✕</span> High opportunity cost</li>
            </ul>
          </div>

          <div className="simple-card">
            <div className="simple-card-badge">Fixed Deposit</div>
            <div className="simple-card-icon icon-amber">
              <ShieldCheck size={22} />
            </div>
            <h3>2. Locked Vault</h3>
            <div className="simple-card-num">2.4% APY</div>
            <p>You lock money into fixed terms. You earn a modest return, but get hit with penalties if an unexpected bill arrives.</p>
            <ul className="simple-card-bullets">
              <li><CheckCircle2 size={15} className="text-muted" /> Modest interest income</li>
              <li><span className="bullet-cross">✕</span> Early withdrawal penalties</li>
              <li><span className="bullet-cross">✕</span> Inflexible during cash crunches</li>
            </ul>
          </div>

          <div className="simple-card is-highlight">
            <div className="simple-card-badge highlight-badge">Recommended Autopilot</div>
            <div className="simple-card-icon icon-blue">
              <TrendingUp size={22} />
            </div>
            <h3>3. Reserve Juggler</h3>
            <div className="simple-card-num highlight-num">5.20% APY</div>
            <p>The best of both worlds. Automatically sweeps surplus into yield, and instantly protects checking when withdrawals surge.</p>
            <ul className="simple-card-bullets">
              <li><CheckCircle2 size={15} className="text-green" /> <strong>+$482,000</strong> net extra gain</li>
              <li><CheckCircle2 size={15} className="text-green" /> Zero early redemption fees</li>
              <li><CheckCircle2 size={15} className="text-green" /> 100% automated cash defense</li>
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
      </section>

      {/* Window 4: Full-Screen Finale & One-Click Launch */}
      <section className="apple-fullscreen-window landing-finale-screen" id="window-finale" aria-label="Launch Reserve Juggler Simulation">
        <div className="finale-content-box">
          <span className="apple-kicker">READY WHEN YOU ARE</span>
          <h2>
            Experience the future<br />
            <span>of cash management.</span>
          </h2>
          <p>
            Launch an interactive simulation with $20M in demo funds. Test liquidity shocks, watch autonomous sweeps, and inspect the live mathematical proof.
          </p>

          <div className="finale-action-group">
            <Button variant="primary" busy={busy} onClick={() => createRun()} className="apple-hero-btn">
              Create simulation <ArrowRight size={18} />
            </Button>
          </div>

          <div className="finale-perks">
            <span><CheckCircle2 size={14} className="text-green" /> 100% Free Demo</span>
            <span><CheckCircle2 size={14} className="text-green" /> Zero Real Funds</span>
            <span><CheckCircle2 size={14} className="text-green" /> Instant 2-Second Setup</span>
          </div>
        </div>
      </section>
    </div>
  );
}
