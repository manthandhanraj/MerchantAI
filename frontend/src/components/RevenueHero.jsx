/**
 * The headline revenue card.
 *
 * Every figure comes from GET /api/dashboard. The growth chip is hidden when
 * the period is too short for the comparison behind it to mean anything — the
 * same guard the KPI row has always applied, kept rather than dropped for the
 * sake of a nicer-looking card.
 */
import { Area, AreaChart, ResponsiveContainer, Tooltip } from 'recharts'

import { usePrefersReducedMotion } from '../hooks/usePrefersReducedMotion'
import {
  formatCurrency,
  formatDate,
  formatDateRange,
  formatNumber,
  formatPercent,
  formatSignedPercent,
} from '../utils/format'

function HeroTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-lg border border-white/15 bg-surface px-3 py-2 shadow-xl">
      <p className="text-xs text-faint">{formatDate(label, { withYear: true })}</p>
      <p className="mt-0.5 text-sm font-medium tabular-nums text-cream">
        {formatCurrency(payload[0].value)}
      </p>
    </div>
  )
}

export function RevenueHero({ summary, daily, growth, growthLabel }) {
  const prefersReducedMotion = usePrefersReducedMotion()
  const hasGrowth = typeof growth === 'number' && Number.isFinite(growth)
  const isUp = hasGrowth && growth > 0
  const isDown = hasGrowth && growth < 0

  return (
    <section
      aria-labelledby="revenue-hero-heading"
      className="pulse-lift pulse-rise relative overflow-hidden rounded-3xl border border-white/8 bg-gradient-to-br from-forest-lit via-forest to-surface p-6 shadow-[0_20px_50px_rgb(0_0_0/0.35)] sm:p-7"
    >
      {/* Champagne corner light. Decorative, and it never moves. */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -right-24 -top-24 h-64 w-64 rounded-full bg-gold/10 blur-3xl"
      />

      <div className="relative">
        <h2
          id="revenue-hero-heading"
          className="text-xs font-semibold uppercase tracking-[0.16em] text-sage/80"
        >
          This period&apos;s revenue
        </h2>

        <p className="mt-3 text-4xl font-semibold tracking-tight tabular-nums text-cream sm:text-5xl">
          {formatCurrency(summary.total_revenue)}
        </p>

        <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1.5">
          {hasGrowth && (
            <span
              className={[
                'inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium tabular-nums',
                isUp ? 'bg-sage/12 text-sage' : '',
                isDown ? 'bg-alert/12 text-alert' : '',
                !isUp && !isDown ? 'bg-white/8 text-muted' : '',
              ].join(' ')}
            >
              <span aria-hidden="true">{isUp ? '↑' : isDown ? '↓' : '→'}</span>
              {formatSignedPercent(growth)}
              <span className="font-normal opacity-80">{growthLabel}</span>
            </span>
          )}
          <span className="text-xs text-faint">
            {formatDateRange(summary.period_start, summary.period_end)} ·{' '}
            {formatNumber(summary.days)} days
          </span>
        </div>

        <div className="-mx-1 mt-5 h-[150px] sm:h-[180px]">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={daily} margin={{ top: 4, right: 4, bottom: 0, left: 4 }}>
              <defs>
                <linearGradient id="hero-revenue-fill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#b8e49d" stopOpacity={0.34} />
                  <stop offset="100%" stopColor="#b8e49d" stopOpacity={0} />
                </linearGradient>
              </defs>
              <Tooltip
                content={<HeroTooltip />}
                cursor={{ stroke: '#b8e49d', strokeOpacity: 0.35, strokeDasharray: '3 3' }}
              />
              <Area
                dataKey="revenue"
                name="Revenue"
                type="monotone"
                stroke="#b8e49d"
                strokeWidth={2}
                fill="url(#hero-revenue-fill)"
                dot={false}
                isAnimationActive={!prefersReducedMotion}
                animationDuration={1100}
                animationEasing="ease-out"
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        {/* Gross profit and visits keep their place on the page now that the
            headline row shows three metrics instead of five. */}
        <dl className="mt-5 grid grid-cols-2 gap-4 border-t border-white/8 pt-4">
          <div>
            <dt className="text-xs text-faint">Gross profit</dt>
            <dd className="mt-1 text-sm font-medium tabular-nums text-cream">
              {formatCurrency(summary.total_profit)}
              <span className="ml-1.5 font-normal text-muted">
                {formatPercent(summary.profit_margin)} margin
              </span>
            </dd>
          </div>
          <div>
            <dt className="text-xs text-faint">Customer visits</dt>
            <dd className="mt-1 text-sm font-medium tabular-nums text-cream">
              {formatNumber(summary.total_customers)}
              <span className="ml-1.5 font-normal text-muted">
                {formatCurrency(summary.revenue_per_customer)} each
              </span>
            </dd>
          </div>
        </dl>
      </div>
    </section>
  )
}
