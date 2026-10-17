import { cents } from '../utils/format';
import { DEFAULT_POLICY, DEFAULT_RUN, SCENARIOS, STRATEGIES } from './constants';

// An isolated frontend development ledger, never an authority in real API mode.
// Mock forecasts use only observed history, never future generated transactions.
const clone = (value) => structuredClone(value);
export class MockError extends Error {
  constructor(message, status = 422) { super(message); this.status = status; }
}
const check = (condition, message) => { if (!condition) throw new MockError(message); };
function integer(value, min, max, label) {
  check(Number.isSafeInteger(value) && value >= min && value <= max, `${label} must be an integer from ${min} to ${max}.`);
}
function randomAt(seed, step) {
  let state = (seed ^ Math.imul(step + 1, 2654435761)) >>> 0 || 1;
  return () => { state ^= state << 13; state ^= state >>> 17; state ^= state << 5; return (state >>> 0) / 4294967296; };
}
const bpsOf = (value, bps) => Number(BigInt(value) * BigInt(bps) / 10000n);

export function validatePolicy(input) {
  const policy = { ...DEFAULT_POLICY, ...input };
  check([90, 95, 99].includes(policy.risk_percentile), 'Select a supported risk percentile.');
  for (const key of ['operational_buffer_cents', 'min_sweep_cents']) integer(policy[key], 0, 5000000000, key);
  integer(policy.vault_rate_bps, 0, 2000, 'Vault rate');
  integer(policy.early_redemption_penalty_bps, 0, 2000, 'Redemption penalty');
  integer(policy.lock_steps, 1, 384, 'Lock duration');
  check(typeof policy.allow_early_redemption === 'boolean', 'Early redemption must be true or false.');
  return policy;
}

export function createEngine(input = {}, id = 'mock-run-1', strategy = 'RESERVE_JUGGLER') {
  const config = { ...DEFAULT_RUN, ...input };
  integer(config.seed, 0, 4294967295, 'Seed');
  integer(config.duration_steps, 1, 2880, 'Duration');
  check(config.step_minutes === 15, 'The mock supports 15-minute steps.');
  check(typeof config.start_time === 'string' && config.start_time.endsWith('Z') && Number.isFinite(Date.parse(config.start_time)), 'Use an ISO UTC start time.');
  integer(config.initial_checking_cents, 0, 100000000000, 'Checking');
  integer(config.initial_vault_cents, 0, 100000000000, 'Vault');
  check(STRATEGIES.some((item) => item.id === strategy), 'Unknown strategy.');
  const policy = validatePolicy(input.policy);
  const run = { id, config, strategy, policy, step: 0, checking: config.initial_checking_cents,
    positions: [], transactions: [], decisions: [], history: [], events: [], delayed: [],
    borrowed: 0, yield: 0, penalties: 0, borrowing_costs: 0, failed_payouts: 0,
    failed_amount: 0, reserve_breaches: 0, sweeps: 0, emergency_events: 0, alerts: [],
    inflow_total: 0, outflow_total: 0, decision: null };
  if (config.initial_vault_cents) addPosition(run, config.initial_vault_cents, 0);
  run.history.push(historyPoint(run, 0, 0));
  return run;
}

