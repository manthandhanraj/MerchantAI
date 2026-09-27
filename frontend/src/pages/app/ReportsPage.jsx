/**
 * Analysis history and downloadable reports.
 *
 * Downloads go through a signed URL the backend mints only after confirming the
 * report belongs to the caller. The URL is short-lived and never rendered into
 * the page as a permanent link.
 */
import { useCallback, useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'

import { AppShell } from '../../components/AppShell'
import { useWorkspace } from '../../auth/WorkspaceProvider'
import { Alert, Button, Card, EmptyState, PageHeader, Spinner } from '../../components/ui'
import {
  createReport,
  deleteReport,
  getMerchant,
  getReportDownloadUrl,
  listAnalyses,
  listReports,
} from '../../services/privateApi'
import { formatDateRange, formatNumber } from '../../utils/format'

function when(value) {
  if (!value) return '—'
  const iso = String(value)
  return `${iso.slice(0, 10)} ${iso.slice(11, 16)}`.trim()
}

export default function ReportsPage() {
  const { id: merchantId } = useParams()
  const { readOnly } = useWorkspace()

  const [merchant, setMerchant] = useState(null)
  const [analyses, setAnalyses] = useState([])
  const [reports, setReports] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [busyId, setBusyId] = useState(null)
  const [notice, setNotice] = useState(null)
  const [confirmingDelete, setConfirmingDelete] = useState(null)

  const load = useCallback(
    async (signal) => {
      setLoading(true)
      setError(null)
      try {
        const [merchantBody, analysesBody, reportsBody] = await Promise.all([
          getMerchant(merchantId, { signal }),
          listAnalyses(merchantId, { signal }),
          listReports(merchantId, { signal }),
        ])
        if (signal?.aborted) return
        setMerchant(merchantBody.merchant)
        setAnalyses(analysesBody.analyses ?? [])
        setReports(reportsBody.reports ?? [])
      } catch (caught) {
        if (!signal?.aborted) setError(caught.message)
      } finally {
        if (!signal?.aborted) setLoading(false)
      }
    },
    [merchantId],
  )

  useEffect(() => {
    const controller = new AbortController()
    load(controller.signal)
    return () => controller.abort()
  }, [load])

  async function generate(analysisId) {
    setBusyId(analysisId)
    setNotice(null)
    try {
      await createReport(merchantId, analysisId)
      const body = await listReports(merchantId)
      setReports(body.reports ?? [])
      setNotice({ tone: 'success', text: 'Report generated and stored privately.' })
    } catch (caught) {
      setNotice({ tone: 'error', text: caught.message })
    } finally {
      setBusyId(null)
    }
  }

  async function download(reportId) {
    setBusyId(reportId)
    setNotice(null)
    try {
      const { url } = await getReportDownloadUrl(merchantId, reportId)
      window.open(url, '_blank', 'noopener,noreferrer')
    } catch (caught) {
      setNotice({ tone: 'error', text: caught.message })
    } finally {
      setBusyId(null)
    }
  }

  async function remove(reportId) {
    setBusyId(reportId)
    setNotice(null)
    try {
      await deleteReport(merchantId, reportId)
      setReports((current) => current.filter((row) => row.id !== reportId))
      setConfirmingDelete(null)
      setNotice({ tone: 'success', text: 'Report deleted. The stored file was removed too.' })
    } catch (caught) {
      setNotice({ tone: 'error', text: caught.message })
    } finally {
      setBusyId(null)
    }
  }

  if (loading) {
    return (
      <AppShell activeMerchantId={merchantId}>
        <Spinner label="Loading your reports…" />
      </AppShell>
    )
  }

  if (error) {
    return (
      <AppShell activeMerchantId={merchantId}>
        <Alert
          tone="error"
          title="Could not load reports"
          action={
            <Button variant="ghost" onClick={() => load()}>
              Try again
            </Button>
          }
        >
          {error}
        </Alert>
      </AppShell>
    )
  }

  const completed = analyses.filter((row) => row.status === 'completed')

  return (
    <AppShell activeMerchantId={merchantId}>
      <PageHeader
        eyebrow={merchant?.name}
        title="Reports and analysis history"
        description="Every analysis you have run, and the business reports generated from them."
      >
        <Button as="link" to={`/app/merchant/${merchantId}`} variant="ghost">
          Back to dashboard
        </Button>
      </PageHeader>

      {notice && (
        <div className="mt-5">
          <Alert tone={notice.tone}>{notice.text}</Alert>
        </div>
      )}

      {/* ---- reports ----------------------------------------------------- */}
      <div className="mt-8">
        <h2 className="text-sm font-semibold text-cream">Generated reports</h2>
        {reports.length === 0 ? (
          <div className="mt-4">
            <EmptyState
              title="No reports yet"
              message="Generate one from any completed analysis below. Reports are PDFs built from exactly the figures on your dashboard."
            />
          </div>
        ) : (
          <Card className="mt-4">
            <ul className="divide-y divide-white/5">
              {reports.map((report) => (
                <li key={report.id} className="flex flex-wrap items-center gap-x-4 gap-y-2 py-3">
                  <div className="min-w-0">
                    <p className="text-sm text-cream">Business analysis report</p>
                    <p className="text-xs text-faint">
                      {when(report.created_at)} · {report.format.toUpperCase()}
                      {report.byte_size
                        ? ` · ${(report.byte_size / 1024).toFixed(0)} KB`
                        : ''}
                    </p>
                  </div>
                  <div className="ml-auto flex flex-wrap items-center gap-2">
                    <Button
                      variant="ghost"
                      onClick={() => download(report.id)}
                      disabled={busyId === report.id}
                      className="px-4 py-2 text-xs"
                    >
                      {busyId === report.id ? 'Preparing…' : 'Download'}
                    </Button>
                    {readOnly ? null : confirmingDelete === report.id ? (
                      <>
                        <Button
                          variant="danger"
                          onClick={() => remove(report.id)}
                          disabled={busyId === report.id}
                          className="px-4 py-2 text-xs"
                        >
                          Confirm delete
                        </Button>
                        <Button
                          variant="quiet"
                          onClick={() => setConfirmingDelete(null)}
                          className="px-3 py-2 text-xs"
                        >
                          Cancel
                        </Button>
                      </>
                    ) : (
                      <Button
                        variant="quiet"
                        onClick={() => setConfirmingDelete(report.id)}
                        className="px-3 py-2 text-xs"
                      >
                        Delete
                      </Button>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          </Card>
        )}
      </div>

      {/* ---- analyses ---------------------------------------------------- */}
      <div className="mt-8">
        <h2 className="text-sm font-semibold text-cream">Analysis history</h2>
        {analyses.length === 0 ? (
          <div className="mt-4">
            <EmptyState
              title="Nothing analysed yet"
              message="Upload a sales file and a customer file, then run your first analysis."
              action={
                <Button as="link" to={`/app/merchant/${merchantId}/upload`}>
                  Upload data
                </Button>
              }
            />
          </div>
        ) : (
          <Card className="mt-4">
            <ul className="divide-y divide-white/5">
              {analyses.map((run) => (
                <li key={run.id} className="flex flex-wrap items-center gap-x-4 gap-y-2 py-3">
                  <div className="min-w-0">
                    <p className="text-sm text-cream">
                      {run.date_start && run.date_end
                        ? formatDateRange(run.date_start, run.date_end)
                        : 'Analysis'}
                    </p>
                    <p className="text-xs text-faint">
                      Run {when(run.created_at)}
                      {run.status !== 'completed' && (
                        <span className="ml-2 text-alert">{run.status}</span>
                      )}
                    </p>
                    {run.error_message && (
                      <p className="mt-1 max-w-prose text-xs text-alert">{run.error_message}</p>
                    )}
                  </div>
                  <div className="ml-auto flex items-center gap-2">
                    {run.status === 'completed' && (
                      <>
                        <Button
                          as="link"
                          to={`/app/merchant/${merchantId}`}
                          variant="quiet"
                          className="px-3 py-2 text-xs"
                        >
                          View
                        </Button>
                        <Button
                          variant="gold"
                          onClick={() => generate(run.id)}
                          disabled={busyId === run.id}
                          className="px-4 py-2 text-xs"
                        >
                          {busyId === run.id ? 'Generating…' : 'Generate report'}
                        </Button>
                      </>
                    )}
                  </div>
                </li>
              ))}
            </ul>
            {completed.length > 0 && (
              <p className="mt-4 text-xs leading-relaxed text-faint">
                {formatNumber(completed.length)} completed analysis
                {completed.length === 1 ? '' : 'es'}. Each one is a snapshot of the data as it
                stood when it ran, so an older report stays true to what you saw then.
              </p>
            )}
          </Card>
        )}
      </div>
    </AppShell>
  )
}
