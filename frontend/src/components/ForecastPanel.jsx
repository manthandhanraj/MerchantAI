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

const ACTUAL_COLOR = '#0f766e'
const FORECAST_COLOR = '#7c3aed'

// How much history to show behind the projection.
const CONTEXT_DAYS = 21

const TREND_LABEL = {
  rising: { text: 'Rising', className: 'bg-emerald-50 text-emerald-700 ring-emerald-200' },
  falling: { text: 'Falling', className: 'bg-red-50 text-red-700 ring-red-200' },
  flat: { text: 'Flat', className: 'bg-slate-100 text-slate-600 ring-slate-200' },
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
      <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5">
        <header className="mb-3">
          <h3 className="text-sm font-semibold text-slate-900">Revenue forecast</h3>
        </header>
        <p className="rounded-lg bg-slate-50 p-4 text-sm text-slate-600">
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
    <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5">
      <header className="mb-4 flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold text-slate-900">Revenue forecast</h3>
          {period && (
            <p className="mt-0.5 text-xs text-slate-500">
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
        <div className="rounded-lg bg-slate-50 p-3">
          <p className="text-xs text-slate-500">Projected total</p>
          <p className="mt-0.5 text-lg font-semibold tabular-nums text-slate-900">
            {formatCurrency(forecast.forecast_total)}
          </p>
        </div>
        <div className="rounded-lg bg-slate-50 p-3">
          <p className="text-xs text-slate-500">Recent daily average</p>
          <p className="mt-0.5 text-lg font-semibold tabular-nums text-slate-900">
            {formatCurrency(forecast.history_daily_mean)}
          </p>
        </div>
        <div className="col-span-2 rounded-lg bg-slate-50 p-3 sm:col-span-1">
          <p className="text-xs text-slate-500">Typical error (measured)</p>
          <p className="mt-0.5 text-lg font-semibold tabular-nums text-slate-900">
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
        <ul className="mt-4 space-y-1 border-t border-slate-100 pt-3">
          {limitations.map((note) => (
            <li key={note} className="text-xs text-slate-500">
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
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5">
      <div className="h-4 w-32 animate-pulse rounded bg-slate-200" />
      <div className="mt-1 h-3 w-48 animate-pulse rounded bg-slate-100" />
      <div className="mt-4 grid grid-cols-3 gap-3">
        {[0, 1, 2].map((index) => (
          <div key={index} className="h-16 animate-pulse rounded-lg bg-slate-100" />
        ))}
      </div>
      <div className="mt-4 h-[260px] animate-pulse rounded-lg bg-slate-100" />
    </div>
  )
}
