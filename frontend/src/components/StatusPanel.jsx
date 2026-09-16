/**
 * Loading / empty / error panel.
 *
 * One component so all three states share the same shape and spacing, and no
 * screen quietly forgets to handle one of them.
 */
const TONES = {
  info: 'border-slate-200 bg-white text-slate-600',
  empty: 'border-slate-200 bg-slate-50 text-slate-600',
  error: 'border-red-200 bg-red-50 text-red-700',
}

export function StatusPanel({ tone = 'info', title, message, actionLabel, onAction }) {
  return (
    <div
      role={tone === 'error' ? 'alert' : 'status'}
      className={`rounded-xl border p-6 text-center ${TONES[tone] ?? TONES.info}`}
    >
      {title && <p className="text-sm font-semibold">{title}</p>}
      {message && <p className="mx-auto mt-1 max-w-prose text-sm">{message}</p>}
      {actionLabel && onAction && (
        <button
          type="button"
          onClick={onAction}
          className="mt-4 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-teal-600"
        >
          {actionLabel}
        </button>
      )}
    </div>
  )
}

export function ChartSkeleton({ height = 260 }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5">
      <div className="h-4 w-36 animate-pulse rounded bg-slate-200" />
      <div className="mt-1 h-3 w-48 animate-pulse rounded bg-slate-100" />
      <div className="mt-4 animate-pulse rounded-lg bg-slate-100" style={{ height }} />
    </div>
  )
}
