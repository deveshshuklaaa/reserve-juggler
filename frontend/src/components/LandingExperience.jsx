import { ArrowDown, ArrowRight, CheckCircle2, Sparkles, TrendingUp, ShieldCheck, Banknote } from 'lucide-react';
import { useSimulation } from '../context/SimulationContext';
import { Button } from './ui';
import RJQuantumPrism from './RJQuantumPrism';

export default function LandingExperience() {
  const { createRun, busy } = useSimulation();

  return (
    <div className="landing-experience">
      {/* Apple Sub-Navigation Bar Ribbon */}
      <div className="apple-subnav-ribbon">
        <div className="subnav-inner">
          <span className="subnav-title">Reserve Juggler</span>
          <div className="subnav-links">
            <a href="#window-hero" className="active-link">Overview</a>
            <a href="#landing-story">Compare Paths</a>
            <Button variant="primary" busy={busy} onClick={() => createRun()} className="subnav-cta">
              Create simulation <ArrowRight size={14} />
            </Button>
          </div>
        </div>
      </div>

      {/* Hero Window: Compact, Crisp, Friendly */}
      <section className="apple-window landing-opening window-in-view" id="window-hero" aria-labelledby="landing-title">
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

        {/* Smooth scroll cue */}
        <div className="landing-scroll-cue">
          <a href="#landing-story" className="window-scroll-prompt">
            <span>Compare the 3 strategies below</span>
            <ArrowDown size={15} />
          </a>
        </div>
      </section>

      {/* Section 2: Compact, Friendly Comparison Story */}
      <section className="apple-window landing-story-compact window-in-view" id="landing-story" aria-label="Explore Reserve Juggler">
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
              <Banknote size={20} />
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
              <ShieldCheck size={20} />
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
              <TrendingUp size={20} />
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

        {/* Final Quick Launch */}
        <div className="story-compact-cta">
          <Button variant="primary" busy={busy} onClick={() => createRun()} className="apple-hero-btn">
            Create simulation <ArrowRight size={18} />
          </Button>
          <span className="simple-note">Simulated data · No real funds · USD · Instant 2-second setup</span>
        </div>
      </section>
    </div>
  );
}
