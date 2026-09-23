/**
 * AI business insights (Stage 4's engine, integrated in Stage 7).
 *
 * Renders the findings from GET /api/insights. Each one states what changed,
 * how big it was, where, and — under "Why flagged" — the documented threshold
 * that made it noteworthy.
 *
 * The severity counts act as the at-a-glance signal. No composite health score
 * is shown: the backend does not compute one, and inventing a number in the
 * browser would put business logic in a component.
 */
import { useState } from 'react'

const SEVERITY_STYLES = {
  HIGH: 'bg-alert/12 text-alert ring-alert/30',
  MEDIUM: 'bg-gold/12 text-gold ring-gold/30',
  LOW: 'bg-white/8 text-muted ring-white/12',
}

const SEVERITY_ORDER = ['HIGH', 'MEDIUM', 'LOW']

// Enough to show the picture without turning the page into a wall of findings.
const INITIAL_VISIBLE = 6

const BASIS_LABEL = {
  previous_period: 'compared with the previous period',
  within_period: 'comparing the second half of the period with the first',
}

function FindingCard({ finding }) {
  const badge = SEVERITY_STYLES[finding.severity] ?? SEVERITY_STYLES.LOW

  return (
    <li className="rounded-xl border border-white/8 bg-white/3 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span
          className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${badge}`}
        >
          {finding.severity}
        </span>
        <span className="text-xs text-faint">{finding.category}</span>
        {finding.scope && finding.scope !== 'merchant' && (
          <span className="text-xs text-faint">· {finding.scope}</span>
        )}
      </div>

      <h4 className="mt-2 text-sm font-semibold text-cream">{finding.title}</h4>
      <p className="mt-1 text-sm text-muted">{finding.description}</p>
      <p className="mt-2 border-t border-white/8 pt-2 text-xs text-faint">
        <span className="font-medium text-muted">Why flagged: </span>
        {finding.reason}
      </p>
    </li>
  )
}

export function InsightsPanel({ insights }) {
  const [expanded, setExpanded] = useState(false)

  if (!insights) return null

  const findings = insights.findings ?? []
  const visible = expanded ? findings : findings.slice(0, INITIAL_VISIBLE)
  const counts = insights.severity_counts ?? {}
  const basis = BASIS_LABEL[insights.comparison_basis]

  return (
    <section className="pulse-lift rounded-2xl border border-white/8 bg-gradient-to-b from-raised to-surface p-4 shadow-[0_12px_30px_rgb(0_0_0/0.25)] sm:p-5">
      <header className="mb-4 flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold text-cream">AI insights</h3>
          <p className="mt-0.5 text-xs text-faint">
            What changed this period{basis ? `, ${basis}` : ''}
          </p>
        </div>

        {findings.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {SEVERITY_ORDER.filter((severity) => counts[severity] > 0).map((severity) => (
              <span
                key={severity}
                className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${SEVERITY_STYLES[severity]}`}
              >
                {counts[severity]} {severity.toLowerCase()}
              </span>
            ))}
          </div>
        )}
      </header>

      {findings.length === 0 ? (
        <p className="rounded-xl bg-white/4 p-4 text-sm text-muted">
          Nothing in this period moved far enough to flag. Revenue, orders, customers
          and stock are all within their normal range.
        </p>
      ) : (
        <>
          <ul className="space-y-3">
            {visible.map((finding) => (
              <FindingCard key={finding.id} finding={finding} />
            ))}
          </ul>

          {findings.length > INITIAL_VISIBLE && (
            <button
              type="button"
              onClick={() => setExpanded((current) => !current)}
              className="mt-3 rounded-lg border border-white/12 bg-white/5 px-3 py-1.5 text-sm font-medium text-muted transition hover:bg-white/8"
            >
              {expanded
                ? 'Show fewer'
                : `Show all ${findings.length} findings`}
            </button>
          )}
        </>
      )}

      {insights.notes?.length > 0 && (
        <ul className="mt-4 space-y-1 border-t border-white/8 pt-3">
          {insights.notes.map((note) => (
            <li key={note} className="text-xs text-faint">
              {note}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

export function InsightsSkeleton() {
  return (
    <div className="pulse-lift rounded-2xl border border-white/8 bg-gradient-to-b from-raised to-surface p-4 shadow-[0_12px_30px_rgb(0_0_0/0.25)] sm:p-5">
      <div className="h-4 w-24 animate-pulse rounded bg-white/8" />
      <div className="mt-1 h-3 w-52 animate-pulse rounded bg-white/5" />
      <div className="mt-4 space-y-3">
        {[0, 1, 2].map((index) => (
          <div key={index} className="h-28 animate-pulse rounded-lg bg-white/5" />
        ))}
      </div>
    </div>
  )
}
