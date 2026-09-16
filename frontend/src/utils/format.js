/**
 * Display formatting helpers.
 *
 * These change how a value *looks*, never what it is. Rates arrive from the API
 * as fractions (0.3022) and are rendered as percentages here; the underlying
 * metric is untouched.
 *
 * Every formatter returns an em dash for null/undefined/NaN/Infinity rather
 * than printing "NaN" or "₹Infinity" into the UI.
 */

const EMPTY = '—'

function isFiniteNumber(value) {
  return typeof value === 'number' && Number.isFinite(value)
}

/**
 * Parse a 'YYYY-MM-DD' string into a local Date.
 *
 * `new Date('2026-03-20')` parses as UTC midnight, which renders as the
 * previous day in any negative-offset timezone. Building from components keeps
 * the date the API sent.
 */
export function parseIsoDate(iso) {
  if (typeof iso !== 'string') return null
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso)
  if (!match) return null
  const date = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]))
  return Number.isNaN(date.getTime()) ? null : date
}

export function toIsoDate(date) {
  if (!(date instanceof Date) || Number.isNaN(date.getTime())) return ''
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${date.getFullYear()}-${month}-${day}`
}

/** Shift an ISO date by a number of days, returning an ISO date. */
export function shiftDays(iso, days) {
  const date = parseIsoDate(iso)
  if (!date) return ''
  date.setDate(date.getDate() + days)
  return toIsoDate(date)
}

/** The later of two ISO dates. Used to clamp a preset to the data's start. */
export function maxIsoDate(a, b) {
  if (!a) return b
  if (!b) return a
  return a > b ? a : b
}

export function formatDate(iso, { withYear = false } = {}) {
  const date = parseIsoDate(iso)
  if (!date) return EMPTY
  return date.toLocaleDateString('en-IN', {
    day: 'numeric',
    month: 'short',
    ...(withYear ? { year: 'numeric' } : {}),
  })
}

/** Full INR amount with Indian digit grouping, e.g. ₹17,51,857. */
export function formatCurrency(value, { decimals = 0 } = {}) {
  if (!isFiniteNumber(value)) return EMPTY
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value)
}

/**
 * Short INR amount for chart axes, using Indian scale words (K / L / Cr).
 * A 180-day axis has no room for ₹1,75,18,565.
 */
export function formatCurrencyCompact(value) {
  if (!isFiniteNumber(value)) return EMPTY
  const abs = Math.abs(value)
  if (abs >= 1e7) return `₹${(value / 1e7).toFixed(abs >= 1e8 ? 0 : 1)}Cr`
  if (abs >= 1e5) return `₹${(value / 1e5).toFixed(abs >= 1e6 ? 0 : 1)}L`
  if (abs >= 1e3) return `₹${(value / 1e3).toFixed(0)}K`
  return `₹${Math.round(value)}`
}

export function formatNumber(value) {
  if (!isFiniteNumber(value)) return EMPTY
  return new Intl.NumberFormat('en-IN').format(Math.round(value))
}

export function formatNumberCompact(value) {
  if (!isFiniteNumber(value)) return EMPTY
  const abs = Math.abs(value)
  if (abs >= 1e7) return `${(value / 1e7).toFixed(1)}Cr`
  if (abs >= 1e5) return `${(value / 1e5).toFixed(1)}L`
  if (abs >= 1e3) return `${(value / 1e3).toFixed(1)}K`
  return formatNumber(value)
}

/** Render a fraction (0.3022) as a percentage (30.2%). */
export function formatPercent(fraction, { decimals = 1 } = {}) {
  if (!isFiniteNumber(fraction)) return EMPTY
  return `${(fraction * 100).toFixed(decimals)}%`
}

/** Same, but always signed — for change indicators. */
export function formatSignedPercent(fraction, { decimals = 1 } = {}) {
  if (!isFiniteNumber(fraction)) return EMPTY
  const percent = fraction * 100
  return `${percent > 0 ? '+' : ''}${percent.toFixed(decimals)}%`
}

/** "20 Mar 2026 – 15 Sep 2026", or a single date when both ends match. */
export function formatDateRange(start, end) {
  if (!start || !end) return EMPTY
  if (start === end) return formatDate(start, { withYear: true })
  return `${formatDate(start)} – ${formatDate(end, { withYear: true })}`
}
