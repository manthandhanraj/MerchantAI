/**
 * A single headline metric.
 *
 * `delta` is a fraction (0.31 = +31%). Positive is green, negative is red, and
 * it is only rendered when a caller passes a label with it — an unexplained
 * arrow on a dashboard is worse than no arrow.
 */
import { formatSignedPercent } from '../utils/format'

export function KpiCard({ label, value, hint, delta, deltaLabel }) {
  const hasDelta = typeof delta === 'number' && Number.isFinite(delta) && deltaLabel
  const isPositive = hasDelta && delta > 0
  const isNegative = hasDelta && delta < 0

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>

      <p className="mt-2 text-2xl font-semibold tabular-nums text-slate-900 sm:text-[1.75rem]">
        {value}
      </p>

      {(hint || hasDelta) && (
        <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1">
          {hasDelta && (
            <span
              className={[
                'inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium tabular-nums',
                isPositive ? 'bg-emerald-50 text-emerald-700' : '',
                isNegative ? 'bg-red-50 text-red-700' : '',
                !isPositive && !isNegative ? 'bg-slate-100 text-slate-600' : '',
              ].join(' ')}
            >
              {isPositive ? '▲' : isNegative ? '▼' : '■'} {formatSignedPercent(delta)}
            </span>
          )}
          {hint && <span className="text-xs text-slate-500">{hint}</span>}
          {hasDelta && <span className="text-xs text-slate-500">{deltaLabel}</span>}
        </div>
      )}
    </div>
  )
}

export function KpiCardSkeleton() {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5">
      <div className="h-3 w-20 animate-pulse rounded bg-slate-200" />
      <div className="mt-3 h-7 w-28 animate-pulse rounded bg-slate-200" />
      <div className="mt-3 h-3 w-16 animate-pulse rounded bg-slate-100" />
    </div>
  )
}
