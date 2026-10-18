export const SCENARIOS = [
  { id: 'NORMAL', name: 'Normal operations', detail: 'Restore the normal flow regime.', icon: 'activity' },
  { id: 'HIGH_WITHDRAWAL', name: 'Withdrawal spike', detail: 'Increase customer withdrawal demand.', icon: 'outflow' },
  { id: 'LOW_DEPOSIT', name: 'Deposit drop', detail: 'Reduce incoming customer deposits.', icon: 'deposit' },
  { id: 'SETTLEMENT_DELAY', name: 'Settlement delay', detail: 'Defer incoming settlement receipts.', icon: 'clock' },
  { id: 'LIQUIDITY_SHOCK', name: 'Liquidity shock', detail: 'Inject a concentrated unexpected outflow.', icon: 'shock' },
];
export const STRATEGIES = [
  { id: 'STATIC', name: 'Static reserve', color: '#99a4b4', description: 'Maintains a fixed $14M cash reserve.' },
  { id: 'REACTIVE', name: 'Reactive reserve', color: '#4c9185', description: 'Responds to the most recent net outflow.' },
  { id: 'RESERVE_JUGGLER', name: 'Reserve Juggler', color: '#0071e3', description: 'Uses a mock forecast buffer and vault constraints.' },
];
export const DEFAULT_POLICY = Object.freeze({ risk_percentile: 95, operational_buffer_cents: 50000000,
  min_sweep_cents: 50000000, vault_rate_bps: 500, early_redemption_penalty_bps: 50,
  lock_steps: 96, allow_early_redemption: false });
export const DEFAULT_RUN = Object.freeze({ seed: 2026, duration_steps: 192, step_minutes: 15,
  start_time: '2026-10-17T08:00:00.000Z', initial_checking_cents: 2000000000, initial_vault_cents: 600000000 });
