/**
 * Weekday grouping for the "customer rhythm" panel.
 *
 * This is a presentation grouping, not a new metric: it averages the daily
 * values the API has already returned in GET /api/dashboard. No threshold,
 * comparison or business rule lives here — those all stay in the backend, so
 * the dashboard and the API still cannot disagree about any published figure.
 */
import { parseIsoDate } from './format'

// Monday first: a merchant reads their week that way, and it puts the weekend
// at the end where the peak usually sits.
export const WEEKDAY_LABELS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

/**
 * Average `field` per weekday across the supplied daily points.
 *
 * Returns seven entries, Monday through Sunday, each with the mean of the days
 * that fell on it, how many days contributed, and the value as a share of the
 * strongest weekday (`share`, 0–1) so bars can be drawn without the caller
 * rescaling. Weekdays with no data have `days: 0` and `value: 0`.
 */
export function weekdayRhythm(daily, field = 'revenue') {
  const totals = WEEKDAY_LABELS.map((label) => ({ label, total: 0, days: 0 }))

  for (const point of daily ?? []) {
    const parsed = parseIsoDate(point?.date)
    if (!parsed) continue

    // Number(null) is 0, so a missing value would otherwise be averaged in as
    // a zero-revenue day rather than as no reading at all.
    const raw = point?.[field]
    if (raw === null || raw === undefined) continue

    const value = Number(raw)
    if (!Number.isFinite(value)) continue

    // getDay() is Sunday-first; shift it so Monday lands at index 0.
    const index = (parsed.getDay() + 6) % 7
    totals[index].total += value
    totals[index].days += 1
  }

  const averages = totals.map((entry) => ({
    label: entry.label,
    days: entry.days,
    value: entry.days > 0 ? entry.total / entry.days : 0,
  }))

  const peak = Math.max(...averages.map((entry) => entry.value))

  return averages.map((entry) => ({
    ...entry,
    share: peak > 0 ? entry.value / peak : 0,
    isPeak: peak > 0 && entry.value === peak,
  }))
}
