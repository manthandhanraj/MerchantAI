/**
 * Prioritised action plan (Stage 5).
 *
 * Renders the High / Medium / Low buckets from GET /api/action-plan. Every item
 * shows the action and, beneath it, the finding that justifies it — so the
 * merchant can see why they are being told to do something.
 */
const PRIORITY_STYLES = {
  High: 'bg-red-50 text-red-700 ring-red-200',
  Medium: 'bg-amber-50 text-amber-800 ring-amber-200',
  Low: 'bg-slate-100 text-slate-600 ring-slate-200',
}

const BUCKETS = [
  { key: 'high', label: 'High priority' },
  { key: 'medium', label: 'Medium priority' },
  { key: 'low', label: 'Low priority' },
]

function ActionCard({ item }) {
  const badge = PRIORITY_STYLES[item.priority] ?? PRIORITY_STYLES.Low

  return (
    <li className="rounded-lg border border-slate-200 bg-white p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span
          className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${badge}`}
        >
          {item.priority}
        </span>
        <span className="text-xs text-slate-500">{item.category}</span>
        {item.scope && item.scope !== 'merchant' && (
          <span className="text-xs text-slate-500">· {item.scope}</span>
        )}
      </div>

      <h4 className="mt-2 text-sm font-semibold text-slate-900">
        {item.rank}. {item.title}
      </h4>
      <p className="mt-1 text-sm text-slate-600">{item.action}</p>
      <p className="mt-2 border-t border-slate-100 pt-2 text-xs text-slate-500">
        <span className="font-medium text-slate-600">Why: </span>
        {item.reason}
      </p>
    </li>
  )
}

export function ActionPlanPanel({ plan }) {
  const buckets = BUCKETS.map((bucket) => ({ ...bucket, items: plan?.[bucket.key] ?? [] })).filter(
    (bucket) => bucket.items.length > 0,
  )

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5">
      <header className="mb-4">
        <h3 className="text-sm font-semibold text-slate-900">Action plan</h3>
        <p className="mt-0.5 text-xs text-slate-500">
          What to focus on for this period, most urgent first
        </p>
      </header>

      {buckets.length === 0 ? (
        <p className="rounded-lg bg-slate-50 p-4 text-sm text-slate-600">
          Nothing needs attention in this period. Revenue, orders and stock are all
          within their normal range.
        </p>
      ) : (
        <div className="space-y-5">
          {buckets.map((bucket) => (
            <div key={bucket.key}>
              <h4 className="text-xs font-medium uppercase tracking-wide text-slate-500">
                {bucket.label}
              </h4>
              <ul className="mt-2 space-y-3">
                {bucket.items.map((item) => (
                  <ActionCard key={item.source_finding} item={item} />
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}

      {plan?.notes?.length > 0 && (
        <ul className="mt-4 space-y-1 border-t border-slate-100 pt-3">
          {plan.notes.map((note) => (
            <li key={note} className="text-xs text-slate-500">
              {note}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

export function ActionPlanSkeleton() {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5">
      <div className="h-4 w-24 animate-pulse rounded bg-slate-200" />
      <div className="mt-1 h-3 w-56 animate-pulse rounded bg-slate-100" />
      <div className="mt-4 space-y-3">
        {[0, 1, 2].map((index) => (
          <div key={index} className="h-24 animate-pulse rounded-lg bg-slate-100" />
        ))}
      </div>
    </div>
  )
}
