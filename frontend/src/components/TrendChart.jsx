/**
 * Reusable daily-trend chart.
 *
 * One component drives every chart on the dashboard so axes, tooltips, grid and
 * spacing stay identical between them. Each series declares its own mark type,
 * which is what lets revenue (area) and gross profit (line) share one plot.
 */
import {
  Area,
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { usePrefersReducedMotion } from '../hooks/usePrefersReducedMotion'
import { formatDate } from '../utils/format'

const AXIS_COLOR = '#7d8c83'
const GRID_COLOR = '#ffffff14'

function ChartTooltip({ active, payload, label, valueFormatter }) {
  if (!active || !payload?.length) return null

  return (
    <div className="rounded-lg border border-white/15 bg-surface px-3 py-2 shadow-xl">
      <p className="text-xs font-medium text-faint">{formatDate(label, { withYear: true })}</p>
      <ul className="mt-1 space-y-0.5">
        {payload.map((entry) => (
          <li key={entry.dataKey} className="flex items-center gap-2 text-sm">
            <span
              aria-hidden="true"
              className="inline-block h-2 w-2 shrink-0 rounded-full"
              style={{ backgroundColor: entry.color }}
            />
            <span className="text-muted">{entry.name}</span>
            <span className="ml-auto font-medium tabular-nums text-cream">
              {valueFormatter(entry.value)}
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}

export function TrendChart({
  title,
  subtitle,
  data,
  series,
  valueFormatter,
  axisFormatter,
  height = 260,
}) {
  const showLegend = series.length > 1
  const prefersReducedMotion = usePrefersReducedMotion()

  return (
    <section className="pulse-lift rounded-2xl border border-white/8 bg-gradient-to-b from-raised to-surface p-4 shadow-[0_12px_30px_rgb(0_0_0/0.25)] sm:p-5">
      <header className="mb-4">
        <h3 className="text-sm font-semibold text-cream">{title}</h3>
        {subtitle && <p className="mt-0.5 text-xs text-faint">{subtitle}</p>}
      </header>

      <div style={{ width: '100%', height }}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid stroke={GRID_COLOR} strokeDasharray="3 3" vertical={false} />
            <XAxis
              dataKey="date"
              tickFormatter={(iso) => formatDate(iso)}
              tick={{ fontSize: 11, fill: AXIS_COLOR }}
              tickLine={false}
              axisLine={{ stroke: GRID_COLOR }}
              // Long ranges hold ~180 points; a minimum gap keeps the axis
              // readable instead of overlapping every label into a smear.
              minTickGap={36}
            />
            <YAxis
              tickFormatter={axisFormatter}
              tick={{ fontSize: 11, fill: AXIS_COLOR }}
              tickLine={false}
              axisLine={false}
              width={58}
            />
            <Tooltip
              content={<ChartTooltip valueFormatter={valueFormatter} />}
              cursor={{ stroke: AXIS_COLOR, strokeDasharray: '3 3' }}
            />
            {showLegend && (
              <Legend
                verticalAlign="top"
                align="right"
                height={28}
                iconType="circle"
                iconSize={8}
                wrapperStyle={{ fontSize: 12, color: '#9baaa0' }}
              />
            )}

            {series.map((item) => {
              // `key` is passed explicitly rather than spread: React rejects a
              // key that arrives inside a spread props object.
              const common = {
                dataKey: item.key,
                name: item.label,
                stroke: item.color,
                isAnimationActive: !prefersReducedMotion,
                animationDuration: 900,
              }

              if (item.type === 'area') {
                return (
                  <Area
                    key={item.key}
                    {...common}
                    type="monotone"
                    fill={item.color}
                    fillOpacity={0.18}
                    strokeWidth={2}
                    stackId={item.stackId}
                    dot={false}
                  />
                )
              }
              if (item.type === 'bar') {
                return (
                  <Bar
                    key={item.key}
                    {...common}
                    fill={item.color}
                    stackId={item.stackId}
                    radius={[2, 2, 0, 0]}
                  />
                )
              }
              return <Line key={item.key} {...common} type="monotone" strokeWidth={2} dot={false} />
            })}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </section>
  )
}
