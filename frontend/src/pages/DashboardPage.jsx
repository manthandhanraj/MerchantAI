/**
 * Merchant dashboard (Stage 3).
 *
 * Owns the data fetching and page layout. Every number rendered here comes from
 * GET /api/dashboard — nothing is computed in the browser, so the dashboard and
 * the API can never disagree.
 */
import { useCallback, useEffect, useMemo, useState } from 'react'

import { ActionPlanPanel, ActionPlanSkeleton } from '../components/ActionPlanPanel'
import { AssistantPanel } from '../components/AssistantPanel'
import { DateRangeControls, PRESETS } from '../components/DateRangeControls'
import { ForecastPanel, ForecastSkeleton } from '../components/ForecastPanel'
import { InsightsPanel, InsightsSkeleton } from '../components/InsightsPanel'
import { KpiCard, KpiCardSkeleton } from '../components/KpiCard'
import { MerchantSelector } from '../components/MerchantSelector'
import { PanelBoundary } from '../components/PanelBoundary'
import { ChartSkeleton, StatusPanel } from '../components/StatusPanel'
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

const COLORS = {
  revenue: '#0f766e',
  profit: '#f59e0b',
  orders: '#4f46e5',
  newCustomers: '#93c5fd',
  repeatCustomers: '#1d4ed8',
}

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

export default function DashboardPage() {
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

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto max-w-7xl px-4 py-5 sm:px-6 lg:px-8">
          <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <h1 className="text-xl font-semibold tracking-tight">MerchantAI</h1>
            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600">
              Demo data
            </span>
          </div>
          <p className="mt-1 text-sm text-slate-500">Merchant performance dashboard</p>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
        {/* Controls */}
        <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
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
          </div>

          {summary?.period_start && (
            <p className="mt-4 border-t border-slate-100 pt-3 text-sm text-slate-600">
              Showing{' '}
              <span className="font-medium text-slate-900">
                {formatDateRange(summary.period_start, summary.period_end)}
              </span>{' '}
              · {formatNumber(summary.days)} days
              {dashboardLoading && <span className="ml-2 text-slate-400">updating…</span>}
            </p>
          )}
        </section>

        {/* Merchant list failure blocks everything below it. */}
        {merchantsError && (
          <div className="mt-6">
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
          <div className="mt-6">
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
            <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
              {Array.from({ length: 5 }, (_, index) => (
                <KpiCardSkeleton key={index} />
              ))}
            </div>
            <div className="mt-6 grid grid-cols-1 gap-4">
              <ChartSkeleton height={280} />
            </div>
          </>
        )}

        {!merchantsError && !dashboardError && summary && !hasData && (
          <div className="mt-6">
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
            {/* 1. Business overview */}
            <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
              <KpiCard
                label="Revenue"
                value={formatCurrency(summary.total_revenue)}
                delta={summary.days >= MIN_DAYS_FOR_GROWTH ? summary.revenue_growth_rate : null}
                deltaLabel="vs previous 7 days"
              />
              <KpiCard
                label="Orders"
                value={formatNumber(summary.total_orders)}
                hint={`${formatNumber(summary.total_units_sold)} units sold`}
              />
              <KpiCard
                label="Customer Visits"
                value={formatNumber(summary.total_customers)}
                hint={`${formatPercent(summary.repeat_customer_rate)} repeat`}
              />
              <KpiCard
                label="Gross Profit"
                value={formatCurrency(summary.total_profit)}
                hint={`${formatPercent(summary.profit_margin)} margin`}
              />
              <KpiCard
                label="Avg Order Value"
                value={formatCurrency(summary.average_order_value)}
                hint={`${formatCurrency(summary.revenue_per_customer)} per visit`}
              />
            </div>

            <p className="mt-3 text-xs text-slate-500">
              Gross profit is revenue minus cost of goods sold; overheads are not modelled.
              Customer visits sum each day&apos;s distinct customers, so a shopper active on
              several days counts once per day.
            </p>

            {/* 2. Performance trends */}
            <div className="mt-6 grid grid-cols-1 gap-4">
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

            <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
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

            {/* 3. AI insights - what changed and why it was flagged */}
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

            {/* 4. Growth recommendations, prioritised */}
            <div className="mt-4">
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

            {/* 5. Short-term forecast */}
            <div className="mt-4">
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

            {/* 6. Ask follow-up questions, grounded in everything above */}
            <div className="mt-4">
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
          </>
        )}
      </main>
    </div>
  )
}