function timestamp(run, step = run.step) {
  return new Date(Date.parse(run.config.start_time) + step * 15 * 60000).toISOString();
}
function addPosition(run, principal, createdStep = run.step) {
  run.positions.push({ id: `VP-${run.positions.length + 1}`, principal_cents: principal,
    rate_bps: run.policy.vault_rate_bps, created_step: createdStep,
    maturity_step: createdStep + run.policy.lock_steps,
    penalty_bps: run.policy.early_redemption_penalty_bps,
    early_redemption_allowed: run.policy.allow_early_redemption,
    accrued_cents: 0, remainder: 0n });
}
function vaultTotals(run) {
  let locked = 0; let redeemable = 0; let accrued = 0;
  for (const position of run.positions) {
    if (position.maturity_step > run.step) locked += position.principal_cents;
    else redeemable += position.principal_cents;
    accrued += position.accrued_cents;
  }
  return { locked, redeemable, accrued };
}
function forecastBasis(run) {
  const observed = run.history.slice(-8).filter((item) => item.step > 0);
  const average = (field, fallback) => observed.length ? Math.round(observed.reduce((sum, item) => sum + item[field], 0) / observed.length) : fallback;
  const inflow = average('inflow_cents', 250000000);
  const outflow = average('requested_outflow_cents', 245000000);
  const drain = Math.max(0, outflow - inflow);
  const peak = Math.max(650000000, drain * 8);
  const uncertainty = Math.round(Math.max(80000000, outflow * 0.6) * ({ 90: 0.8, 95: 1, 99: 1.5 }[run.policy.risk_percentile]));
  return { inflow, outflow, peak, uncertainty, reserve: peak + uncertainty + run.policy.operational_buffer_cents };
}
function reserveFor(run) {
  if (run.strategy === 'STATIC') return 1400000000;
  if (run.strategy === 'REACTIVE') {
    const last = run.history.at(-1);
    return Math.max(450000000, Math.max(0, (last?.outflow_cents ?? 0) - (last?.inflow_cents ?? 0)) * 4 + run.policy.operational_buffer_cents);
  }
  return forecastBasis(run).reserve;
}
function historyPoint(run, inflow, outflow, requestedOutflow = outflow) {
  const totals = vaultTotals(run);
  return { step: run.step, timestamp: timestamp(run), checking_cents: run.checking,
    required_reserve_cents: reserveFor(run), vault_cents: totals.locked + totals.redeemable,
    inflow_cents: inflow, outflow_cents: outflow, requested_outflow_cents: requestedOutflow, net_flow_cents: inflow - outflow,
    realized_interest_cents: run.yield, borrowing_cents: run.borrowed,
    net_benefit_cents: run.yield - run.penalties - run.borrowing_costs };
}

export function scheduleScenario(run, input) {
  check(SCENARIOS.some((item) => item.id === input.scenario), 'Unknown scenario enum.');
  const parameters = { duration_steps: 8, multiplier_bps: 30000, reduction_bps: 6000,
    delay_steps: 8, fraction_bps: 7500, shock_cents: 800000000, ...input.parameters };
  integer(parameters.duration_steps, 1, 96, 'Scenario duration');
  integer(parameters.multiplier_bps, 10000, 50000, 'Withdrawal multiplier');
  integer(parameters.reduction_bps, 0, 10000, 'Deposit reduction');
  integer(parameters.delay_steps, 1, 96, 'Settlement delay');
  integer(parameters.fraction_bps, 0, 10000, 'Settlement fraction');
  integer(parameters.shock_cents, 1, 10000000000, 'Shock amount');
  const effective_step = input.effective_step ?? run.step + 1;
  integer(effective_step, run.step + 1, run.config.duration_steps, 'Effective step');
  const event = { id: `EV-${run.events.length + 1}`, scenario: input.scenario, parameters,
    effective_step, status: 'SCHEDULED', submitted_step: run.step };
  run.events.push(event);
  return clone(event);
}

export function setPolicy(run, input) {
  const allowed = Object.keys(DEFAULT_POLICY);
  check(Object.keys(input).every((key) => allowed.includes(key)), 'Unknown policy parameter.');
  run.policy = validatePolicy({ ...run.policy, ...input });
  // Existing position terms are immutable. New decisions use the new policy.
  return clone(run.policy);
}

