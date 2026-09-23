/**
 * Loading / empty / error panel.
 *
 * One component so all three states share the same shape and spacing, and no
 * screen quietly forgets to handle one of them.
 */
const TONES = {
  info: 'border-white/8 bg-surface text-muted',
  empty: 'border-white/8 bg-white/4 text-muted',
  error: 'border-alert/25 bg-alert/8 text-alert',
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
          className="mt-4 rounded-lg border border-white/12 bg-white/5 px-4 py-2 text-sm font-medium text-muted transition hover:bg-white/8"
        >
          {actionLabel}
        </button>
      )}
    </div>
  )
}

export function ChartSkeleton({ height = 260 }) {
  return (
    <div className="pulse-lift rounded-2xl border border-white/8 bg-gradient-to-b from-raised to-surface p-4 shadow-[0_12px_30px_rgb(0_0_0/0.25)] sm:p-5">
      <div className="h-4 w-36 animate-pulse rounded bg-white/8" />
      <div className="mt-1 h-3 w-48 animate-pulse rounded bg-white/5" />
      <div className="mt-4 animate-pulse rounded-lg bg-white/5" style={{ height }} />
    </div>
  )
}
