import { Component } from 'react';
import { BrowserRouter, Link, Route, Routes } from 'react-router-dom';
import { SimulationProvider } from './context/SimulationContext';
import { Layout } from './components/Layout';
import TreasuryDashboard from './pages/TreasuryDashboard';
import LiquidityShockLab from './pages/LiquidityShockLab';
import StrategyArena from './pages/StrategyArena';
import LandingExperience from './components/LandingExperience';

class ErrorBoundary extends Component {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() {
    if (this.state.failed) return <div className="fatal-error"><h1>This workspace could not be displayed.</h1><p>Reload to reconnect to a confirmed simulation state.</p><button className="button button-primary" onClick={() => window.location.reload()}>Reload workspace</button></div>;
    return this.props.children;
  }
}
export function AppRoutes() {
  return <Routes><Route element={<Layout />}><Route index element={<div className="page-content landing-page"><LandingExperience /></div>} /><Route path="command-center" element={<TreasuryDashboard />} /><Route path="shock-lab" element={<LiquidityShockLab />} /><Route path="strategy-arena" element={<StrategyArena />} /><Route path="*" element={<div className="empty-state"><h1>Page not found</h1><Link to="/command-center">Return to Command Center</Link></div>} /></Route></Routes>;
}
export default function App() {
  return <ErrorBoundary><BrowserRouter><SimulationProvider><AppRoutes /></SimulationProvider></BrowserRouter></ErrorBoundary>;
}
