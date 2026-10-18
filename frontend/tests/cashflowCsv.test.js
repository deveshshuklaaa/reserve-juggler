import { describe, expect, it } from 'vitest';
import { parseCashflowCsv, parseCsvRecords } from '../src/utils/cashflowCsv';

const HEADER = 'timestamp,inflow_cents,outflow_cents';
const csv = (...rows) => [HEADER, ...rows].join('\n');
const validRows = ['2026-01-01T00:00:00Z,12500,4000', '2026-01-01T00:15:00Z,0,2500'];

describe('cash-flow CSV import', () => {
  it('exports a domain-neutral tokenizer with correct physical line numbers', () => {
    expect(parseCsvRecords('\uFEFFtimestamp,description\r\n2026-01-01 00:00:00,"A, B\r\nC ""quoted"""\r\nnext,value')).toEqual([
      { cells: ['timestamp', 'description'], line: 1 },
      { cells: ['2026-01-01 00:00:00', 'A, B\r\nC "quoted"'], line: 2 },
      { cells: ['next', 'value'], line: 4 },
    ]);
  });

  it('keeps exact integer cents and identifies a quarter-hour series', () => {
    expect(parseCashflowCsv(csv(...validRows))).toEqual({
      rows: [
        { timestamp: '2026-01-01T00:00:00.000Z', inflow_cents: 12500, outflow_cents: 4000 },
        { timestamp: '2026-01-01T00:15:00.000Z', inflow_cents: 0, outflow_cents: 2500 },
      ],
      interval_minutes: 15,
      total_inflow_cents: 12500,
      total_outflow_cents: 6500,
      start_time: '2026-01-01T00:00:00.000Z',
      end_time: '2026-01-01T00:15:00.000Z',
    });
  });

  it('accepts BOM, CRLF, quoted cells, reordered headers, and hourly data', () => {
    const text = '\uFEFF"outflow_cents","timestamp","inflow_cents"\r\n"40","2024-02-29T23:00:00Z","00050"\r\n"60","2024-03-01T00:00:00Z","100"\r\n';
    const result = parseCashflowCsv(text);
    expect(result.interval_minutes).toBe(60);
    expect(result.total_inflow_cents).toBe(150);
    expect(result.total_outflow_cents).toBe(100);
  });

  it.each(['', HEADER, csv(validRows[0])])('rejects missing or insufficient data: %s', (text) => {
    expect(() => parseCashflowCsv(text)).toThrow(/empty|at least two/i);
  });

  it.each([
    ['timestamp,inflow_cents,inflow_cents', /Row 1:.*duplicated/],
    ['timestamp,inflow_cents', /Row 1:.*exactly/],
    ['timestamp,inflow_cents,outflow_cents,policy', /Row 1:.*exactly/],
    ['timestamp,inflow,outflow', /Row 1:.*exactly/],
  ])('rejects ambiguous or noncanonical headers: %s', (header, error) => {
    expect(() => parseCashflowCsv([header, ...validRows].join('\n'))).toThrow(error);
  });

  it.each([
    ['2026-01-01T00:00:00Z,,1', /Row 2:.*inflow_cents is required/],
    ['2026-01-01T00:00:00Z,1', /Row 2:.*expected 3 fields/],
    ['2026-01-01T00:00:00Z,1,2,3', /Row 2:.*expected 3 fields/],
    ['', /Row 2:.*expected 3 fields/],
  ])('reports missing cells and blank rows at their source line', (row, error) => {
    expect(() => parseCashflowCsv(csv(row, validRows[1]))).toThrow(error);
  });

  it.each(['-1', '1.25', '1e3', '+1', '=1+1', 'NaN', '9007199254740992'])('rejects invalid cents: %s', (amount) => {
    expect(() => parseCashflowCsv(csv(`2026-01-01T00:00:00Z,${amount},0`, validRows[1]))).toThrow(/Row 2:.*inflow_cents/);
  });

  it('rejects unsafe aggregate totals even when individual rows are safe', () => {
    expect(() => parseCashflowCsv(csv('2026-01-01T00:00:00Z,9007199254740991,0', '2026-01-01T00:15:00Z,1,0'))).toThrow(/Row 3:.*totals exceed/);
  });

  it.each([
    '2026-02-29T00:00:00Z',
    '2026-02-30T00:00:00Z',
    '2026-13-01T00:00:00Z',
    '2026-01-01T24:00:00Z',
    '2026-01-01T00:60:00Z',
    '2026-01-01T00:00:60Z',
    '2026-01-01T00:00:00+00:00',
    '2026-01-01 00:00:00',
  ])('rejects invalid calendars or non-UTC timestamps: %s', (timestamp) => {
    expect(() => parseCashflowCsv(csv(`${timestamp},0,0`, validRows[1]))).toThrow(/Row 2:.*timestamp/);
  });

  it.each([
    ['2026-01-01T00:00:00Z', /strictly increasing/],
    ['2025-12-31T23:45:00Z', /strictly increasing/],
    ['2026-01-01T00:30:00Z', /exactly 15 or 60/],
  ])('rejects duplicate, reversed, or unsupported intervals', (timestamp, error) => {
    expect(() => parseCashflowCsv(csv(validRows[0], `${timestamp},0,0`))).toThrow(error);
  });

  it('rejects mixed hourly and quarter-hour intervals', () => {
    expect(() => parseCashflowCsv(csv(...validRows, '2026-01-01T01:15:00Z,0,0'))).toThrow(/Row 4:.*remain 15 minutes/);
  });

  it.each([
    ['"2026-01-01T00:00:00Z,0,0', /quoted field is not closed/],
    ['2026-01-01T00:00:00Z,1"0,0', /Row 2:.*quote must start/],
    ['"2026-01-01T00:00:00Z"oops,0,0', /Row 2:.*closing quote/],
  ])('rejects malformed quoted fields', (row, error) => {
    expect(() => parseCashflowCsv(csv(row, validRows[1]))).toThrow(error);
  });

  it('handles escaped quotes as cell content and then rejects the invalid financial value', () => {
    expect(() => parseCashflowCsv(csv('2026-01-01T00:00:00Z,"1""2",0', validRows[1]))).toThrow(/Row 2:.*inflow_cents/);
  });

  it('accepts 5000 rows but rejects the next row without silently truncating', () => {
    const rows = Array.from({ length: 5001 }, (_, index) => `${new Date(Date.UTC(2026, 0, 1) + index * 15 * 60000).toISOString()},0,0`);
    expect(parseCashflowCsv(csv(...rows.slice(0, 5000))).rows).toHaveLength(5000);
    expect(() => parseCashflowCsv(csv(...rows))).toThrow(/Row 5002:.*maximum of 5,000/);
  });

  it('ignores only a fully empty suffix, including quoted and whitespace cells', () => {
    expect(parseCashflowCsv(`${csv(...validRows)}\n${',,\n'.repeat(5075)}""," ",\r\n\n`).rows).toHaveLength(2);
    expect(() => parseCashflowCsv(`${csv(...validRows)}\n,,\n2026-01-01T00:30:00Z,,0`)).toThrow(/Row 4/);
    expect(() => parseCashflowCsv(`${csv(...validRows)}\n,1,`)).toThrow(/Row 4/);
    expect(() => parseCashflowCsv(`${csv(...validRows)}\n"`)).toThrow(/quoted field is not closed/);
  });

  it('rejects oversized text before parsing', () => {
    expect(() => parseCashflowCsv('x'.repeat(2 * 1024 * 1024 + 1))).toThrow(/2 MB/);
  });
});
