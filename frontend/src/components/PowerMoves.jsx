/**
 * The short list: what to do first.
 *
 * These are the top-ranked items from GET /api/action-plan, in the order the
 * backend ranked them. The full plan, with every bucket and its justification,
 * stays further down the page.
 */
const PRIORITY_TONE = {
  High: 'text-alert',
  Medium: 'text-gold',
  Low: 'text-muted',
}

export function PowerMoves({ items, loading, error, onOpenPlan }) {
  return (
    <section
      aria-labelledby="power-moves-heading"
      className="pulse-lift flex flex-col rounded-2xl border border-white/8 bg-gradient-to-b from-raised to-surface p-5 shadow-[0_12px_30px_rgb(0_0_0/0.25)] sm:p-6"
    >
      <header className="mb-4">
        <h3 id="power-moves-heading" className="text-sm font-semibold text-cream">
          Today&apos;s power moves
        </h3>
        <p className="mt-0.5 text-xs text-faint">Your highest-priority actions, ranked</p>
      </header>

      {loading && (
        <ul className="space-y-4" role="status" aria-label="Loading your power moves">
          {[0, 1, 2].map((index) => (
            <li key={index} className="flex gap-3">
              <div className="mt-0.5 h-6 w-6 shrink-0 animate-pulse rounded-full bg-white/8" />
              <div className="min-w-0 flex-1 space-y-2">
                <div className="h-3.5 w-4/5 animate-pulse rounded bg-white/8" />
                <div className="h-3 w-2/5 animate-pulse rounded bg-white/5" />
              </div>
            </li>
          ))}
        </ul>
      )}

      {!loading && error && <p className="text-sm text-alert">{error}</p>}

      {!loading && !error && items.length === 0 && (
        <p className="rounded-xl bg-white/4 p-4 text-sm text-muted">
          Nothing needs attention in this period. Revenue, orders and stock are all
          within their normal range.
        </p>
      )}

      {!loading && !error && items.length > 0 && (
        <>
          <ol className="space-y-4">
            {items.map((item) => (
              <li key={item.source_finding} className="flex gap-3">
                <span
                  aria-hidden="true"
                  className="mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-full border border-sage/35 bg-sage/12 text-[0.7rem] font-semibold text-sage"
                >
                  ✓
                </span>
                <div className="min-w-0">
                  <p className="text-sm font-medium leading-snug text-cream">{item.title}</p>
                  <p className="mt-1 text-xs text-faint">
                    <span className={PRIORITY_TONE[item.priority] ?? PRIORITY_TONE.Low}>
                      {item.priority} priority
                    </span>
                    <span className="mx-1.5">·</span>
                    {item.category}
                  </p>
                </div>
              </li>
            ))}
          </ol>

          <button
            type="button"
            onClick={onOpenPlan}
            className="mt-5 w-fit rounded-full border border-white/12 px-4 py-2 text-xs font-medium text-muted transition hover:border-sage/40 hover:text-sage"
          >
            See the full plan
          </button>
        </>
      )}
    </section>
  )
}
