/**
 * Product, category and inventory panels for the private dashboard.
 *
 * All three render values the backend computed and stored. Nothing is derived
 * here beyond choosing which rows to show, and a metric the backend could not
 * compute is shown as unknown rather than as a number.
 */
import { formatCurrency, formatNumber, formatPercent } from '../utils/format'

const CARD =
  'pulse-lift rounded-2xl border border-white/8 bg-gradient-to-b from-raised to-surface p-5 shadow-[0_12px_30px_rgb(0_0_0/0.25)] sm:p-6'

function Th({ children, align = 'left' }) {
  return (
    <th className={`px-2 py-2 text-${align} text-xs font-medium text-faint`}>{children}</th>
  )
}

function Td({ children, align = 'left', className = '' }) {
  return <td className={`px-2 py-2.5 text-${align} text-sm ${className}`}>{children}</td>
}

export function ProductPerformance({ products = [], limit = 8 }) {
  if (products.length === 0) return null
  const rows = products.slice(0, limit)

  return (
    <section aria-labelledby="products-heading" className={CARD}>
      <header className="mb-4">
        <h3 id="products-heading" className="text-sm font-semibold text-cream">
          Product performance
        </h3>
        <p className="mt-0.5 text-xs text-faint">
          Ranked by revenue over the analysed period
        </p>
      </header>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[520px]">
          <thead>
            <tr className="border-b border-white/10">
              <Th>Product</Th>
              <Th align="right">Revenue</Th>
              <Th align="right">Units</Th>
              <Th align="right">Share</Th>
              <Th align="right">Margin</Th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.product} className="border-b border-white/5">
                <Td className="text-cream">{row.product}</Td>
                <Td align="right" className="tabular-nums text-cream">
                  {formatCurrency(row.revenue)}
                </Td>
                <Td align="right" className="tabular-nums text-muted">
                  {formatNumber(row.units_sold)}
                </Td>
                <Td align="right" className="tabular-nums text-muted">
                  {formatPercent(row.revenue_share)}
                </Td>
                <Td align="right" className="tabular-nums text-muted">
                  {formatPercent(row.profit_margin)}
                </Td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {products.length > limit && (
        <p className="mt-3 text-xs text-faint">
          Showing the top {limit} of {formatNumber(products.length)} products.
        </p>
      )}
    </section>
  )
}

export function CategoryPerformance({ categories = [] }) {
  if (categories.length === 0) return null

  return (
    <section aria-labelledby="categories-heading" className={CARD}>
      <header className="mb-4">
        <h3 id="categories-heading" className="text-sm font-semibold text-cream">
          Category performance
        </h3>
        <p className="mt-0.5 text-xs text-faint">Where the revenue is concentrated</p>
      </header>

      <ul className="space-y-3">
        {categories.map((row) => {
          const share = Number(row.revenue_share)
          const width = Number.isFinite(share) ? Math.max(share * 100, 1.5) : 0
          return (
            <li key={row.category}>
              <div className="flex items-baseline justify-between gap-3">
                <span className="truncate text-sm text-cream">{row.category}</span>
                <span className="shrink-0 text-sm tabular-nums text-muted">
                  {formatCurrency(row.revenue)}
                  <span className="ml-2 text-xs text-faint">{formatPercent(row.revenue_share)}</span>
                </span>
              </div>
              <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-white/8">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-sage/50 to-sage"
                  style={{ width: `${width}%` }}
                />
              </div>
            </li>
          )
        })}
      </ul>
    </section>
  )
}

const STATUS_TONE = {
  critical: 'text-alert',
  low: 'text-gold',
  healthy: 'text-sage',
}

export function InventoryAlerts({ inventory = [] }) {
  const risky = inventory.filter((row) =>
    ['critical', 'low'].includes(String(row.stock_status).toLowerCase()),
  )

  return (
    <section aria-labelledby="inventory-heading" className={CARD}>
      <header className="mb-4">
        <h3 id="inventory-heading" className="text-sm font-semibold text-cream">
          Inventory alerts
        </h3>
        <p className="mt-0.5 text-xs text-faint">
          Days of cover from your recent selling rate
        </p>
      </header>

      {risky.length === 0 ? (
        <p className="rounded-xl bg-white/4 p-4 text-sm text-muted">
          No product is close to running out at its current selling rate.
        </p>
      ) : (
        <ul className="space-y-3">
          {risky.slice(0, 8).map((row) => {
            const cover = Number(row.days_of_inventory_cover)
            const status = String(row.stock_status).toLowerCase()
            return (
              <li key={row.product} className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                <span className="text-sm text-cream">{row.product}</span>
                <span className={`text-xs font-medium ${STATUS_TONE[status] ?? 'text-muted'}`}>
                  {status}
                </span>
                <span className="ml-auto text-sm tabular-nums text-muted">
                  {Number.isFinite(cover) ? `${cover.toFixed(1)} days` : 'cover unknown'}
                  <span className="ml-2 text-xs text-faint">
                    {formatNumber(row.inventory)} units left
                  </span>
                </span>
              </li>
            )
          })}
        </ul>
      )}

      <p className="mt-4 text-xs leading-relaxed text-faint">
        Stock is inferred from the sales history you uploaded, not read from a live inventory
        feed. A product with no recent sales has no meaningful cover, and is reported as unknown
        rather than as unlimited.
      </p>
    </section>
  )
}
