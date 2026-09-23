/**
 * Short-term forecast (Stage 6).
 *
 * Reuses TrendChart so the projection is drawn with the same axes, tooltip and
 * spacing as every other chart. Recent actuals and the projection are separate
 * series, joined at the last observed day so the lines meet.
 *
 * When the API reports the history is too short, the panel explains that rather
 * than drawing an empty chart.
 */
import { TrendChart } from './TrendChart'
import { formatCurrency, formatCurrencyCompact, formatDate, formatPercent } from '../utils/format'

// Sage for what happened, champagne for what is only projected — the same
// meaning the two colours carry everywhere else in the theme.
const ACTUAL_COLOR = '#b8e49d'
const FORECAST_COLOR = '#e5bd75'

// How much history to show behind the projection.
const CONTEXT_DAYS = 21

const TREND_LABEL = {
  rising: { text: 'Rising', className: 'bg-sage/12 text-sage ring-sage/30' },
  falling: { text: 'Falling', className: 'bg-alert/12 text-alert ring-alert/30' },
  flat: { text: 'Flat', className: 'bg-white/8 text-muted ring-white/12' },
}

function buildSeries(daily, forecast) {
  const history = (daily ?? []).slice(-CONTEXT_DAYS)
  const rows = history.map((point) => ({
    date: point.date,
    actual: point.revenue,
    projected: null,
  }))

  // Join the two lines at the last observed day, otherwise they render as two
  // disconnected fragments.
  if (rows.length > 0) {
    rows[rows.length - 1].projected = rows[rows.length - 1].actual
  }

  ;(forecast.points ?? []).forEach((point) => {
    rows.push({ date: point.date, actual: null, projected: point.value })
  })

  return rows
}

export function ForecastPanel({ daily, forecast }) {
  if (!forecast) return null

  if (!forecast.available) {
    return (
      <section className="pulse-lift rounded-2xl border border-white/8 bg-gradient-to-b from-raised to-surface p-4 shadow-[0_12px_30px_rgb(0_0_0/0.25)] sm:p-5">
        <header className="mb-3">
          <h3 className="text-sm font-semibold text-cream">Revenue forecast</h3>
        </header>
        <p className="rounded-xl bg-white/4 p-4 text-sm text-muted">
          {forecast.reason ?? 'A forecast is not available for this period.'}
        </p>
      </section>
    )
  }

  const trend = TREND_LABEL[forecast.trend_direction] ?? TREND_LABEL.flat
  const backtestError = forecast.backtest?.mean_absolute_percentage_error
  // Defensive: the response model always sets these when available is true, but
  // a render crash here would blank the whole page, not just this panel.
  const period = forecast.forecast_period
  const limitations = forecast.limitations ?? []
  const method = forecast.method ?? 'projection'

  return (
    <section className="pulse-lift rounded-2xl border border-white/8 bg-gradient-to-b from-raised to-surface p-4 shadow-[0_12px_30px_rgb(0_0_0/0.25)] sm:p-5">
      <header className="mb-4 flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold text-cream">Revenue forecast</h3>
          {period && (
            <p className="mt-0.5 text-xs text-faint">
              Next {period.days} days · {formatDate(period.start)} to{' '}
              {formatDate(period.end, { withYear: true })}
            </p>
          )}
        </div>
        <span
          className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${trend.className}`}
        >
          {trend.text} trend
        </span>
      </header>

      <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-3">
        <div className="rounded-xl bg-white/4 p-3">
          <p className="text-xs text-faint">Projected total</p>
          <p className="mt-0.5 text-lg font-semibold tabular-nums text-cream">
            {formatCurrency(forecast.forecast_total)}
          </p>
        </div>
        <div className="rounded-xl bg-white/4 p-3">
          <p className="text-xs text-faint">Recent daily average</p>
          <p className="mt-0.5 text-lg font-semibold tabular-nums text-cream">
            {formatCurrency(forecast.history_daily_mean)}
          </p>
        </div>
        <div className="col-span-2 rounded-xl bg-white/4 p-3 sm:col-span-1">
          <p className="text-xs text-faint">Typical error (measured)</p>
          <p className="mt-0.5 text-lg font-semibold tabular-nums text-cream">
            {backtestError == null ? 'Not measured' : formatPercent(backtestError)}
          </p>
        </div>
      </div>

      <TrendChart
        title="Actual and projected daily revenue"
        subtitle={`Method: ${method.replaceAll('_', ' ')}`}
        data={buildSeries(daily, forecast)}
        height={260}
        valueFormatter={formatCurrency}
        axisFormatter={formatCurrencyCompact}
        series={[
          { key: 'actual', label: 'Actual', color: ACTUAL_COLOR, type: 'line' },
          { key: 'projected', label: 'Projected', color: FORECAST_COLOR, type: 'line' },
        ]}
      />

      {limitations.length > 0 && (
        <ul className="mt-4 space-y-1 border-t border-white/8 pt-3">
          {limitations.map((note) => (
            <li key={note} className="text-xs text-faint">
              {note}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

export function ForecastSkeleton() {
  return (
    <div className="pulse-lift rounded-2xl border border-white/8 bg-gradient-to-b from-raised to-surface p-4 shadow-[0_12px_30px_rgb(0_0_0/0.25)] sm:p-5">
      <div className="h-4 w-32 animate-pulse rounded bg-white/8" />
      <div className="mt-1 h-3 w-48 animate-pulse rounded bg-white/5" />
      <div className="mt-4 grid grid-cols-3 gap-3">
        {[0, 1, 2].map((index) => (
          <div key={index} className="h-16 animate-pulse rounded-lg bg-white/5" />
        ))}
      </div>
      <div className="mt-4 h-[260px] animate-pulse rounded-lg bg-white/5" />
    </div>
  )
}
