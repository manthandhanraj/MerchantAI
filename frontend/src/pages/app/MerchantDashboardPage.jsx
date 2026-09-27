/**
 * The private Business Pulse dashboard, driven by a stored analysis run.
 *
 * It reuses the demo's panels unchanged — the payloads the private endpoints
 * return have the same shape as the public ones, because both are produced by
 * the same analytics services. The differences are all about provenance: which
 * upload the figures came from, when they were computed, and what to do when
 * there is nothing to show yet.
 */
import { useCallback, useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'

import { ActionPlanPanel } from '../../components/ActionPlanPanel'
import { AiCoachCard } from '../../components/AiCoachCard'
import { AppShell } from '../../components/AppShell'
import { useWorkspace } from '../../auth/WorkspaceProvider'
import { AssistantPanel } from '../../components/AssistantPanel'
import { CustomerRhythm } from '../../components/CustomerRhythm'
import { ForecastPanel } from '../../components/ForecastPanel'
import { InsightsPanel } from '../../components/InsightsPanel'
import { PanelBoundary } from '../../components/PanelBoundary'
import {
  CategoryPerformance,
  InventoryAlerts,
  ProductPerformance,
} from '../../components/PerformancePanels'
import { PowerMoves } from '../../components/PowerMoves'
import { PulseKpi, PulseKpiSkeleton } from '../../components/PulseKpi'
import { RevenueHero } from '../../components/RevenueHero'
import { ChartSkeleton, StatusPanel } from '../../components/StatusPanel'
import { TrendChart } from '../../components/TrendChart'
import { Alert, Button, Card, EmptyState, PageHeader, Select, Spinner } from '../../components/ui'
import {
  askPrivateAssistant,
  createReport,
  getMerchant,
  getPrivateActionPlan,
  getPrivateAssistantStatus,
  getPrivateDashboard,
  getPrivateForecast,
  getPrivateInsights,
  listAnalyses,
  runAnalysis,
} from '../../services/privateApi'
import {
  formatCurrency,
  formatCurrencyCompact,
  formatDateRange,
  formatNumber,
  formatNumberCompact,
  formatPercent,
} from '../../utils/format'

// Same palette the demo dashboard uses, so a chart means the same thing in both.
const COLORS = {
  revenue: '#b8e49d',
  profit: '#e5bd75',
  orders: '#7fc8d8',
  newCustomers: '#8fb9a3',
  repeatCustomers: '#b8e49d',
}

const MIN_DAYS_FOR_GROWTH = 14
const POWER_MOVE_COUNT = 3

/**
 * A metric the uploaded columns could not support.
 *
 * Shown instead of a zero, because "0 customers" and "you did not upload
 * customer data" are different statements and only one of them is true.
 */
const UNAVAILABLE = 'Not available from this dataset'

function has(value) {
  return typeof value === 'number' && Number.isFinite(value) && value !== 0
}

export default function MerchantDashboardPage() {
  const { id: merchantId } = useParams()
  const { isDemo, readOnly } = useWorkspace()

  const [merchant, setMerchant] = useState(null)
  const [analyses, setAnalyses] = useState([])
  const [analysisId, setAnalysisId] = useState(null)
  const [bootstrapping, setBootstrapping] = useState(true)
  const [bootError, setBootError] = useState(null)

  const [dashboard, setDashboard] = useState(null)
  const [insights, setInsights] = useState(null)
  const [plan, setPlan] = useState(null)
  const [forecast, setForecast] = useState(null)
  const [panelsLoading, setPanelsLoading] = useState(false)
  const [panelError, setPanelError] = useState(null)

  const [assistantStatus, setAssistantStatus] = useState(null)
  const [assistantAnswer, setAssistantAnswer] = useState(null)
  const [assistantLoading, setAssistantLoading] = useState(false)
  const [assistantError, setAssistantError] = useState(null)

  const [running, setRunning] = useState(false)
  const [reporting, setReporting] = useState(false)
  const [notice, setNotice] = useState(null)

  // ---- merchant + analysis list ---------------------------------------
  const bootstrap = useCallback(
    async (signal) => {
      setBootstrapping(true)
      setBootError(null)
      try {
        const [merchantBody, analysesBody] = await Promise.all([
          getMerchant(merchantId, { signal }),
          listAnalyses(merchantId, { signal }),
        ])
        if (signal?.aborted) return
        setMerchant(merchantBody)
        const rows = analysesBody.analyses ?? []
        setAnalyses(rows)
        const completed = rows.find((row) => row.status === 'completed')
        setAnalysisId(completed?.id ?? null)
      } catch (caught) {
        if (!signal?.aborted) setBootError(caught.message)
      } finally {
        if (!signal?.aborted) setBootstrapping(false)
      }
    },
    [merchantId],
  )

  useEffect(() => {
    const controller = new AbortController()
    bootstrap(controller.signal)
    return () => controller.abort()
  }, [bootstrap])

  // ---- the four panels, for the selected analysis ----------------------
  useEffect(() => {
    if (!analysisId) return undefined
    const controller = new AbortController()
    const { signal } = controller

    setPanelsLoading(true)
    setPanelError(null)

    Promise.all([
      getPrivateDashboard(merchantId, analysisId, { signal }),
      getPrivateInsights(merchantId, analysisId, { signal }),
      getPrivateActionPlan(merchantId, analysisId, { signal }),
      getPrivateForecast(merchantId, analysisId, { signal }),
    ])
      .then(([dash, ins, act, fc]) => {
        if (signal.aborted) return
        setDashboard(dash)
        setInsights(ins)
        setPlan(act)
        setForecast(fc)
        setPanelsLoading(false)
      })
      .catch((caught) => {
        if (signal.aborted) return
        setPanelError(caught.message)
        setPanelsLoading(false)
      })

    return () => controller.abort()
  }, [merchantId, analysisId])

  useEffect(() => {
    const controller = new AbortController()
    getPrivateAssistantStatus({ signal: controller.signal })
      .then((body) => {
        if (!controller.signal.aborted) setAssistantStatus(body)
      })
      .catch(() => {
        // The panel works without this; it only chooses a label.
      })
    return () => controller.abort()
  }, [])

  // A previous answer must not sit above a different analysis's numbers.
  useEffect(() => {
    setAssistantAnswer(null)
    setAssistantError(null)
  }, [analysisId])

  const handleAsk = useCallback(
    (question) => {
      setAssistantLoading(true)
      setAssistantError(null)
      askPrivateAssistant(merchantId, question)
        .then((body) => {
          setAssistantAnswer(body)
          setAssistantLoading(false)
        })
        .catch((caught) => {
          setAssistantError(caught.message)
          setAssistantAnswer(null)
          setAssistantLoading(false)
        })
    },
    [merchantId],
  )

  async function handleRunAnalysis() {
    setRunning(true)
    setNotice(null)
    try {
      const body = await runAnalysis(merchantId, {
        idempotency_key: `run-${Date.now()}`,
      })
      const listBody = await listAnalyses(merchantId)
      setAnalyses(listBody.analyses ?? [])
      setAnalysisId(body.analysis.id)
      setNotice({ tone: 'success', text: 'Analysis complete. Your dashboard is up to date.' })
    } catch (caught) {
      setNotice({ tone: 'error', text: caught.message })
    } finally {
      setRunning(false)
    }
  }

  async function handleGenerateReport() {
    setReporting(true)
    setNotice(null)
    try {
      await createReport(merchantId, analysisId)
      setNotice({
        tone: 'success',
        text: 'Report generated. Open the Reports tab to download it.',
      })
    } catch (caught) {
      setNotice({ tone: 'error', text: caught.message })
    } finally {
      setReporting(false)
    }
  }

  // ---- states ----------------------------------------------------------
  if (bootstrapping) {
    return (
      <AppShell activeMerchantId={merchantId}>
        <Spinner label="Opening your dashboard…" />
      </AppShell>
    )
  }

  if (bootError) {
    return (
      <AppShell activeMerchantId={merchantId}>
        <Alert
          tone="error"
          title="Could not open this business"
          action={
            <Button variant="ghost" onClick={() => bootstrap()}>
              Try again
            </Button>
          }
        >
          {bootError}
        </Alert>
      </AppShell>
    )
  }

  const info = merchant?.merchant ?? {}
  const hasBothUploads = merchant?.has_sales_data && merchant?.has_customer_data
  const failedLatest = analyses[0]?.status === 'failed' ? analyses[0] : null

  // Nothing uploaded, or only half of it.
  if (!analysisId) {
    return (
      <AppShell activeMerchantId={merchantId}>
        <PageHeader eyebrow={info.name} title="No analysis yet" />
        <div className="mt-8 max-w-2xl">
          {failedLatest && (
            <div className="mb-5">
              <Alert tone="error" title="The last analysis did not finish">
                {failedLatest.error_message || 'Something went wrong while analysing your data.'}
              </Alert>
            </div>
          )}
          <EmptyState
            title={hasBothUploads ? 'Ready to analyse' : 'Upload your data to get started'}
            message={
              hasBothUploads
                ? 'Both files are in place. Run the analysis to see your dashboard, insights, plan and forecast.'
                : 'MerchantAI needs a sales file and a customer file before it can tell you anything. It will never show you numbers it did not compute from your data.'
            }
            action={
              readOnly ? (
                <Button as="link" to="/signup">
                  Create your own workspace
                </Button>
              ) : hasBothUploads ? (
                <Button onClick={handleRunAnalysis} disabled={running}>
                  {running ? 'Running the analysis…' : 'Analyse my business'}
                </Button>
              ) : (
                <Button as="link" to={`/app/merchant/${merchantId}/upload`}>
                  Upload data
                </Button>
              )
            }
          />
          {notice && (
            <div className="mt-5">
              <Alert tone={notice.tone}>{notice.text}</Alert>
            </div>
          )}
        </div>
      </AppShell>
    )
  }

  const summary = dashboard?.summary ?? null
  const daily = dashboard?.daily ?? []
  const growth =
    summary && summary.days >= MIN_DAYS_FOR_GROWTH ? summary.revenue_growth_rate : null
  const rankedActions = [...(plan?.high ?? []), ...(plan?.medium ?? []), ...(plan?.low ?? [])]

  return (
    <AppShell activeMerchantId={merchantId}>
      <PageHeader
        eyebrow={info.business_type || 'Your business'}
        title={info.name || 'Your business'}
        description={
          dashboard?.period?.start
            ? `Analysis of ${formatDateRange(dashboard.period.start, dashboard.period.end)}`
            : undefined
        }
      >
        <div className="flex flex-wrap items-center gap-2">
          {analyses.length > 1 && (
            <>
              <label htmlFor="analysis-select" className="sr-only">
                Analysis
              </label>
              <Select
                id="analysis-select"
                value={analysisId}
                onChange={(event) => setAnalysisId(event.target.value)}
                className="max-w-[16rem]"
              >
                {analyses
                  .filter((row) => row.status === 'completed')
                  .map((row) => (
                    <option key={row.id} value={row.id}>
                      {String(row.created_at).slice(0, 10)} · {row.date_start} to {row.date_end}
                    </option>
                  ))}
              </Select>
            </>
          )}
          {!readOnly && (
            <>
              <Button as="link" to={`/app/merchant/${merchantId}/upload`} variant="ghost">
                Upload new data
              </Button>
              <Button variant="ghost" onClick={handleRunAnalysis} disabled={running}>
                {running ? 'Running…' : 'Re-run analysis'}
              </Button>
            </>
          )}
          <Button variant="gold" onClick={handleGenerateReport} disabled={reporting}>
            {reporting ? 'Generating…' : 'Generate report'}
          </Button>
        </div>
      </PageHeader>

      {notice && (
        <div className="mt-5">
          <Alert tone={notice.tone}>{notice.text}</Alert>
        </div>
      )}

      {panelError && (
        <div className="mt-5">
          <Alert tone="error" title="Could not load this analysis">
            {panelError}
          </Alert>
        </div>
      )}

      {panelsLoading && !summary && (
        <>
          <div className="mt-8 grid grid-cols-1 gap-5 lg:grid-cols-[1.85fr_1fr]">
            <ChartSkeleton height={220} />
            <ChartSkeleton height={220} />
          </div>
          <div className="mt-5 grid grid-cols-1 gap-5 sm:grid-cols-3">
            {[0, 1, 2].map((index) => (
              <PulseKpiSkeleton key={index} />
            ))}
          </div>
        </>
      )}

      {summary && !dashboard.has_data && (
        <div className="mt-8">
          <StatusPanel
            tone="empty"
            title="No activity in this period"
            message="The analysed period contains no recorded sales. Upload data covering a period with trading activity."
            actionLabel="Upload data"
            onAction={() => window.location.assign(`/app/merchant/${merchantId}/upload`)}
          />
        </div>
      )}

      {summary && dashboard.has_data && (
        <>
          {/* 1. Headline */}
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
                loading={panelsLoading && !plan}
                error={null}
                onOpenPlan={() =>
                  document.getElementById('growth-lab')?.scrollIntoView({ block: 'start' })
                }
              />
            </PanelBoundary>
          </div>

          {/* 2. Supporting numbers */}
          <div className="mt-5 grid grid-cols-1 gap-5 sm:grid-cols-3">
            <PulseKpi
              label="Orders"
              value={formatNumber(summary.total_orders)}
              hint={`${formatNumber(summary.total_units_sold)} units sold`}
              accent
            />
            <PulseKpi
              label="Returning customers"
              value={
                has(summary.total_customers)
                  ? formatPercent(summary.repeat_customer_rate)
                  : '—'
              }
              hint={
                has(summary.total_customers)
                  ? `${formatNumber(summary.repeat_customers)} of ${formatNumber(
                      summary.total_customers,
                    )} visits`
                  : UNAVAILABLE
              }
              delay={70}
            />
            <PulseKpi
              label="Average order"
              value={
                has(summary.total_orders) ? formatCurrency(summary.average_order_value) : '—'
              }
              hint={
                has(summary.total_customers)
                  ? `${formatCurrency(summary.revenue_per_customer)} per visit`
                  : has(summary.total_orders)
                    ? `${formatNumber(summary.total_orders)} orders`
                    : UNAVAILABLE
              }
              delay={140}
            />
          </div>

          {/* 3. Rhythm and moves */}
          <div className="mt-5 grid grid-cols-1 items-stretch gap-5 lg:grid-cols-[1.85fr_1fr]">
            <PanelBoundary name="Customer rhythm">
              <CustomerRhythm daily={daily} />
            </PanelBoundary>
            <PanelBoundary name="Power moves">
              <PowerMoves
                items={rankedActions.slice(0, POWER_MOVE_COUNT)}
                loading={panelsLoading && !plan}
                error={null}
                onOpenPlan={() =>
                  document.getElementById('growth-lab')?.scrollIntoView({ block: 'start' })
                }
              />
            </PanelBoundary>
          </div>

          {/* 4. Data provenance */}
          <Card className="mt-5">
            <h2 className="text-sm font-semibold text-cream">Where these figures came from</h2>
            <dl className="mt-3 grid grid-cols-1 gap-x-8 gap-y-2 text-sm sm:grid-cols-2">
              <div className="flex justify-between gap-4 border-b border-white/5 pb-2">
                <dt className="text-faint">Source file</dt>
                <dd className="text-cream">
                  {isDemo
                    ? 'Seeded synthetic demo data'
                    : (dashboard.source_upload?.original_filename ?? 'No longer available')}
                </dd>
              </div>
              <div className="flex justify-between gap-4 border-b border-white/5 pb-2">
                <dt className="text-faint">Rows analysed</dt>
                <dd className="tabular-nums text-cream">
                  {dashboard.source_upload
                    ? formatNumber(dashboard.source_upload.row_count)
                    : '—'}
                </dd>
              </div>
              <div className="flex justify-between gap-4 border-b border-white/5 pb-2">
                <dt className="text-faint">Period covered</dt>
                <dd className="text-cream">
                  {formatDateRange(dashboard.period.start, dashboard.period.end)}
                </dd>
              </div>
              <div className="flex justify-between gap-4 border-b border-white/5 pb-2">
                <dt className="text-faint">Analysis run</dt>
                <dd className="text-cream">
                  {String(dashboard.generated_at ?? '').slice(0, 10) || '—'}
                </dd>
              </div>
            </dl>
            <p className="mt-4 text-xs leading-relaxed text-faint">
              Gross profit is revenue minus cost of goods sold; overheads are not modelled.
              Customer visits sum each day&apos;s distinct customers, so a shopper active on
              several days counts once per day.
            </p>
          </Card>

          {/* 5. Trends */}
          <div className="mt-8 grid grid-cols-1 gap-5">
            <TrendChart
              title="Revenue and gross profit"
              subtitle="Daily totals across the analysed period"
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

          {/* 6. Product, category, inventory */}
          <div className="mt-5 grid grid-cols-1 gap-5 lg:grid-cols-[1.4fr_1fr]">
            <PanelBoundary name="Product performance">
              <ProductPerformance products={dashboard.products} />
            </PanelBoundary>
            <div className="flex flex-col gap-5">
              <PanelBoundary name="Category performance">
                <CategoryPerformance categories={dashboard.categories} />
              </PanelBoundary>
              <PanelBoundary name="Inventory">
                <InventoryAlerts inventory={dashboard.inventory} />
              </PanelBoundary>
            </div>
          </div>

          {/* 7. Growth lab */}
          <section id="growth-lab" className="mt-8 scroll-mt-28">
            <h2 className="text-xs font-semibold uppercase tracking-[0.16em] text-gold">
              Growth lab
            </h2>

            {insights?.has_data && (
              <div className="mt-4">
                <PanelBoundary name="Insights">
                  <InsightsPanel insights={insights} />
                </PanelBoundary>
              </div>
            )}

            {plan?.has_data && (
              <div className="mt-5">
                <PanelBoundary name="Action plan">
                  <ActionPlanPanel plan={plan} />
                </PanelBoundary>
              </div>
            )}

            {forecast && (
              <div className="mt-5">
                <PanelBoundary name="Forecast">
                  <ForecastPanel daily={daily} forecast={forecast} />
                </PanelBoundary>
              </div>
            )}

            <div className="mt-5">
              <PanelBoundary name="Assistant">
                <AssistantPanel
                  status={assistantStatus}
                  answer={assistantAnswer}
                  loading={assistantLoading}
                  error={assistantError}
                  onAsk={handleAsk}
                  onRetry={() => setAssistantError(null)}
                  disabled={false}
                />
              </PanelBoundary>
            </div>
          </section>
        </>
      )}
    </AppShell>
  )
}
