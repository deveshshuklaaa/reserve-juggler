export function cents(value) {
  if (!Number.isSafeInteger(value)) throw new TypeError('Expected safe integer cents.');
  return value;
}

export function money(value, compact = false) {
  if (value == null) return '—';
  cents(value);
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD',
    ...(compact ? { notation: 'compact', minimumFractionDigits: 2, maximumFractionDigits: 2 }
      : { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
  }).format(value / 100);
}

export const rate = (bps, digits = 2) => bps == null ? '—' : `${(bps / 100).toFixed(digits)}%`;
export function utc(value, date = false) {
  if (!value) return '—';
  return new Intl.DateTimeFormat('en-GB', { timeZone: 'UTC', hour: '2-digit', minute: '2-digit',
    ...(date ? { day: '2-digit', month: 'short', year: 'numeric' } : {}),
  }).format(new Date(value));
}

export function dollarsToCents(value) {
  if (!/^\d+(\.\d{1,2})?$/.test(String(value))) throw new Error('Use a positive USD amount with at most two decimal places.');
  const [whole, fraction = ''] = String(value).split('.');
  return cents(Number(whole) * 100 + Number(fraction.padEnd(2, '0')));
}

export function exportCsv(filename, headers, rows) {
  const escape = (value) => {
    let text = String(value ?? '');
    if (/^[=+@\t\r]/.test(text) || (/^-/.test(text) && !/^-\d+(\.\d+)?$/.test(text))) text = `'${text}`;
    return `"${text.replaceAll('"', '""')}"`;
  };
  const csv = [headers, ...rows].map((row) => row.map(escape).join(',')).join('\r\n');
  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8;' }));
  const link = document.createElement('a');
  link.href = url; link.download = filename; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
