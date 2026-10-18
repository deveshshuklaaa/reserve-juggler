import { describe, expect, it } from 'vitest';
import { ORGANIZER_HEADERS, parseOrganizerCsv } from '../src/utils/organizerCsv';

function fixtureRow(overrides = {}) {
  return {
    timestamp: '2026-01-01 00:00:00',
    deposits_usd: '123.4500',
    withdrawals_usd: '23.45',
    net_flow_usd: '100.00',
    repo_sweep_window_open: 'True',
    repo_sweep_mature: 'False',
    tier1_repo_rate_apy: '-0.0500',
    tier2_bond_yield_pct: '-0.125',
    tier2_bond_price_index: '100.255',
    tier2_bond_mod_duration: '4.5',
    tier3_stock_index_price: '4895.71',
    tier3_stock_volatility_pct: '18.20',
    tier1_early_redemption_haircut_pct: '0.5',
    tier2_bond_liquidation_haircut_pct: '1.25',
    tier3_stock_liquidation_haircut_pct: '3.50',
    emergency_overdraft_penalty_apr_pct: '15.0',
    ...overrides,
  };
}

function csv(rows = [fixtureRow(), fixtureRow({ timestamp: '2026-01-01 01:00:00' })], headers = ORGANIZER_HEADERS) {
  return [headers.join(','), ...rows.map((row) => headers.map((field) => row[field]).join(','))].join('\n');
}

