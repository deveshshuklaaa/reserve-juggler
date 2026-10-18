const HEADERS = ['timestamp', 'inflow_cents', 'outflow_cents'];
const MAX_ROWS = 5000;
const MAX_BYTES = 2 * 1024 * 1024;
const MAX_CENTS = BigInt(Number.MAX_SAFE_INTEGER);

function fail(row, message) {
  throw new Error(`Row ${row}: ${message}`);
}

function checkSize(text) {
  let bytes = 0;
  for (const character of text) {
    const code = character.codePointAt(0);
    bytes += code <= 0x7f ? 1 : code <= 0x7ff ? 2 : code <= 0xffff ? 3 : 4;
    if (bytes > MAX_BYTES) throw new Error('CSV files must be 2 MB or smaller.');
  }
}

// Keep physical line numbers, including inside quoted cells, for useful import errors.
// Domain-specific timestamp and amount validation belongs to the caller.
export function parseCsvRecords(text) {
  if (typeof text !== 'string') throw new TypeError('CSV content must be text.');
  checkSize(text);
  text = text.replace(/^\uFEFF/, '');
  const records = [];
  let cells = [];
  let value = '';
  let quoted = false;
  let closedQuote = false;
  let line = 1;
  let recordLine = 1;

  const finishRecord = () => {
    cells.push(value);
    records.push({ cells, line: recordLine });
    cells = [];
    value = '';
    closedQuote = false;
  };

  for (let index = 0; index < text.length; index += 1) {
    const character = text[index];
    if (quoted) {
      if (character === '"') {
        if (text[index + 1] === '"') {
          value += '"';
          index += 1;
        } else {
          quoted = false;
          closedQuote = true;
        }
      } else {
        value += character;
        if (character === '\n' || (character === '\r' && text[index + 1] !== '\n')) line += 1;
      }
      continue;
    }

    if (character === ',') {
      cells.push(value);
      value = '';
      closedQuote = false;
    } else if (character === '\r' || character === '\n') {
      finishRecord();
      if (character === '\r' && text[index + 1] === '\n') index += 1;
      line += 1;
      recordLine = line;
    } else if (character === '"') {
      if (value !== '' || closedQuote) fail(line, 'a quote must start a field and quoted fields must be closed before the next field.');
      quoted = true;
    } else {
      if (closedQuote) fail(line, 'unexpected text after a closing quote.');
      value += character;
    }
  }

  if (quoted) fail(recordLine, 'the quoted field is not closed.');
  if (value !== '' || cells.length || closedQuote) finishRecord();
  // Spreadsheet exports can retain thousands of empty trailing records.
  // Remove only the empty suffix: interior gaps must still fail validation,
  // and physical source line numbers must remain intact.
  while (records.length && records.at(-1).cells.every((cell) => cell.trim() === '')) records.pop();
  if (records.length > MAX_ROWS + 1) fail(records[MAX_ROWS + 1].line, `a maximum of ${MAX_ROWS.toLocaleString('en-US')} cash-flow rows is supported.`);
  return records;
}

function parseTimestamp(value, row) {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,3}))?Z$/.exec(value);
  if (!match) fail(row, 'timestamp must be ISO 8601 UTC, for example 2026-01-01T00:00:00Z.');
  const [, yearText, monthText, dayText, hourText, minuteText, secondText] = match;
  const [year, month, day, hour, minute, second] = [yearText, monthText, dayText, hourText, minuteText, secondText].map(Number);
  const leapYear = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  const monthDays = [31, leapYear ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  if (month < 1 || month > 12 || day < 1 || day > monthDays[month - 1] || hour > 23 || minute > 59 || second > 59) {
    fail(row, 'timestamp contains an invalid UTC calendar date or time.');
  }
  // Validate calendar components first: Date.parse alone normalizes dates such as February 30.
  const milliseconds = Date.parse(value);
  if (!Number.isFinite(milliseconds)) fail(row, 'timestamp is outside the supported UTC date range.');
  return { milliseconds, timestamp: new Date(milliseconds).toISOString() };
}

