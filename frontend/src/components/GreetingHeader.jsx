/**
 * The page's opening line.
 *
 * The greeting follows the reader's own clock — it is a salutation, not an
 * analytical figure, so it does not touch the dataset's fixed window. The
 * sentence after it does come from the data: it reflects the measured revenue
 * movement rather than always claiming things look good.
 */
import { parseIsoDate } from '../utils/format'

const MONTHS = [
  'JANUARY', 'FEBRUARY', 'MARCH', 'APRIL', 'MAY', 'JUNE',
  'JULY', 'AUGUST', 'SEPTEMBER', 'OCTOBER', 'NOVEMBER', 'DECEMBER',
]

function greetingForHour(hour) {
  if (hour < 12) return 'Good morning.'
  if (hour < 17) return 'Good afternoon.'
  return 'Good evening.'
}

/**
 * Headline and supporting line, chosen by how the period actually moved.
 *
 * `growth` is the last seven days against the seven before them, so the wording
 * speaks about the past week rather than the business overall. A thirty-day
 * period can be up while its final week is down, and the insights below say so
 * — the greeting must not contradict them.
 */
export function toneFor(growth) {
  if (typeof growth !== 'number' || !Number.isFinite(growth)) {
    return {
      headline: 'Here is where your business stands today.',
      support: 'Clear numbers, straight from your own sales. Your best next move is ready.',
    }
  }
  if (growth > 0.02) {
    return {
      headline: 'Your week looks beautiful today.',
      support: 'Clear numbers. Strong momentum. Your best next move is ready.',
    }
  }
  if (growth < -0.02) {
    return {
      headline: 'Your last week eased off a little.',
      support: 'Clear numbers, nothing hidden. Your best next move is ready below.',
    }
  }
  return {
    headline: 'Your week is holding steady.',
    support: 'Clear numbers. Level momentum. Your best next move is ready.',
  }
}

export function GreetingHeader({ merchantId, periodEnd, growth, children }) {
  const parsed = parseIsoDate(periodEnd)
  const month = parsed ? MONTHS[parsed.getMonth()] : null
  const tone = toneFor(growth)

  return (
    <div className="flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between lg:gap-10">
      <div className="min-w-0 max-w-2xl">
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-gold">
          {[merchantId, month].filter(Boolean).join(' · ') || 'Loading'}
        </p>
        <h1 className="mt-3 text-2xl font-semibold leading-tight tracking-tight text-cream sm:text-3xl lg:text-[2.1rem]">
          {greetingForHour(new Date().getHours())}{' '}
          <span className="text-muted">{tone.headline}</span>
        </h1>
        <p className="mt-3 text-sm leading-relaxed text-muted sm:text-[0.95rem]">{tone.support}</p>
      </div>

      {children && <div className="shrink-0 lg:pt-1">{children}</div>}
    </div>
  )
}
