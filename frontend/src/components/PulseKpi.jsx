/**
 * A headline metric in the KPI row.
 *
 * `hint` is a second real figure from the same payload, not a fabricated
 * period-on-period delta: GET /api/dashboard measures growth for revenue only,
 * so no other card claims a movement it cannot support.
 */
export function PulseKpi({ label, value, hint, accent = false, delay = 0 }) {
  return (
    <div
      className={[
        'pulse-lift pulse-rise rounded-2xl border p-5 shadow-[0_12px_30px_rgb(0_0_0/0.25)] sm:p-6',
        accent
          ? 'border-sage/30 bg-gradient-to-b from-[#16201a] to-raised'
          : 'border-white/8 bg-gradient-to-b from-raised to-surface',
      ].join(' ')}
      style={{ animationDelay: `${delay}ms` }}
    >
      <p className="text-xs font-medium uppercase tracking-[0.12em] text-faint">{label}</p>
      <p className="mt-2.5 text-[1.75rem] font-semibold leading-none tracking-tight tabular-nums text-cream sm:text-3xl">
        {value}
      </p>
      {/* Muted, not green: these are supporting figures from the same payload,
          not measured improvements. Only revenue has a comparison behind it. */}
      {hint && <p className="mt-2.5 text-xs text-muted">{hint}</p>}
    </div>
  )
}

export function PulseKpiSkeleton() {
  return (
    <div className="rounded-2xl border border-white/8 bg-surface p-5 sm:p-6">
      <div className="h-3 w-20 animate-pulse rounded bg-white/8" />
      <div className="mt-3 h-8 w-28 animate-pulse rounded bg-white/8" />
      <div className="mt-3 h-3 w-24 animate-pulse rounded bg-white/5" />
    </div>
  )
}