function parseCents(value, field, row) {
  if (!/^\d+$/.test(value)) fail(row, `${field} must be a nonnegative integer number of cents.`);
  // Avoid constructing arbitrarily large integers from an oversized numeric field.
  const significant = value.replace(/^0+/, '') || '0';
  if (significant.length > 16) fail(row, `${field} exceeds the safe integer limit.`);
  const cents = BigInt(significant);
  if (cents > MAX_CENTS) fail(row, `${field} exceeds the safe integer limit.`);
  return { cents, value: Number(cents) };
}

/**
 * Parse a local, canonical cash-flow CSV. Amounts are integer USD cents; no dollar
 * conversion or backend upload occurs here. Two or more equally spaced records
 * are required so a 15-minute or hourly input series has an explicit interval.
 */
export function parseCashflowCsv(text) {
  const records = parseCsvRecords(text);
  if (!records.length) throw new Error('The CSV is empty. Add the timestamp,inflow_cents,outflow_cents header and at least two cash-flow rows.');

  const headers = records[0].cells.map((cell) => cell.trim());
  if (new Set(headers).size !== headers.length) fail(records[0].line, 'CSV headers must not be duplicated.');
  if (headers.length !== HEADERS.length || HEADERS.some((header) => !headers.includes(header))) {
    fail(records[0].line, `CSV headers must contain exactly ${HEADERS.join(', ')}.`);
  }
  if (records.length < 3) throw new Error('Add at least two cash-flow rows to establish a 15-minute or 60-minute interval.');

  const indexes = Object.fromEntries(HEADERS.map((header) => [header, headers.indexOf(header)]));
  const rows = [];
  let intervalMinutes;
  let previousTimestamp;
  let totalInflow = 0n;
  let totalOutflow = 0n;

  for (const record of records.slice(1)) {
    if (record.cells.length !== HEADERS.length) fail(record.line, `expected ${HEADERS.length} fields; found ${record.cells.length}.`);
    const values = record.cells.map((cell) => cell.trim());
    for (const header of HEADERS) {
      if (!values[indexes[header]]) fail(record.line, `${header} is required.`);
    }
    const { milliseconds, timestamp } = parseTimestamp(values[indexes.timestamp], record.line);
    if (previousTimestamp !== undefined) {
      const gap = (milliseconds - previousTimestamp) / 60000;
      if (gap <= 0) fail(record.line, 'timestamps must be strictly increasing without duplicates.');
      if (gap !== 15 && gap !== 60) fail(record.line, 'timestamps must have regular intervals of exactly 15 or 60 minutes.');
      if (intervalMinutes !== undefined && gap !== intervalMinutes) fail(record.line, `timestamp interval must remain ${intervalMinutes} minutes throughout the file.`);
      intervalMinutes = gap;
    }
    const inflow = parseCents(values[indexes.inflow_cents], 'inflow_cents', record.line);
    const outflow = parseCents(values[indexes.outflow_cents], 'outflow_cents', record.line);
    totalInflow += inflow.cents;
    totalOutflow += outflow.cents;
    if (totalInflow > MAX_CENTS || totalOutflow > MAX_CENTS) fail(record.line, 'combined cash-flow totals exceed the safe integer limit.');
    const net = totalInflow - totalOutflow;
    if (net > MAX_CENTS || net < -MAX_CENTS) fail(record.line, 'cumulative net cash flow exceeds the safe integer limit.');
    rows.push({ timestamp, inflow_cents: inflow.value, outflow_cents: outflow.value });
    previousTimestamp = milliseconds;
  }

  return {
    rows,
    interval_minutes: intervalMinutes,
    total_inflow_cents: Number(totalInflow),
    total_outflow_cents: Number(totalOutflow),
    start_time: rows[0].timestamp,
    end_time: rows[rows.length - 1].timestamp,
  };
}
