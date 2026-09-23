/**
 * The AI growth coach.
 *
 * It restates the single highest-priority item from GET /api/action-plan — the
 * same engine that fills the plan further down the page, so the headline here
 * can never disagree with it. Nothing is written in the browser.
 */
export function AiCoachCard({ item, loading, error, onOpenPlan }) {
  return (
    <section
      aria-labelledby="ai-coach-heading"
      className="pulse-lift pulse-rise relative flex flex-col overflow-hidden rounded-3xl border border-gold/25 bg-gradient-to-b from-[#1a1611] to-cocoa p-6 shadow-[0_20px_50px_rgb(0_0_0/0.4)] sm:p-7"
    >
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -left-16 -top-20 h-52 w-52 rounded-full bg-gold/10 blur-3xl"
      />

      <div className="relative flex min-h-0 flex-1 flex-col">
        <h2
          id="ai-coach-heading"
          className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.16em] text-gold"
        >
          <span aria-hidden="true" className="pulse-sparkle text-sm leading-none">
            ✦
          </span>
          AI growth coach
        </h2>

        {loading && (
          <div className="mt-5 space-y-3" role="status" aria-label="Loading your top move">
            <div className="h-5 w-full animate-pulse rounded bg-white/8" />
            <div className="h-5 w-4/5 animate-pulse rounded bg-white/8" />
            <div className="mt-4 h-3 w-full animate-pulse rounded bg-white/5" />
            <div className="h-3 w-3/4 animate-pulse rounded bg-white/5" />
          </div>
        )}

        {!loading && error && (
          <p className="mt-5 text-sm leading-relaxed text-alert">
            The growth coach could not load its suggestion. {error}
          </p>
        )}

        {!loading && !error && !item && (
          <p className="mt-5 text-base leading-snug text-cream">
            Nothing needs your attention in this period. Revenue, orders and stock are
            all within their normal range.
          </p>
        )}

        {!loading && !error && item && (
          <>
            <h3 className="mt-5 text-xl font-semibold leading-snug tracking-tight text-cream sm:text-[1.4rem]">
              {item.title}
            </h3>
            <p className="mt-3 text-sm leading-relaxed text-muted">{item.action}</p>
            <p className="mt-3 text-xs leading-relaxed text-faint">
              <span className="font-medium text-muted">Why: </span>
              {item.reason}
            </p>

            <button
              type="button"
              onClick={onOpenPlan}
              className="focus-gold mt-6 inline-flex w-fit items-center gap-2 rounded-full bg-gold px-5 py-2.5 text-sm font-semibold text-[#221a0c] transition hover:bg-[#f0cd8d]"
            >
              Open my growth plan
              <span aria-hidden="true">→</span>
            </button>
          </>
        )}
      </div>
    </section>
  )
}