export function advanceEngine(run, expectedStep = run.step, includeSnapshot = true) {
  if (expectedStep !== run.step) throw new MockError('Simulation step changed. State has been refreshed.', 409);
  check(run.step < run.config.duration_steps, 'The simulation has completed.');
  run.step += 1; run.alerts = [];
  const random = randomAt(run.config.seed, run.step);
  let deposit = Math.round(180000000 + random() * 110000000);
  let settlement = Math.round(25000000 + random() * 40000000);
  let withdrawal = Math.round(200000000 + random() * 100000000);
  let shock = 0;
  for (const event of run.events) event.status = run.step < event.effective_step ? 'SCHEDULED' : run.step < event.effective_step + event.parameters.duration_steps ? 'ACTIVE' : 'COMPLETED';
  // The newest effective scenario supersedes the previous future flow regime.
  const event = run.events.filter((item) => item.effective_step <= run.step).at(-1);
  for (const previous of run.events) if (event && previous !== event && previous.effective_step <= event.effective_step && previous.status === 'ACTIVE') previous.status = 'SUPERSEDED';
  if (event?.status === 'ACTIVE') {
    const p = event.parameters;
    if (event.scenario === 'HIGH_WITHDRAWAL') withdrawal = bpsOf(withdrawal, p.multiplier_bps);
    if (event.scenario === 'LOW_DEPOSIT') deposit -= bpsOf(deposit, p.reduction_bps);
    if (event.scenario === 'LIQUIDITY_SHOCK' && run.step === event.effective_step) shock = p.shock_cents;
    if (event.scenario === 'SETTLEMENT_DELAY') {
      const deferred = bpsOf(settlement, p.fraction_bps); settlement -= deferred;
      run.delayed.push({ amount_cents: deferred, due_step: run.step + p.delay_steps });
    }
  }
  for (const due of run.delayed.filter((item) => item.due_step === run.step)) settlement += due.amount_cents;
  run.delayed = run.delayed.filter((item) => item.due_step > run.step);
  // Accrual is not realized interest. Maturity credits principal AND interest.
  for (const position of run.positions) {
    const numerator = BigInt(position.principal_cents) * BigInt(position.rate_bps) * 15n + position.remainder;
    const denominator = 10000n * 365n * 24n * 60n;
    position.accrued_cents += Number(numerator / denominator);
    position.remainder = numerator % denominator;
    if (position.maturity_step === run.step && position.principal_cents > 0) {
      run.checking += position.principal_cents + position.accrued_cents;
      run.yield += position.accrued_cents;
      run.alerts.push({ severity: 'SUCCESS', message: `${position.id} matured. Principal and earned interest were credited to checking.` });
      position.principal_cents = 0; position.accrued_cents = 0; position.remainder = 0n;
    }
  }
  const inflow = deposit + settlement; const requestedOutflow = withdrawal + shock;
  run.checking += inflow;
  // Attempt eligible redemption before emergency borrowing to fund payments.
  let redeemed = 0; let penalty = 0;
  const redeem = (needed) => {
    for (const position of run.positions) {
      if (needed <= 0) break;
      if (!position.principal_cents || (position.maturity_step > run.step && !position.early_redemption_allowed)) continue;
      const principal = position.principal_cents;
      const fee = position.maturity_step > run.step ? bpsOf(principal, position.penalty_bps) : 0;
      run.checking += principal - fee; redeemed += principal; penalty += fee;
      needed -= principal - fee; position.principal_cents = 0; position.accrued_cents = 0; position.remainder = 0n;
    }
  };
  if (run.checking < requestedOutflow) redeem(requestedOutflow - run.checking);
  if (run.checking < requestedOutflow) {
    const borrowed = Math.min(requestedOutflow - run.checking, Math.max(0, 1000000000 - run.borrowed));
    if (borrowed > 0) {
      run.borrowed += borrowed; run.checking += borrowed; run.emergency_events += 1;
      run.alerts.push({ severity: 'WARNING', message: 'Emergency credit was used to fund customer payouts.' });
    }
  }
  const paid = Math.min(run.checking, requestedOutflow);
  run.checking -= paid;
  const unpaid = requestedOutflow - paid;
  if (unpaid > 0) {
    run.failed_payouts += 1; run.failed_amount += unpaid;
    run.alerts.push({ severity: 'CRITICAL', message: 'A customer payout could not be fully funded.' });
  }
  run.inflow_total += inflow; run.outflow_total += paid;
  const cost = run.borrowed > 0 ? Math.max(1, bpsOf(run.borrowed, 1)) : 0;
  const paidCost = Math.min(cost, run.checking);
  run.checking -= paidCost; run.borrowing_costs += cost;
  // Unpaid borrowing costs remain liabilities, never silently disappear.
  run.borrowed += cost - paidCost;
  const pre = run.checking;
  run.history.push(historyPoint(run, inflow, paid, requestedOutflow));
  const required = reserveFor(run);
  const basis = forecastBasis(run);
  let action = 'HOLD'; let amount = 0; let executed = false;
  if (run.checking < required) {
    redeem(required - run.checking);
    if (run.checking < required) {
      action = 'LIQUIDITY_WARNING'; run.reserve_breaches += 1;
      run.alerts.push({ severity: 'WARNING', message: 'Checking is below the required reserve. Locked principal is not available liquidity.' });
    } else { action = 'WITHDRAW'; }
    amount = redeemed; executed = redeemed > 0;
  } else if (run.checking - required >= run.policy.min_sweep_cents && run.checking - required > 0) {
    action = 'SWEEP'; amount = run.checking - required;
    run.checking -= amount; addPosition(run, amount); run.sweeps += 1; executed = true;
  } else if (redeemed > 0) { action = 'WITHDRAW'; amount = redeemed; executed = true; }
  run.penalties += penalty;
  if (penalty > 0) run.alerts.push({ severity: 'WARNING', message: 'Early vault redemption incurred a penalty; accrued interest was forfeited.' });
  const explanation = action === 'SWEEP' ? ['Checking exceeded the mock reserve and minimum sweep threshold.', 'A new vault position was created using the active policy.']
    : action === 'WITHDRAW' ? ['Eligible vault principal was redeemed to replenish checking.', penalty ? 'The position’s original early redemption penalty was applied.' : 'No early redemption penalty was required.']
    : action === 'LIQUIDITY_WARNING' ? ['The reserve target cannot be fully covered by eligible liquidity.', 'Locked vault principal is excluded unless its original terms permit early redemption.']
    : ['Checking is within the configured reserve corridor.', 'No eligible transfer is required.'];
  run.decision = { id: `D-${run.step}`, timestamp: timestamp(run), action, amount_cents: amount,
    pre_checking_cents: pre, post_checking_cents: run.checking, executed,
    execution_status: action === 'HOLD' ? 'NOT_REQUIRED' : executed ? 'EXECUTED' : 'REJECTED',
    penalty_cents: penalty, required_reserve_cents: required, risk_method: 'BUFFER_BASELINE',
    peak_shortfall_cents: basis.peak, uncertainty_buffer_cents: basis.uncertainty,
    operational_buffer_cents: run.policy.operational_buffer_cents, explanation };
  run.decisions.push(clone(run.decision));
  for (const [type, direction, amountCents, source] of [
    ['DEPOSIT', 'INFLOW', deposit, 'Client deposits'], ['MERCHANT_SETTLEMENT', 'INFLOW', settlement, 'Merchant receipts'],
    ['WITHDRAWAL', 'OUTFLOW', paid, shock ? 'Customer payouts + shock' : 'Customer payouts'],
  ]) if (amountCents > 0) run.transactions.push({ id: `TX-${run.step}-${type}`, timestamp: timestamp(run), type, direction, amount_cents: amountCents, source });
  run.history[run.history.length - 1] = historyPoint(run, inflow, paid, requestedOutflow);
  return includeSnapshot ? snapshot(run) : undefined;
}

