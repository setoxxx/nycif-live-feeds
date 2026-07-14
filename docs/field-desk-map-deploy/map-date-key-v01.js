/** Prefer explicit YYYY-MM-DD row.date; only derive from timestamps when absent/invalid. */
export function isValidDateKey(value) {
  return /^\d{4}-\d{2}-\d{2}$/.test(String(value || ''));
}

export function dateKeyFromLocalDate(date) {
  if (!date || Number.isNaN(date.getTime())) return '';
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}

export function eventDateKey(row = {}, start = null) {
  const raw = String(row.date || '').trim();
  if (isValidDateKey(raw)) return raw;
  const fromStart = start instanceof Date ? dateKeyFromLocalDate(start) : '';
  if (fromStart) return fromStart;
  const slice = String(row.start_date_time || row.start || '').slice(0, 10);
  return isValidDateKey(slice) ? slice : '';
}
