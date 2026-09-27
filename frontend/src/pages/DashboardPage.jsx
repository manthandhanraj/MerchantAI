/**
 * Merchant dashboard (Stage 3).
 *
 * Owns the data fetching and page layout. Every number rendered here comes from
 * GET /api/dashboard — nothing is computed in the browser, so the dashboard and
 * the API can never disagree.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { ActionPlanPanel, ActionPlanSkeleton } from '../components/ActionPlanPanel'
import { AiCoachCard } from '../components/AiCoachCard'
import { AssistantPanel } from '../components/AssistantPanel'
import { CustomerRhythm } from '../components/CustomerRhythm'
import { DateRangeControls, PRESETS } from '../components/DateRangeControls'
import { ForecastPanel, ForecastSkeleton } from '../components/ForecastPanel'
import { GreetingHeader } from '../components/GreetingHeader'
import { InsightsPanel, InsightsSkeleton } from '../components/InsightsPanel'
import { MerchantSelector } from '../components/MerchantSelector'
import { PanelBoundary } from '../components/PanelBoundary'
import { PowerMoves } from '../components/PowerMoves'
import { PulseKpi, PulseKpiSkeleton } from '../components/PulseKpi'
import { RevenueHero } from '../components/RevenueHero'
import { ChartSkeleton, StatusPanel } from '../components/StatusPanel'
import { TopNav } from '../components/TopNav'
import { TrendChart } from '../components/TrendChart'
import {
  askAssistant,
  getActionPlan,
  getAssistantStatus,
  getDashboard,
  getForecast,
  getInsights,
  getMerchants,
} from '../services/api'
import {
  formatCurrency,
  formatCurrencyCompact,
  formatDateRange,
  formatNumber,
  formatNumberCompact,
  formatPercent,
  maxIsoDate,
  shiftDays,
} from '../utils/format'

const DEFAULT_PRESET = '30'

// The growth figure compares the most recent 7 days with the 7 before them.
// Below 14 days that window shrinks, so the label would be wrong — hide it.
const MIN_DAYS_FOR_GROWTH = 14

// Chart colours for the dark theme. Sage carries revenue everywhere, so the
// trend chart and the hero card cannot appear to describe different things.
const COLORS = {
  revenue: '#b8e49d',
  profit: '#e5bd75',
  orders: '#7fc8d8',
  newCustomers: '#8fb9a3',
  repeatCustomers: '#b8e49d',
}

// How many action-plan items the "power moves" panel shows before the reader
// drops into the full plan.
const POWER_MOVE_COUNT = 3

/** Derive a start/end range from a merchant's own data bounds. */
function rangeForPreset(merchant, presetId) {
  if (!merchant) return { start: '', end: '' }

  const end = merchant.last_date
  const preset = PRESETS.find((item) => item.id === presetId)
  if (!preset?.days) return { start: merchant.first_date, end }

  return {
    start: maxIsoDate(merchant.first_date, shiftDays(end, -(preset.days - 1))),
    end,
  }
}

/**
 * @param {boolean} [embedded] Render without the page chrome, so the same
 *   dashboard can sit inside the authenticated workspace shell during the
 *   local demo instead of being duplicated.
 */