describe('official organizer CSV preview', () => {
  it('preserves every decimal string, boolean string, market field and unspecified timestamp', () => {
    const inputRows = [fixtureRow(), fixtureRow({ timestamp: '2026-01-01 01:00:00' })];
    const result = parseOrganizerCsv(csv(inputRows));
    expect(result).toEqual({ format: 'organizer', rows: inputRows, interval_minutes: 60, start_time: inputRows[0].timestamp, end_time: inputRows[1].timestamp, timezone_status: 'UNSPECIFIED', reconciliation_warnings: [] });
    expect(result.rows[0].tier1_repo_rate_apy).toBe('-0.0500');
    expect(result.rows[0].timestamp).not.toContain('Z');
  });

  it('supports reordered exact headers, quoted fields, BOM and CRLF without changing values', () => {
    const headers = [...ORGANIZER_HEADERS].reverse();
    const text = `\uFEFF${csv(undefined, headers).replaceAll('\n', '\r\n').replace('123.4500', '"123.4500"')}\r\n`;
    expect(parseOrganizerCsv(text).rows[0]).toEqual(fixtureRow());
  });

  it('reconciles exact decimals beyond binary floating-point precision', () => {
    const result = parseOrganizerCsv(csv([
      fixtureRow({ deposits_usd: '0.3', withdrawals_usd: '0.2', net_flow_usd: '0.1' }),
      fixtureRow({ timestamp: '2026-01-01 01:00:00', deposits_usd: '9007199254740993.11', withdrawals_usd: '9007199254740993.10', net_flow_usd: '0.0100' }),
    ]));
    expect(result.reconciliation_warnings).toEqual([]);
  });

  it('warns for every net difference, including sub-cent differences, while preserving it', () => {
    const rows = [fixtureRow({ net_flow_usd: '100.00000000000000000001' }), fixtureRow({ timestamp: '2026-01-01 01:00:00', net_flow_usd: '99.99' })];
    const result = parseOrganizerCsv(csv(rows));
    expect(result.rows).toEqual(rows);
    expect(result.reconciliation_warnings.map((warning) => warning.row)).toEqual([2, 3]);
    expect(result.reconciliation_warnings[0].message).toContain('preserved');
  });

  it.each(['NaN', 'Infinity', '-Infinity', '1e2', '', ' 1', '1 000', '12,000'])('rejects invalid decimal %j', (value) => {
    expect(() => parseOrganizerCsv(csv([fixtureRow({ deposits_usd: value }), fixtureRow({ timestamp: '2026-01-01 01:00:00' })]))).toThrow(/Row 2/);
  });

  it.each(['deposits_usd', 'withdrawals_usd', 'tier3_stock_volatility_pct', 'emergency_overdraft_penalty_apr_pct'])('rejects negative %s', (field) => {
    expect(() => parseOrganizerCsv(csv([fixtureRow({ [field]: '-0.001' }), fixtureRow({ timestamp: '2026-01-01 01:00:00' })]))).toThrow(/must be nonnegative/);
  });

  it.each(['tier2_bond_price_index', 'tier2_bond_mod_duration', 'tier3_stock_index_price'])('requires positive %s', (field) => {
    expect(() => parseOrganizerCsv(csv([fixtureRow({ [field]: '0.000' }), fixtureRow({ timestamp: '2026-01-01 01:00:00' })]))).toThrow(/greater than zero/);
  });

  it.each(['tier1_early_redemption_haircut_pct', 'tier2_bond_liquidation_haircut_pct', 'tier3_stock_liquidation_haircut_pct'])('requires %s between 0 and 100 inclusive', (field) => {
    for (const value of ['-0.0001', '100.00000000001']) {
      expect(() => parseOrganizerCsv(csv([fixtureRow({ [field]: value }), fixtureRow({ timestamp: '2026-01-01 01:00:00' })]))).toThrow(/between 0 and 100/);
    }
    expect(() => parseOrganizerCsv(csv([fixtureRow({ [field]: '0' }), fixtureRow({ timestamp: '2026-01-01 01:00:00', [field]: '100.0000' })]))).not.toThrow();
  });

  it.each(['true', 'FALSE', '1', 'yes', ''])('requires the source True/False booleans, rejecting %j', (value) => {
    expect(() => parseOrganizerCsv(csv([fixtureRow({ repo_sweep_window_open: value }), fixtureRow({ timestamp: '2026-01-01 01:00:00' })]))).toThrow(/must be True or False/);
  });

  it.each(['2026-02-29 00:00:00', '2026-02-30 00:00:00', '2026-13-01 00:00:00', '0000-01-01 00:00:00', '2026-01-01 24:00:00', '2026-01-01 00:15:00', '2026-01-01T00:00:00', '2026-01-01 00:00:00Z', '2026-01-01 00:00:00.000'])('rejects malformed or invalid timestamp %s', (timestamp) => {
    expect(() => parseOrganizerCsv(csv([fixtureRow({ timestamp }), fixtureRow({ timestamp: '2026-01-01 01:00:00' })]))).toThrow(/timestamp/);
  });

  it('accepts leap day and midnight across months without assigning a timezone', () => {
    const rows = [fixtureRow({ timestamp: '2024-02-29 23:00:00' }), fixtureRow({ timestamp: '2024-03-01 00:00:00' })];
    expect(parseOrganizerCsv(csv(rows)).rows).toEqual(rows);
  });

  it.each(['2026-01-01 00:00:00', '2025-12-31 23:00:00', '2026-01-01 02:00:00'])('rejects duplicate, descending or missing hours at %s', (timestamp) => {
    expect(() => parseOrganizerCsv(csv([fixtureRow(), fixtureRow({ timestamp })]))).toThrow(/continuous one-hour/);
  });

  it('requires the exact unique organizer header set and at least two rows', () => {
    expect(() => parseOrganizerCsv('')).toThrow(/empty/);
    expect(() => parseOrganizerCsv(csv([fixtureRow()]))).toThrow(/at least two/);
    expect(() => parseOrganizerCsv(csv(undefined, ORGANIZER_HEADERS.slice(1)))).toThrow(/headers must contain exactly/);
    expect(() => parseOrganizerCsv(csv(undefined, [...ORGANIZER_HEADERS, 'extra']))).toThrow(/headers must contain exactly/);
    expect(() => parseOrganizerCsv(csv(undefined, [...ORGANIZER_HEADERS.slice(0, -1), 'timestamp']))).toThrow(/duplicated/);
  });

  it('reports malformed records and enforces file size and data-row limits', () => {
    expect(() => parseOrganizerCsv(`${csv()}\n`)).not.toThrow();
    expect(() => parseOrganizerCsv(`${csv()}\n\n`)).toThrow(/Row 4/);
    expect(() => parseOrganizerCsv('x'.repeat(2 * 1024 * 1024 + 1))).toThrow(/2 MB/);
    const records = `${ORGANIZER_HEADERS.join(',')}\n${`${ORGANIZER_HEADERS.map((field) => fixtureRow()[field]).join(',')}\n`.repeat(5001)}`;
    expect(() => parseOrganizerCsv(records)).toThrow(/5,000/);
  });
});
