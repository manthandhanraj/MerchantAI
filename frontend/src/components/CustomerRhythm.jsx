/**
 * Which days of the week the business actually earns on.
 *
 * The bars average the daily revenue already returned by GET /api/dashboard —
 * see utils/rhythm.js. The highlighted day is whichever one measures strongest,
 * not a fixed weekend assumption.
 */
import { formatCurrency, formatCurrencyCompact } from '../utils/format'
import { weekdayRhythm } from '../utils/rhythm'

// A floor so a genuinely quiet day still reads as a bar rather than nothing.
const MIN_BAR_SHARE = 0.06

export function CustomerRhythm({ daily }) {
  const rhythm = weekdayRhythm(daily, 'revenue')
  const hasAny = rhythm.some((entry) => entry.days > 0)
  const peak = rhythm.find((entry) => entry.isPeak)

  return (
    <section
      id="customers"
      aria-labelledby="rhythm-heading"
      className="pulse-lift scroll-mt-28 rounded-2xl border border-white/8 bg-gradient-to-b from-raised to-surface p-5 shadow-[0_12px_30px_rgb(0_0_0/0.25)] sm:p-6"
    >
      <header className="mb-5 flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h3 id="rhythm-heading" className="text-sm font-semibold text-cream">
            Your customer rhythm
          </h3>
          <p className="mt-0.5 text-xs text-faint">
            Average revenue by day of the week, across this period
          </p>
        </div>
        {hasAny && peak && peak.value > 0 && (
          <span className="rounded-full bg-gold/12 px-2.5 py-1 text-xs font-medium text-gold">
            {peak.label} is your strongest day
          </span>
        )}
      </header>

      {!hasAny ? (
        <p className="rounded-xl bg-white/4 p-4 text-sm text-muted">
          There are no daily totals in this period to compare weekdays with.
        </p>
      ) : (
        <ul className="flex h-44 items-end gap-2 sm:gap-3">
          {rhythm.map((entry, index) => {
            const height = entry.days === 0 ? 0 : Math.max(entry.share, MIN_BAR_SHARE) * 100
            return (
              <li key={entry.label} className="flex h-full min-w-0 flex-1 flex-col justify-end">
                <div className="flex h-full items-end">
                  <div
                    className={[
                      'pulse-bar w-full rounded-t-lg',
                      entry.isPeak
                        ? 'bg-gradient-to-t from-gold/45 to-gold'
                        : 'bg-gradient-to-t from-sage/12 to-sage/45',
                    ].join(' ')}
                    style={{
                      height: `${height}%`,
                      animationDelay: `${index * 70}ms`,
                    }}
                    title={
                      entry.days === 0
                        ? `${entry.label}: no data`
                        : `${entry.label}: ${formatCurrency(entry.value)} average across ${
                            entry.days
                          } day${entry.days === 1 ? '' : 's'}`
                    }
                  />
                </div>
                <p
                  className={`mt-2.5 truncate text-center text-xs ${
                    entry.isPeak ? 'font-medium text-gold' : 'text-faint'
                  }`}
                >
                  {entry.label}
                </p>
                <p className="truncate text-center text-[0.65rem] tabular-nums text-faint">
                  {entry.days === 0 ? '—' : formatCurrencyCompact(entry.value)}
                </p>
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}