export function snapshot(run) {
  const totals = vaultTotals(run); const basis = forecastBasis(run); const reserve = reserveFor(run);
  return { run_id: run.id, step: run.step, timestamp: timestamp(run), status: run.step >= run.config.duration_steps ? 'COMPLETED' : 'PAUSED',
    duration_steps: run.config.duration_steps, seed: run.config.seed, currency: 'USD', source: 'mock',
    checking_cents: run.checking, vault_locked_cents: totals.locked, vault_redeemable_cents: totals.redeemable,
    accrued_interest_cents: totals.accrued, required_reserve_cents: reserve,
    deployable_surplus_cents: run.checking - reserve >= run.policy.min_sweep_cents ? Math.max(0, run.checking - reserve) : 0,
    realized_interest_cents: run.yield, penalties_cents: run.penalties, borrowing_costs_cents: run.borrowing_costs,
    borrowing_outstanding_cents: run.borrowed, net_benefit_cents: run.yield - run.penalties - run.borrowing_costs,
    reserve_breaches: run.reserve_breaches, failed_payouts: run.failed_payouts,
    policy: clone(run.policy), decision: clone(run.decision), alerts: clone(run.alerts),
    forecast: { horizon_minutes: 1440, peak_shortfall_cents: basis.peak, uncertainty_buffer_cents: basis.uncertainty,
      operational_buffer_cents: run.policy.operational_buffer_cents, model_version: 'mock-observed-baseline-v1', method: 'Observed moving average', risk_percentile: run.policy.risk_percentile, risk_method: 'BUFFER_BASELINE' },
    positions: run.positions.filter((p) => p.principal_cents > 0).map(({ remainder, ...p }) => ({ ...p,
      maturity_at: timestamp(run, p.maturity_step), status: p.maturity_step > run.step ? 'LOCKED' : 'REDEEMABLE' })),
    scenarios: clone(run.events),
  };
}

