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
  const num = typeof value === 'number' ? value : Number(value);
  if (!Number.isFinite(num)) return '—';
  return num.toLocaleString('en-US', {
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  });
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
export function formatRateDecimal(value, digits = 2) {
  if (value == null) return '—';
  if (typeof value === 'string' && value.includes('.')) {
    const num = Number(value);
    return Number.isFinite(num) ? `${num.toFixed(digits)}%` : `${value}%`;
  }
  if (typeof value === 'number') {
    // If > 50, likely bps (e.g. 520 -> 5.20%)
    if (value > 50) return `${(value / 100).toFixed(digits)}%`;
    return `${value.toFixed(digits)}%`;
  }
  return String(value);
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
