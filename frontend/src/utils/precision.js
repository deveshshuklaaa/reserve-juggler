/**
 * PRECISION & TIME FORMATTING UTILITIES
 * Task F1A: Ensures precision-preserving decimal strings for market index prices,
 * yields, rates, and accurate handling of timezone-unspecified hourly timestamps.
 */

/**
 * Formats a number or decimal string to a specific fraction length without floating-point artifacts.
 */
export function formatDecimal(value, fractionDigits = 2) {
  if (value == null || value === '') return '—';
  if (!Number.isInteger(fractionDigits) || fractionDigits < 0 || fractionDigits > 20) throw new RangeError('Invalid decimal precision.');
  const match = String(value).match(/^([+-]?)(\d+)(?:\.(\d+))?$/);
  if (!match) return '—';
  const [, sign, whole, fraction = ''] = match;
  const scale = 10n ** BigInt(fractionDigits);
  let scaled = BigInt(whole) * scale + BigInt(fraction.slice(0, fractionDigits).padEnd(fractionDigits, '0') || '0');
  if (Number(fraction[fractionDigits] ?? 0) >= 5) scaled += 1n;
  const integer = (scaled / scale).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  const decimal = fractionDigits ? `.${(scaled % scale).toString().padStart(fractionDigits, '0')}` : '';
  return `${sign === '-' && scaled !== 0n ? '-' : ''}${integer}${decimal}`;
}

/**
 * Parses a decimal string safely to a float or returns fallback.
 */
export function parseDecimalString(str, fallback = 0) {
  if (str == null || str === '') return fallback;
  const num = Number(str);
  return Number.isFinite(num) ? num : fallback;
}

/**
 * Formats rate or percentage from either basis points or high-precision decimal strings.
 * Does not truncate high-precision decimals into coarse integer bps.
 */
export function formatRateDecimal(value, digits = 2, unit = 'percent') {
  if (value == null) return '—';
  if (!['percent', 'bps'].includes(unit)) throw new TypeError('Explicit rate unit must be percent or bps.');
  if (unit === 'bps') {
    if (!Number.isSafeInteger(value)) throw new TypeError('Basis points must be integer.');
    const negative = value < 0 ? '-' : '';
    const absolute = BigInt(Math.abs(value));
    value = `${negative}${absolute / 100n}.${(absolute % 100n).toString().padStart(2, '0')}`;
  }
  const formatted = formatDecimal(value, digits);
  return formatted === '—' ? formatted : `${formatted}%`;
}

/**
 * Preserves source timezone-unspecified timestamps (e.g. "2026-01-01 17:00:00" or "2026-10-17T17:00:00").
 * Does NOT append "Z" or assume UTC unless explicitly marked with "Z" or offset.
 */
export function formatSourceTimestamp(timestampStr, includeDate = true) {
  if (!timestampStr) return '—';
  const str = String(timestampStr);

  // If already contains Z or offset (+00:00, -05:00), parse as standard ISO
  if (/(Z|[+-]\d{2}:\d{2})$/.test(str)) {
    const d = new Date(str);
    if (!Number.isFinite(d.getTime())) return str;
    const timePart = `${String(d.getUTCHours()).padStart(2, '0')}:${String(d.getUTCMinutes()).padStart(2, '0')}`;
    if (!includeDate) return `${timePart} UTC`;
    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    return `${String(d.getUTCDate()).padStart(2, '0')} ${months[d.getUTCMonth()]} ${d.getUTCFullYear()} ${timePart} UTC`;
  }

  // Timezone-unspecified source string e.g. "2026-01-01 17:00:00" or "2026-01-01T17:00:00"
  const match = str.match(/^(\d{4})[-/](\d{2})[-/](\d{2})[T\s](\d{2}):(\d{2})(?::(\d{2}))?/);
  if (match) {
    const [, year, month, day, hours, minutes] = match;
    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    const monthName = months[parseInt(month, 10) - 1] ?? month;
    if (!includeDate) return `${hours}:${minutes}`;
    return `${day} ${monthName} ${year} ${hours}:${minutes}`;
  }

  return str;
}
