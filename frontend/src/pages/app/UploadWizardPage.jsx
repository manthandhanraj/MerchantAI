/**
 * Guided upload: choose a file, confirm the column mapping, fix anything the
 * validator flags, then store it.
 *
 * The validation step never writes anything. A file is only stored once the
 * backend has confirmed every row can be read, so a merchant's workspace cannot
 * end up holding a file the product would then refuse to analyse.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'

import { AppShell } from '../../components/AppShell'
import {
  Alert,
  Button,
  Card,
  Field,
  PageHeader,
  Select,
  Spinner,
} from '../../components/ui'
import {
  createUpload,
  getMerchant,
  getUploadSchema,
  listUploads,
  runAnalysis,
  validateUpload,
} from '../../services/privateApi'
import { formatNumber } from '../../utils/format'
import { downloadTemplate } from '../../utils/templates'

// The stages the request actually passes through. Each one is set when the
// corresponding call starts, so the label always describes real work rather
// than counting down a timer.
const ANALYSIS_STAGES = [
  'Reading your stored files',
  'Validating the dataset',
  'Calculating metrics',
  'Generating insights and the plan',
  'Preparing your dashboard',
]

const TYPE_LABEL = { sales: 'Sales data', customers: 'Customer data' }
const TYPE_BLURB = {
  sales: 'One row per product per day: what sold, what it earned and what it cost.',
  customers: 'One row per day: how many people bought, and how many were returning.',
}

function newIdempotencyKey() {
  // Stable for one submission, so a retry after a dropped connection resolves
  // to the same upload instead of creating a second one.
  return `up-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
}

export default function UploadWizardPage() {
  const { id: merchantId } = useParams()
  const navigate = useNavigate()
  const location = useLocation()
  const fileInput = useRef(null)
  const justCreated = location.state?.justCreated

  const [merchant, setMerchant] = useState(null)
  const [schema, setSchema] = useState(null)
  const [existing, setExisting] = useState([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(null)

  const [uploadType, setUploadType] = useState('sales')
  const [file, setFile] = useState(null)
  const [check, setCheck] = useState(null)
  const [mapping, setMapping] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [stored, setStored] = useState(null)
  const [dragging, setDragging] = useState(false)
  const [analysing, setAnalysing] = useState(false)
  const [stage, setStage] = useState(null)
  const [idempotencyKey, setIdempotencyKey] = useState(newIdempotencyKey)

  const refresh = useCallback(
    async (signal) => {
      setLoading(true)
      setLoadError(null)
      try {
        const [merchantBody, schemaBody, uploadsBody] = await Promise.all([
          getMerchant(merchantId, { signal }),
          getUploadSchema(merchantId, { signal }),
          listUploads(merchantId, { signal }),
        ])
        if (signal?.aborted) return
        setMerchant(merchantBody.merchant)
        setSchema(schemaBody)
        setExisting(uploadsBody.uploads ?? [])
        // Nudge the merchant towards whichever file is still missing.
        const hasSales = (uploadsBody.uploads ?? []).some(
          (u) => u.upload_type === 'sales' && u.status === 'ready',
        )
        if (hasSales) setUploadType('customers')
      } catch (caught) {
        if (!signal?.aborted) setLoadError(caught.message)
      } finally {
        if (!signal?.aborted) setLoading(false)
      }
    },
    [merchantId],
  )

  useEffect(() => {
    const controller = new AbortController()
    refresh(controller.signal)
    return () => controller.abort()
  }, [refresh])

  const fields = schema?.types?.[uploadType] ?? []
  const maxMb = schema ? Math.round(schema.max_bytes / (1024 * 1024)) : 10

  const ready = useMemo(
    () => ({
      sales: existing.some((u) => u.upload_type === 'sales' && u.status === 'ready'),
      customers: existing.some((u) => u.upload_type === 'customers' && u.status === 'ready'),
    }),
    [existing],
  )

  function reset() {
    setFile(null)
    setCheck(null)
    setMapping(null)
    setError(null)
    setStored(null)
    setIdempotencyKey(newIdempotencyKey())
    if (fileInput.current) fileInput.current.value = ''
  }

  async function handleFile(nextFile) {
    if (!nextFile) return
    setError(null)
    setStored(null)

    if (!nextFile.name.toLowerCase().endsWith('.csv')) {
      setError('Only .csv files are supported. Export your spreadsheet as CSV and try again.')
      return
    }
    if (schema && nextFile.size > schema.max_bytes) {
      setError(`That file is ${(nextFile.size / 1024 / 1024).toFixed(1)} MB, above the ${maxMb} MB limit.`)
      return
    }

    setFile(nextFile)
    setBusy(true)
    try {
      const result = await validateUpload(merchantId, { file: nextFile, uploadType })
      setCheck(result)
      setMapping(result.mapping)
    } catch (caught) {
      setError(caught.message)
      setCheck(null)
    } finally {
      setBusy(false)
    }
  }

  async function revalidate(nextMapping) {
    setMapping(nextMapping)
    if (!file) return
    setBusy(true)
    setError(null)
    try {
      const result = await validateUpload(merchantId, {
        file,
        uploadType,
        mapping: nextMapping,
      })
      setCheck(result)
    } catch (caught) {
      setError(caught.message)
    } finally {
      setBusy(false)
    }
  }

  async function confirm() {
    if (!file || !check?.ok) return
    setBusy(true)
    setError(null)
    try {
      const result = await createUpload(merchantId, {
        file,
        uploadType,
        mapping,
        idempotencyKey,
      })
      setStored(result.upload)
      const uploadsBody = await listUploads(merchantId)
      setExisting(uploadsBody.uploads ?? [])
    } catch (caught) {
      setError(caught.message)
    } finally {
      setBusy(false)
    }
  }

  async function analyseNow() {
    setAnalysing(true)
    setError(null)
    setStage(0)

    // The backend runs the pipeline in one call, so the client cannot observe
    // each step. These labels advance while the request is genuinely in flight
    // and stop the moment it settles — they never outlive the real work, and
    // the final state comes from the response, not from a timer.
    const ticker = setInterval(
      () => setStage((current) => (current === null ? 0 : Math.min(current + 1, ANALYSIS_STAGES.length - 1))),
      900,
    )

    try {
      await runAnalysis(merchantId, { idempotency_key: newIdempotencyKey() })
      clearInterval(ticker)
      navigate(`/app/merchant/${merchantId}`, { replace: true })
    } catch (caught) {
      clearInterval(ticker)
      setError(caught.message)
      setAnalysing(false)
      setStage(null)
    }
  }

  function downloadErrors() {
    const rows = [['row', 'column', 'value', 'problem']]
    for (const item of check.errors ?? []) {
      rows.push([item.row, item.column, item.value, item.problem])
    }
    const csv = rows
      .map((row) => row.map((cell) => `"${String(cell).replaceAll('"', '""')}"`).join(','))
      .join('\n')
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }))
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `${uploadType}-validation-errors.csv`
    anchor.click()
    URL.revokeObjectURL(url)
  }

  if (loading) {
    return (
      <AppShell activeMerchantId={merchantId}>
        <Spinner label="Preparing the upload wizard…" />
      </AppShell>
    )
  }

  if (loadError) {
    return (
      <AppShell activeMerchantId={merchantId}>
        <Alert
          tone="error"
          title="Could not open the upload wizard"
          action={
            <Button variant="ghost" onClick={() => refresh()}>
              Try again
            </Button>
          }
        >
          {loadError}
        </Alert>
      </AppShell>
    )
  }

  const bothReady = ready.sales && ready.customers

  return (
    <AppShell activeMerchantId={merchantId}>
      {justCreated && (
        <div className="mb-6">
          <Alert tone="success" title={`${justCreated} is ready`}>
            One more step: upload your data so MerchantAI has something real to analyse.
          </Alert>
        </div>
      )}

      <PageHeader
        eyebrow={merchant?.name}
        title="Upload your business data"
        description="Two files are needed: daily sales per product, and daily customer counts. Nothing is stored until it passes validation."
      >
        <Button as="link" to={`/app/merchant/${merchantId}`} variant="ghost">
          Back to dashboard
        </Button>
      </PageHeader>

      {/* ---- progress ------------------------------------------------- */}
      <div className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-2">
        {['sales', 'customers'].map((type) => (
          <button
            key={type}
            type="button"
            onClick={() => {
              setUploadType(type)
              reset()
            }}
            className={[
              'rounded-2xl border p-4 text-left transition sm:p-5',
              uploadType === type
                ? 'border-sage/40 bg-gradient-to-b from-[#16201a] to-raised'
                : 'border-white/8 bg-gradient-to-b from-raised to-surface hover:border-white/15',
            ].join(' ')}
            aria-pressed={uploadType === type}
          >
            <div className="flex items-center gap-2">
              <span
                aria-hidden="true"
                className={[
                  'grid h-5 w-5 place-items-center rounded-full border text-[0.65rem] font-semibold',
                  ready[type]
                    ? 'border-sage/40 bg-sage/15 text-sage'
                    : 'border-white/15 text-faint',
                ].join(' ')}
              >
                {ready[type] ? '✓' : ''}
              </span>
              <span className="text-sm font-semibold text-cream">{TYPE_LABEL[type]}</span>
              {ready[type] && <span className="ml-auto text-xs text-sage">Uploaded</span>}
            </div>
            <p className="mt-2 text-xs leading-relaxed text-muted">{TYPE_BLURB[type]}</p>
          </button>
        ))}
      </div>

      {error && (
        <div className="mt-5">
          <Alert tone="error" title="Upload problem">
            {error}
          </Alert>
        </div>
      )}

      {/* ---- stored ---------------------------------------------------- */}
      {stored ? (
        <Card className="mt-5">
          <Alert tone="success" title={`${TYPE_LABEL[uploadType]} stored`}>
            {formatNumber(stored.row_count)} rows saved from{' '}
            <span className="font-medium">{stored.original_filename}</span>. Your file is private to
            your account.
          </Alert>

          <div className="mt-5 flex flex-wrap gap-3">
            {bothReady ? (
              <Button onClick={analyseNow} disabled={analysing}>
                {analysing ? 'Analysing…' : 'Analyse my business'}
              </Button>
            ) : (
              <Button
                onClick={() => {
                  setUploadType(uploadType === 'sales' ? 'customers' : 'sales')
                  reset()
                }}
              >
                Upload the {uploadType === 'sales' ? 'customer' : 'sales'} file next
              </Button>
            )}
            <Button variant="ghost" onClick={reset}>
              Upload another file
            </Button>
          </div>

          {analysing && (
            <ul className="mt-5 space-y-2" role="status" aria-live="polite">
              {ANALYSIS_STAGES.map((label, index) => {
                const done = stage !== null && index < stage
                const active = stage === index
                return (
                  <li
                    key={label}
                    className={`flex items-center gap-2.5 text-sm ${
                      done ? 'text-sage' : active ? 'text-cream' : 'text-faint'
                    }`}
                  >
                    <span aria-hidden="true" className="w-4 shrink-0 text-center">
                      {done ? '✓' : active ? (
                        <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-white/15 border-t-sage align-middle" />
                      ) : '○'}
                    </span>
                    {label}
                  </li>
                )
              })}
            </ul>
          )}

          {!bothReady && (
            <p className="mt-4 text-xs leading-relaxed text-faint">
              Both files are needed before an analysis can run. Customer counts are kept per day so
              they cannot be double counted, and there is no honest way to derive them from the
              sales file.
            </p>
          )}
        </Card>
      ) : (
        <>
          {/* ---- drop zone --------------------------------------------- */}
          <Card className="mt-5">
            <h2 className="text-sm font-semibold text-cream">
              Choose your {TYPE_LABEL[uploadType].toLowerCase()} file
            </h2>

            <div
              onDragOver={(event) => {
                event.preventDefault()
                setDragging(true)
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={(event) => {
                event.preventDefault()
                setDragging(false)
                handleFile(event.dataTransfer.files?.[0])
              }}
              className={[
                'mt-4 rounded-2xl border-2 border-dashed p-8 text-center transition',
                dragging ? 'border-sage/60 bg-sage/5' : 'border-white/12 bg-white/3',
              ].join(' ')}
            >
              <p className="text-sm text-muted">
                Drag a CSV here, or{' '}
                <button
                  type="button"
                  onClick={() => fileInput.current?.click()}
                  className="font-medium text-sage underline"
                >
                  browse for one
                </button>
                .
              </p>
              <p className="mt-2 text-xs text-faint">
                CSV only, up to {maxMb} MB and {formatNumber(schema?.max_rows ?? 0)} rows.
              </p>
              <button
                type="button"
                onClick={() => downloadTemplate(uploadType)}
                className="mt-3 text-xs font-medium text-sage underline"
              >
                Download a sample {TYPE_LABEL[uploadType].toLowerCase()} template
              </button>
              <input
                ref={fileInput}
                type="file"
                accept=".csv,text/csv"
                className="sr-only"
                onChange={(event) => handleFile(event.target.files?.[0])}
              />
              {file && (
                <p className="mt-4 text-xs text-cream">
                  Selected: <span className="font-medium">{file.name}</span> (
                  {(file.size / 1024).toFixed(0)} KB)
                </p>
              )}
            </div>

            <details className="mt-4">
              <summary className="cursor-pointer text-xs font-medium text-muted hover:text-cream">
                What columns does this file need?
              </summary>
              <ul className="mt-3 space-y-1.5">
                {fields.map((field) => (
                  <li key={field.name} className="text-xs text-faint">
                    <span className="font-medium text-muted">{field.name}</span> — {field.description}
                  </li>
                ))}
              </ul>
              <p className="mt-3 text-xs text-faint">
                Column names do not have to match exactly. Common spellings are recognised
                automatically, and anything unmatched can be mapped by hand below.
              </p>
            </details>
          </Card>

          {busy && (
            <div className="mt-5">
              <Spinner label="Checking your file…" />
            </div>
          )}

          {/* ---- mapping + validation ---------------------------------- */}
          {check && !busy && (
            <>
              <Card className="mt-5">
                <h2 className="text-sm font-semibold text-cream">Match your columns</h2>
                <p className="mt-1 text-xs text-muted">
                  Confirm each required field points at the right column from your file.
                </p>

                <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
                  {fields.map((field) => (
                    <Field
                      key={field.name}
                      label={field.name}
                      id={`map-${field.name}`}
                      hint={field.description}
                      error={
                        check.unmapped_required?.includes(field.name)
                          ? 'No matching column found — choose one.'
                          : null
                      }
                    >
                      <Select
                        id={`map-${field.name}`}
                        value={mapping?.[field.name] ?? ''}
                        onChange={(event) =>
                          revalidate({
                            ...mapping,
                            [field.name]: event.target.value || null,
                          })
                        }
                      >
                        <option value="">Not mapped</option>
                        {(check.headers ?? []).map((header) => (
                          <option key={header} value={header}>
                            {header}
                          </option>
                        ))}
                      </Select>
                    </Field>
                  ))}
                </div>
              </Card>

              {check.preview?.length > 0 && (
                <Card className="mt-5">
                  <h2 className="text-sm font-semibold text-cream">Preview</h2>
                  <p className="mt-1 text-xs text-muted">
                    The first {check.preview.length} rows, as MerchantAI reads them.
                  </p>
                  <div className="mt-4 overflow-x-auto">
                    <table className="w-full min-w-[640px] text-left text-xs">
                      <thead>
                        <tr className="border-b border-white/10">
                          {fields.map((field) => (
                            <th key={field.name} className="px-2 py-2 font-medium text-faint">
                              {field.name}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {check.preview.map((row, index) => (
                          <tr key={index} className="border-b border-white/5">
                            {fields.map((field) => (
                              <td key={field.name} className="px-2 py-2 tabular-nums text-cream">
                                {row[field.name] ?? '—'}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </Card>
              )}

              {check.warnings?.length > 0 && (
                <div className="mt-5">
                  <Alert tone="warning" title="Worth a look">
                    <ul className="space-y-1">
                      {check.warnings.map((warning) => (
                        <li key={warning}>{warning}</li>
                      ))}
                    </ul>
                  </Alert>
                </div>
              )}

              {check.ok ? (
                <Card className="mt-5">
                  <Alert tone="success" title="Ready to store">
                    {check.messages?.join(' ')}
                  </Alert>
                  <div className="mt-5 flex flex-wrap gap-3">
                    <Button onClick={confirm} disabled={busy}>
                      {busy ? 'Storing…' : `Store this ${TYPE_LABEL[uploadType].toLowerCase()}`}
                    </Button>
                    <Button variant="quiet" onClick={reset}>
                      Choose a different file
                    </Button>
                  </div>
                </Card>
              ) : (
                <Card className="mt-5">
                  <Alert tone="error" title={`${formatNumber(check.error_count)} row(s) need fixing`}>
                    <p>
                      Nothing has been stored. Correct these rows in your file and upload it again —
                      MerchantAI will not guess at a value or drop a row on your behalf.
                    </p>
                    {check.messages?.length > 0 && (
                      <ul className="mt-2 space-y-1">
                        {check.messages.map((message) => (
                          <li key={message}>{message}</li>
                        ))}
                      </ul>
                    )}
                  </Alert>

                  {check.errors?.length > 0 && (
                    <>
                      <div className="mt-4 overflow-x-auto">
                        <table className="w-full min-w-[520px] text-left text-xs">
                          <thead>
                            <tr className="border-b border-white/10">
                              <th className="px-2 py-2 font-medium text-faint">Row</th>
                              <th className="px-2 py-2 font-medium text-faint">Column</th>
                              <th className="px-2 py-2 font-medium text-faint">Value</th>
                              <th className="px-2 py-2 font-medium text-faint">Problem</th>
                            </tr>
                          </thead>
                          <tbody>
                            {check.errors.slice(0, 20).map((item, index) => (
                              <tr key={index} className="border-b border-white/5">
                                <td className="px-2 py-2 tabular-nums text-cream">{item.row}</td>
                                <td className="px-2 py-2 text-muted">{item.column}</td>
                                <td className="px-2 py-2 text-muted">{item.value || '(empty)'}</td>
                                <td className="px-2 py-2 text-alert">{item.problem}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                      {check.error_count > 20 && (
                        <p className="mt-3 text-xs text-faint">
                          Showing the first 20 of {formatNumber(check.error_count)}.
                        </p>
                      )}
                      <div className="mt-4 flex flex-wrap gap-3">
                        <Button variant="ghost" onClick={downloadErrors}>
                          Download the full error list
                        </Button>
                        <Button variant="quiet" onClick={reset}>
                          Choose a different file
                        </Button>
                      </div>
                    </>
                  )}
                </Card>
              )}
            </>
          )}
        </>
      )}

      {/* ---- history ---------------------------------------------------- */}
      {existing.length > 0 && (
        <Card className="mt-8">
          <h2 className="text-sm font-semibold text-cream">Previous uploads</h2>
          <ul className="mt-3 divide-y divide-white/5">
            {existing.map((upload) => (
              <li key={upload.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2.5">
                <span className="text-sm text-cream">{upload.original_filename}</span>
                <span className="text-xs text-faint">{TYPE_LABEL[upload.upload_type]}</span>
                <span className="text-xs text-faint">
                  {formatNumber(upload.row_count)} rows
                </span>
                <span className="ml-auto text-xs text-faint">
                  {String(upload.created_at).slice(0, 10)}
                </span>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </AppShell>
  )
}
