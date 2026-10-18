import { parseCsvRecords } from './cashflowCsv';

export const ORGANIZER_HEADERS = Object.freeze([
  'timestamp',
  'deposits_usd',
  'withdrawals_usd',
  'net_flow_usd',
  'repo_sweep_window_open',
  'repo_sweep_mature',
  'tier1_repo_rate_apy',
  'tier2_bond_yield_pct',
  'tier2_bond_price_index',
  'tier2_bond_mod_duration',
  'tier3_stock_index_price',
  'tier3_stock_volatility_pct',
  'tier1_early_redemption_haircut_pct',
  'tier2_bond_liquidation_haircut_pct',
  'tier3_stock_liquidation_haircut_pct',
  'emergency_overdraft_penalty_apr_pct',
]);

const BOOLEAN_HEADERS = new Set(['repo_sweep_window_open', 'repo_sweep_mature']);
const NONNEGATIVE_HEADERS = new Set(['deposits_usd', 'withdrawals_usd', 'tier3_stock_volatility_pct', 'emergency_overdraft_penalty_apr_pct']);
const POSITIVE_HEADERS = new Set(['tier2_bond_price_index', 'tier2_bond_mod_duration', 'tier3_stock_index_price']);
const HAIRCUT_HEADERS = new Set(['tier1_early_redemption_haircut_pct', 'tier2_bond_liquidation_haircut_pct', 'tier3_stock_liquidation_haircut_pct']);

function fail(row, message) {
  throw new Error(`Row ${row}: ${message}`);
}

function parseDecimal(value, field, row) {
  if (!/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$/.test(value) || !Number.isFinite(Number(value))) {
    fail(row, `${field} must be a finite decimal without exponent notation.`);
  }
  // Number is used only to reject infinities. All comparisons and reconciliation
  // below use the source decimal's exact integer coefficient and decimal scale.
  const negative = value.startsWith('-');
  const unsigned = value.replace(/^[+-]/, '');
  const [whole = '', fraction = ''] = unsigned.split('.');
  const reducedFraction = fraction.replace(/0+$/, '');
  const digits = `${whole}${reducedFraction}`.replace(/^0+/, '') || '0';
  return { coefficient: BigInt(digits) * (negative ? -1n : 1n), scale: reducedFraction.length };
}

function scaled(decimal, scale) {
  return decimal.coefficient * (10n ** BigInt(scale - decimal.scale));
}

function validateDecimal(decimal, field, row) {
  if (NONNEGATIVE_HEADERS.has(field) && decimal.coefficient < 0n) fail(row, `${field} must be nonnegative.`);
  if (POSITIVE_HEADERS.has(field) && decimal.coefficient <= 0n) fail(row, `${field} must be greater than zero.`);
  if (HAIRCUT_HEADERS.has(field) && (decimal.coefficient < 0n || decimal.coefficient > 100n * 10n ** BigInt(decimal.scale))) {
    fail(row, `${field} must be between 0 and 100 percent.`);
  }
}

function timestampCalendarValue(value, row) {
  const match = /^(\d{4})-(\d{2})-(\d{2}) (\d{2}):00:00$/.exec(value);
  if (!match) fail(row, 'timestamp must use the organizer format YYYY-MM-DD HH:00:00, with no timezone suffix.');
  const [, yearText, monthText, dayText, hourText] = match;
  const [year, month, day, hour] = [yearText, monthText, dayText, hourText].map(Number);
  const leapYear = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  const monthDays = [31, leapYear ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  if (year < 1 || month < 1 || month > 12 || day < 1 || day > monthDays[month - 1] || hour > 23) {
    fail(row, 'timestamp contains an invalid calendar date or hour.');
  }
  // UTC setters provide timezone-independent calendar arithmetic only. This
  // does not assign a timezone to the source or change the stored timestamp.
  const calendar = new Date(0);
  calendar.setUTCFullYear(year, month - 1, day);
  calendar.setUTCHours(hour, 0, 0, 0);
  return calendar.getTime();
}

/**
 * Validate an immutable organizer data preview. Every cell remains its source
 * string; no dollars-to-cents conversion, resampling, or backend upload occurs.
 */
export function parseOrganizerCsv(text) {
  const records = parseCsvRecords(text);
  if (!records.length) throw new Error('The organizer CSV is empty. Add the official header and at least two hourly rows.');
  const headers = records[0].cells;
  if (new Set(headers).size !== headers.length) fail(records[0].line, 'CSV headers must not be duplicated.');
  if (headers.length !== ORGANIZER_HEADERS.length || ORGANIZER_HEADERS.some((header) => !headers.includes(header))) {
    fail(records[0].line, `Organizer CSV headers must contain exactly ${ORGANIZER_HEADERS.join(', ')}.`);
  }
  if (records.length < 3) throw new Error('Add at least two continuous hourly organizer rows.');

  const rows = [];
  const reconciliationWarnings = [];
  let previousTime;
  for (const record of records.slice(1)) {
    if (record.cells.length !== ORGANIZER_HEADERS.length) fail(record.line, `expected ${ORGANIZER_HEADERS.length} fields; found ${record.cells.length}.`);
    const row = Object.fromEntries(headers.map((field, index) => [field, record.cells[index]]));
    const time = timestampCalendarValue(row.timestamp, record.line);
    if (previousTime !== undefined && time - previousTime !== 60 * 60 * 1000) {
      fail(record.line, 'timestamps must be strictly increasing at continuous one-hour intervals, without duplicates or gaps.');
    }
    const decimals = {};
    for (const field of ORGANIZER_HEADERS.slice(1)) {
      if (BOOLEAN_HEADERS.has(field)) {
        if (row[field] !== 'True' && row[field] !== 'False') fail(record.line, `${field} must be True or False.`);
      } else {
        decimals[field] = parseDecimal(row[field], field, record.line);
        validateDecimal(decimals[field], field, record.line);
      }
    }
    const deposits = decimals.deposits_usd;
    const withdrawals = decimals.withdrawals_usd;
    const net = decimals.net_flow_usd;
    const scale = Math.max(deposits.scale, withdrawals.scale, net.scale);
    if (scaled(deposits, scale) - scaled(withdrawals, scale) !== scaled(net, scale)) {
      reconciliationWarnings.push({ row: record.line, message: 'net_flow_usd differs from deposits_usd minus withdrawals_usd. The supplied values are preserved.' });
    }
    rows.push(row);
    previousTime = time;
  }

  return {
    format: 'organizer',
    rows,
    interval_minutes: 60,
    start_time: rows[0].timestamp,
    end_time: rows[rows.length - 1].timestamp,
    timezone_status: 'UNSPECIFIED',
    reconciliation_warnings: reconciliationWarnings,
  };
}