export function forecastSeries(run, horizon = 1440) {
  check([15, 30, 60, 1440].includes(horizon), 'Unsupported forecast horizon.');
  const basis = forecastBasis(run);
  return { as_of: timestamp(run), horizon_minutes: horizon, model_version: 'mock-observed-baseline-v1',
    method: 'Observed moving average', source: 'mock',
    points: Array.from({ length: horizon / 15 }, (_, index) => {
      const spread = Math.round(basis.uncertainty * Math.sqrt(index + 1) / 4);
      const net = basis.inflow - basis.outflow;
      return { timestamp: timestamp(run, run.step + index + 1), predicted_inflow_cents: basis.inflow,
        predicted_outflow_cents: basis.outflow, predicted_net_cents: net,
        lower_cents: net - spread, upper_cents: net + spread };
    }) };
}

export function report(run) {
  const average = Math.round(run.history.reduce((sum, p) => sum + p.checking_cents, 0) / run.history.length);
  return { run_id: run.id, seed: run.config.seed, source: 'mock', strategy: run.strategy,
    duration_steps: run.step, realized_interest_cents: run.yield, average_checking_cents: average,
    penalties_cents: run.penalties, borrowing_costs_cents: run.borrowing_costs, borrowing_outstanding_cents: run.borrowed,
    reserve_breaches: run.reserve_breaches, emergency_events: run.emergency_events, failed_payouts: run.failed_payouts,
    failed_payout_cents: run.failed_amount, sweeps: run.sweeps, net_benefit_cents: run.yield - run.penalties - run.borrowing_costs,
    inflow_cents: run.inflow_total, paid_outflow_cents: run.outflow_total };
}

export function backtest(input = {}, policy = DEFAULT_POLICY) {
  integer(input.days, 7, 30, 'Backtest days');
  check([7, 14, 30].includes(input.days), 'Unsupported duration.');
  check(SCENARIOS.some((s) => s.id === input.scenario), 'Unknown scenario.');
  const selected = input.strategies ?? STRATEGIES.map((item) => item.id);
  check(selected.length > 0 && selected.every((s) => STRATEGIES.some((item) => item.id === s)), 'Select supported strategies.');
  const results = selected.map((strategy) => {
    const run = createEngine({ seed: input.seed, duration_steps: input.days * 96, policy }, `backtest-${strategy}`, strategy);
    if (input.scenario !== 'NORMAL') scheduleScenario(run, { scenario: input.scenario, effective_step: 32, parameters: input.parameters });
    while (run.step < run.config.duration_steps) advanceEngine(run, run.step, false);
    return { ...report(run), history: run.history.filter((_, index) => index % 16 === 0 || index === run.step) };
  });
  return { status: 'COMPLETED', source: 'mock', scenario: input.scenario, seed: input.seed, days: input.days,
    model_evaluation: null, results };
}