export default function DashboardPage({ embedded = false }) {
  const [merchants, setMerchants] = useState([])
  const [merchantsLoading, setMerchantsLoading] = useState(true)
  const [merchantsError, setMerchantsError] = useState(null)

  const [merchantId, setMerchantId] = useState('')
  const [preset, setPreset] = useState(DEFAULT_PRESET)
  const [range, setRange] = useState({ start: '', end: '' })

  const [dashboard, setDashboard] = useState(null)
  const [dashboardLoading, setDashboardLoading] = useState(false)
  const [dashboardError, setDashboardError] = useState(null)

  const [actionPlan, setActionPlan] = useState(null)
  const [actionPlanLoading, setActionPlanLoading] = useState(false)
  const [actionPlanError, setActionPlanError] = useState(null)

  const [insights, setInsights] = useState(null)
  const [insightsLoading, setInsightsLoading] = useState(false)
  const [insightsError, setInsightsError] = useState(null)

  const [forecast, setForecast] = useState(null)
  const [forecastLoading, setForecastLoading] = useState(false)
  const [forecastError, setForecastError] = useState(null)

  const [assistantStatus, setAssistantStatus] = useState(null)
  const [assistantAnswer, setAssistantAnswer] = useState(null)
  const [assistantLoading, setAssistantLoading] = useState(false)
  const [assistantError, setAssistantError] = useState(null)

  const [reloadToken, setReloadToken] = useState(0)

  const retry = useCallback(() => setReloadToken((token) => token + 1), [])

  // --- Load the merchant list -------------------------------------------
  useEffect(() => {
    const controller = new AbortController()

    setMerchantsLoading(true)
    setMerchantsError(null)

    getMerchants({ signal: controller.signal })
      .then((body) => {
        if (controller.signal.aborted) return
        const list = body?.merchants ?? []
        setMerchants(list)
        if (list.length > 0) {
          setMerchantId((current) => current || list[0].merchant_id)
          setRange((current) =>
            current.start ? current : rangeForPreset(list[0], DEFAULT_PRESET),
          )
        }
        setMerchantsLoading(false)
      })
      .catch((error) => {
        if (controller.signal.aborted) return
        setMerchantsError(error.message)
        setMerchantsLoading(false)
      })

    return () => controller.abort()
  }, [reloadToken])

  // --- Load dashboard data ----------------------------------------------
  // Aborting the previous request is what stops a slow response for an old
  // merchant landing after a fast one for the new merchant.
  useEffect(() => {
    if (!merchantId || !range.start || !range.end) return undefined

    const controller = new AbortController()

    setDashboardLoading(true)
    setDashboardError(null)

    getDashboard(
      { merchantId, start: range.start, end: range.end },
      { signal: controller.signal },
    )
      .then((body) => {
        if (controller.signal.aborted) return
        setDashboard(body)
        setDashboardLoading(false)
      })
      .catch((error) => {
        if (controller.signal.aborted) return
        setDashboardError(error.message)
        setDashboard(null)
        setDashboardLoading(false)
      })

    return () => controller.abort()
  }, [merchantId, range.start, range.end, reloadToken])

  // --- Load the action plan ---------------------------------------------
  // Deliberately its own request: if the plan fails, the dashboard above it
  // still renders.
  useEffect(() => {
    if (!merchantId || !range.start || !range.end) return undefined

    const controller = new AbortController()

    setActionPlanLoading(true)
    setActionPlanError(null)

    getActionPlan(
      { merchantId, start: range.start, end: range.end },
      { signal: controller.signal },
    )
      .then((body) => {
        if (controller.signal.aborted) return
        setActionPlan(body)
        setActionPlanLoading(false)
      })
      .catch((error) => {
        if (controller.signal.aborted) return
        setActionPlanError(error.message)
        setActionPlan(null)
        setActionPlanLoading(false)
      })

    return () => controller.abort()
  }, [merchantId, range.start, range.end, reloadToken])

  // --- Load insights -----------------------------------------------------
  useEffect(() => {
    if (!merchantId || !range.start || !range.end) return undefined

    const controller = new AbortController()

    setInsightsLoading(true)
    setInsightsError(null)

    getInsights({ merchantId, start: range.start, end: range.end }, { signal: controller.signal })
      .then((body) => {
        if (controller.signal.aborted) return
        setInsights(body)
        setInsightsLoading(false)
      })
      .catch((error) => {
        if (controller.signal.aborted) return
        setInsightsError(error.message)
        setInsights(null)
        setInsightsLoading(false)
      })

    return () => controller.abort()
  }, [merchantId, range.start, range.end, reloadToken])

  // --- Load the forecast -------------------------------------------------
  // Its own request, like the action plan: a forecast that cannot be produced
  // must not take the dashboard down with it.
  useEffect(() => {
    if (!merchantId || !range.start || !range.end) return undefined

    const controller = new AbortController()

    setForecastLoading(true)
    setForecastError(null)

    getForecast({ merchantId, start: range.start, end: range.end }, { signal: controller.signal })
      .then((body) => {
        if (controller.signal.aborted) return
        setForecast(body)
        setForecastLoading(false)
      })
      .catch((error) => {
        if (controller.signal.aborted) return
        setForecastError(error.message)
        setForecast(null)
        setForecastLoading(false)
      })

    return () => controller.abort()
  }, [merchantId, range.start, range.end, reloadToken])

  // --- Assistant configuration -------------------------------------------
  useEffect(() => {
    const controller = new AbortController()
    getAssistantStatus({ signal: controller.signal })
      .then((body) => {
        if (!controller.signal.aborted) setAssistantStatus(body)
      })
      .catch(() => {
        // The panel works without this; it only chooses a label.
      })
    return () => controller.abort()
  }, [reloadToken])

  // Clear a previous answer when the question would no longer apply to it.
  useEffect(() => {
    setAssistantAnswer(null)
    setAssistantError(null)
  }, [merchantId, range.start, range.end])

  const handleAsk = useCallback(
    (question) => {
      if (!merchantId) return
      setAssistantLoading(true)
      setAssistantError(null)

      askAssistant({ merchantId, question, start: range.start, end: range.end })
        .then((body) => {
          setAssistantAnswer(body)
          setAssistantLoading(false)
        })
        .catch((error) => {
          setAssistantError(error.message)
          setAssistantAnswer(null)
          setAssistantLoading(false)
        })
    },
    [merchantId, range.start, range.end],
  )

  const selectedMerchant = useMemo(
    () => merchants.find((item) => item.merchant_id === merchantId) ?? null,
    [merchants, merchantId],
  )

  function handleMerchantChange(nextId) {
    setMerchantId(nextId)
    const merchant = merchants.find((item) => item.merchant_id === nextId)
    if (merchant) setRange(rangeForPreset(merchant, preset))
  }

  function handlePresetChange(nextPreset) {
    setPreset(nextPreset.id)
    if (selectedMerchant) setRange(rangeForPreset(selectedMerchant, nextPreset.id))
  }

  function handleStartChange(value) {
    setPreset('custom')
    setRange((current) => ({ ...current, start: value }))
  }

  function handleEndChange(value) {
    setPreset('custom')
    setRange((current) => ({ ...current, end: value }))
  }

  const summary = dashboard?.summary ?? null
  const daily = dashboard?.daily ?? []
  const hasData = Boolean(dashboard?.has_data)
  const isBusy = merchantsLoading || dashboardLoading

  // The growth figure compares the most recent 7 days with the 7 before them,
  // so it is only shown once the period is long enough to contain both.
  const growth =
    summary && summary.days >= MIN_DAYS_FOR_GROWTH ? summary.revenue_growth_rate : null

  // The plan arrives already ranked; the coach takes the top item and the power
  // moves take the next few, so neither re-orders anything.
  const rankedActions = useMemo(
    () => [
      ...(actionPlan?.high ?? []),
      ...(actionPlan?.medium ?? []),
      ...(actionPlan?.low ?? []),
    ],
    [actionPlan],
  )

  const planRef = useRef(null)

  const openPlan = useCallback(() => {
    const node = planRef.current
    // jsdom and a few older browsers have no scrollIntoView; the button should
    // stay harmless there rather than throwing inside an event handler.
    if (typeof node?.scrollIntoView !== 'function') return

    node.scrollIntoView({
      behavior: window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
        ? 'auto'
        : 'smooth',
      block: 'start',
    })
  }, [])

  return (
    <div className={embedded ? '' : 'min-h-screen bg-ink text-cream'}>
      {!embedded && (
        <TopNav merchantId={merchantId} live={!merchantsError && !merchantsLoading} />
      )}

      <main
        id="business-pulse"
        className={
          embedded
            ? 'scroll-mt-28'
            : 'mx-auto max-w-7xl scroll-mt-28 px-4 py-8 sm:px-6 lg:px-8'
        }
      >
        {/* Greeting, with the controls that scope everything below it. */}
        <GreetingHeader
          merchantId={merchantId}
          periodEnd={summary?.period_end}
          growth={growth}
        >
          <div className="flex flex-col gap-4 rounded-2xl border border-white/8 bg-gradient-to-b from-raised to-surface p-4 shadow-[0_12px_30px_rgb(0_0_0/0.25)] sm:p-5">
            <MerchantSelector
              merchants={merchants}
              value={merchantId}
              onChange={handleMerchantChange}
              disabled={merchantsLoading || Boolean(merchantsError)}
            />
            <DateRangeControls
              start={range.start}
              end={range.end}
              minDate={selectedMerchant?.first_date}
              maxDate={selectedMerchant?.last_date}
              activePreset={preset}
              onPresetChange={handlePresetChange}
              onStartChange={handleStartChange}
              onEndChange={handleEndChange}
              disabled={!selectedMerchant}
            />
            {dashboardLoading && (
              <p className="text-xs text-faint" role="status">
                updating…
              </p>
            )}
          </div>
        </GreetingHeader>

        {/* Merchant list failure blocks everything below it. */}
        {merchantsError && (
          <div className="mt-8">
            <StatusPanel
              tone="error"
              title="Could not load merchants"
              message={merchantsError}
              actionLabel="Try again"
              onAction={retry}
            />
          </div>
        )}

        {!merchantsError && dashboardError && (
          <div className="mt-8">
            <StatusPanel
              tone="error"
              title="Could not load dashboard data"
              message={dashboardError}
              actionLabel="Try again"
              onAction={retry}
            />
          </div>
        )}

        {!merchantsError && !dashboardError && isBusy && !summary && (
          <>
            <div className="mt-8 grid grid-cols-1 gap-5 lg:grid-cols-[1.85fr_1fr]">
              <ChartSkeleton height={220} />
              <ChartSkeleton height={220} />
            </div>
            <div className="mt-5 grid grid-cols-1 gap-5 sm:grid-cols-3">
              {Array.from({ length: 3 }, (_, index) => (
                <PulseKpiSkeleton key={index} />
              ))}
            </div>
          </>
        )}

        {!merchantsError && !dashboardError && summary && !hasData && (
          <div className="mt-8">
            <StatusPanel
              tone="empty"
              title="No activity in this period"
              message={`${merchantId} has no recorded sales between ${formatDateRange(
                range.start,
                range.end,
              )}. Try a wider date range or the "All" preset.`}
              actionLabel="Show all data"
              onAction={() => handlePresetChange(PRESETS[PRESETS.length - 1])}
            />
          </div>
        )}

        {!merchantsError && !dashboardError && summary && hasData && (
          <>
            {/* 1. The headline: this period's revenue, and the single best move. */}
            <div className="mt-8 grid grid-cols-1 items-stretch gap-5 lg:grid-cols-[1.85fr_1fr]">
              <RevenueHero
                summary={summary}
                daily={daily}
                growth={growth}
                growthLabel="vs previous 7 days"
              />
              <PanelBoundary name="Growth coach">
                <AiCoachCard
                  item={rankedActions[0] ?? null}
                  loading={actionPlanLoading && !actionPlan}
                  error={actionPlanError}
                  onOpenPlan={openPlan}
                />
              </PanelBoundary>
            </div>

            {/* 2. The three supporting numbers. */}
            <div className="mt-5 grid grid-cols-1 gap-5 sm:grid-cols-3">
              <PulseKpi
                label="Orders"
                value={formatNumber(summary.total_orders)}
                hint={`${formatNumber(summary.total_units_sold)} units sold`}
                accent
                delay={0}
              />
              <PulseKpi
                label="Returning customers"
                value={formatPercent(summary.repeat_customer_rate)}
                hint={`${formatNumber(summary.repeat_customers)} of ${formatNumber(
                  summary.total_customers,
                )} visits`}
                delay={70}
              />
              <PulseKpi
                label="Average order"
                value={formatCurrency(summary.average_order_value)}
                hint={`${formatCurrency(summary.revenue_per_customer)} per visit`}
                delay={140}
              />
            </div>

            {/* 3. Weekly shape, and what to do about it. */}
            <div className="mt-5 grid grid-cols-1 items-stretch gap-5 lg:grid-cols-[1.85fr_1fr]">
              <PanelBoundary name="Customer rhythm">
                <CustomerRhythm daily={daily} />
              </PanelBoundary>
              <PanelBoundary name="Power moves">
                <PowerMoves
                  items={rankedActions.slice(0, POWER_MOVE_COUNT)}
                  loading={actionPlanLoading && !actionPlan}
                  error={actionPlanError}
                  onOpenPlan={openPlan}
                />
              </PanelBoundary>
            </div>

            <p className="mt-4 text-xs leading-relaxed text-faint">
              Gross profit is revenue minus cost of goods sold; overheads are not modelled.
              Customer visits sum each day&apos;s distinct customers, so a shopper active on
              several days counts once per day.
            </p>

            {/* 4. Performance trends */}
            <div className="mt-8 grid grid-cols-1 gap-5">
              <TrendChart
                title="Revenue and gross profit"
                subtitle="Daily totals across the selected period"
                data={daily}
                height={300}
                valueFormatter={formatCurrency}
                axisFormatter={formatCurrencyCompact}
                series={[
                  { key: 'revenue', label: 'Revenue', color: COLORS.revenue, type: 'area' },
                  { key: 'profit', label: 'Gross profit', color: COLORS.profit, type: 'line' },
                ]}
              />
            </div>

            <div className="mt-5 grid grid-cols-1 gap-5 lg:grid-cols-2">
              <TrendChart
                title="Orders"
                subtitle="Orders placed per day"
                data={daily}
                valueFormatter={formatNumber}
                axisFormatter={formatNumberCompact}
                series={[{ key: 'orders', label: 'Orders', color: COLORS.orders, type: 'line' }]}
              />
              <TrendChart
                title="Customers: new vs repeat"
                subtitle="Daily distinct customers, split by type"
                data={daily}
                valueFormatter={formatNumber}
                axisFormatter={formatNumberCompact}
                series={[
                  {
                    key: 'repeat_customers',
                    label: 'Repeat',
                    color: COLORS.repeatCustomers,
                    type: 'area',
                    stackId: 'customers',
                  },
                  {
                    key: 'new_customers',
                    label: 'New',
                    color: COLORS.newCustomers,
                    type: 'area',
                    stackId: 'customers',
                  },
                ]}
              />
            </div>

            {/* 5. Growth lab: what changed, what to do, what comes next. */}
            <section id="growth-lab" className="mt-8 scroll-mt-28">
              <h2 className="text-xs font-semibold uppercase tracking-[0.16em] text-gold">
                Growth lab
              </h2>

              <div className="mt-4">
                {insightsLoading && !insights && <InsightsSkeleton />}
                {insightsError && (
                  <StatusPanel
                    tone="error"
                    title="Could not load insights"
                    message={insightsError}
                    actionLabel="Try again"
                    onAction={retry}
                  />
                )}
                {!insightsError && insights?.has_data && (
                  <PanelBoundary name="Insights">
                    <InsightsPanel insights={insights} />
                  </PanelBoundary>
                )}
              </div>

              <div className="mt-5 scroll-mt-28" ref={planRef}>
                {actionPlanLoading && !actionPlan && <ActionPlanSkeleton />}
                {actionPlanError && (
                  <StatusPanel
                    tone="error"
                    title="Could not load the action plan"
                    message={actionPlanError}
                    actionLabel="Try again"
                    onAction={retry}
                  />
                )}
                {!actionPlanError && actionPlan?.has_data && (
                  <PanelBoundary name="Action plan">
                    <ActionPlanPanel plan={actionPlan} />
                  </PanelBoundary>
                )}
              </div>

              <div className="mt-5">
                {forecastLoading && !forecast && <ForecastSkeleton />}
                {forecastError && (
                  <StatusPanel
                    tone="error"
                    title="Could not load the forecast"
                    message={forecastError}
                    actionLabel="Try again"
                    onAction={retry}
                  />
                )}
                {!forecastError && forecast && (
                  <PanelBoundary name="Forecast">
                    <ForecastPanel daily={daily} forecast={forecast} />
                  </PanelBoundary>
                )}
              </div>

              <div className="mt-5">
                <PanelBoundary name="Assistant">
                  <AssistantPanel
                    status={assistantStatus}
                    answer={assistantAnswer}
                    loading={assistantLoading}
                    error={assistantError}
                    onAsk={handleAsk}
                    onRetry={() => setAssistantError(null)}
                    disabled={!merchantId}
                  />
                </PanelBoundary>
              </div>
            </section>
          </>
        )}

        <p className="mt-10 border-t border-white/8 pt-5 text-xs text-faint">
          All figures come from this merchant&apos;s own synthetic demo dataset. MerchantAI
          does not use, and does not claim access to, private Paytm data or APIs.
        </p>
      </main>
    </div>
  )
}
