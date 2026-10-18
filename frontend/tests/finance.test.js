import { describe, expect, it } from 'vitest';
import { cents, dollarsToCents, money, rate, utc } from '../src/utils/format';

describe('financial display conventions', () => {
  it('converts cents to exact USD including zero and negatives', () => {
    expect(money(500000000)).toBe('$5,000,000.00');
    expect(money(0)).toBe('$0.00'); expect(money(-12345)).toBe('-$123.45');
  });
  it('distinguishes missing values from zero', () => {
    expect(money(null)).toBe('—'); expect(money(undefined)).toBe('—');
  });
  it('rejects floating-point money and unsafe integers', () => {
    expect(() => cents(1.5)).toThrow(); expect(() => money(Number.MAX_SAFE_INTEGER + 1)).toThrow();
  });
  it('parses dollar inputs without fractional-cent ambiguity', () => {
    expect(dollarsToCents('0.01')).toBe(1); expect(dollarsToCents('100.10')).toBe(10010);
    for (const input of ['-3', '1.001', '', 'NaN']) expect(() => dollarsToCents(input)).toThrow();
  });
  it('formats basis points and UTC independently of local timezone', () => {
    expect(rate(500)).toBe('5.00%'); expect(rate(0)).toBe('0.00%');
    expect(utc('2026-10-17T08:15:00Z')).toBe('08:15');
  });
});
