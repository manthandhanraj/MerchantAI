/**
 * Calls to the private workspace API.
 *
 * Every request carries the current Supabase access token in an Authorization
 * header. Nothing here sends a user id: the backend derives the caller from the
 * verified token, so a client that lied about who it was would change nothing.
 *
 * The token is read from the Supabase client at call time rather than captured
 * once, so a token refreshed in the background is picked up immediately.
 */
import { UNAUTHORIZED_EVENT } from '../lib/localAuth'
import { getAccessToken } from '../lib/supabase'

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? ''

class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

export { ApiError }

function extractDetail(body, fallback) {
  const detail = body?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0]
    if (typeof first?.msg === 'string') {
      const field = Array.isArray(first.loc) ? first.loc[first.loc.length - 1] : null
      return field ? `${field}: ${first.msg}` : first.msg
    }
  }
  return fallback
}

async function request(path, { method = 'GET', body, form, signal } = {}) {
  const token = await getAccessToken()
  if (!token) {
    throw new ApiError('Your session has ended. Sign in again to continue.', 401)
  }

  const headers = { Authorization: `Bearer ${token}` }
  let payload
  if (form) {
    // Let the browser set the multipart boundary itself.
    payload = form
  } else if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
    payload = JSON.stringify(body)
  }

  const response = await fetch(`${BASE_URL}${path}`, { method, headers, body: payload, signal })

  if (response.status === 204) return null

  if (!response.ok) {
    let message = `Request failed (${response.status})`
    try {
      message = extractDetail(await response.json(), message)
    } catch {
      // Not JSON; the status message is the best available.
    }
    // An expired token, or an account that no longer exists: end the session
    // so the user is sent to sign in instead of seeing a page of errors.
    if (response.status === 401) {
      window.dispatchEvent(new Event(UNAUTHORIZED_EVENT))
    }
    throw new ApiError(message, response.status)
  }

  return response.json()
}

// ------------------------------------------------------------------ account
export const getMe = (options) => request('/api/me', options)
export const updateMe = (fullName) =>
  request('/api/me', { method: 'PATCH', body: { full_name: fullName } })

// ---------------------------------------------------------------- merchants
export const listMerchants = (options) => request('/api/my/merchants', options)
export const createMerchant = (payload) =>
  request('/api/my/merchants', { method: 'POST', body: payload })
export const getMerchant = (id, options) => request(`/api/my/merchants/${id}`, options)
export const updateMerchant = (id, payload) =>
  request(`/api/my/merchants/${id}`, { method: 'PATCH', body: payload })
export const deleteMerchant = (id) => request(`/api/my/merchants/${id}`, { method: 'DELETE' })

// ------------------------------------------------------------------ uploads
export const getUploadSchema = (merchantId, options) =>
  request(`/api/my/merchants/${merchantId}/uploads/schema`, options)

export function validateUpload(merchantId, { file, uploadType, mapping }) {
  const form = new FormData()
  form.append('file', file)
  form.append('upload_type', uploadType)
  if (mapping) form.append('mapping', JSON.stringify(mapping))
  return request(`/api/my/merchants/${merchantId}/uploads/validate`, { method: 'POST', form })
}

export function createUpload(merchantId, { file, uploadType, mapping, idempotencyKey }) {
  const form = new FormData()
  form.append('file', file)
  form.append('upload_type', uploadType)
  if (mapping) form.append('mapping', JSON.stringify(mapping))
  if (idempotencyKey) form.append('idempotency_key', idempotencyKey)
  return request(`/api/my/merchants/${merchantId}/uploads`, { method: 'POST', form })
}

export const listUploads = (merchantId, options) =>
  request(`/api/my/merchants/${merchantId}/uploads`, options)

// ----------------------------------------------------------------- analyses
export const runAnalysis = (merchantId, payload = {}) =>
  request(`/api/my/merchants/${merchantId}/analyses`, { method: 'POST', body: payload })
export const listAnalyses = (merchantId, options) =>
  request(`/api/my/merchants/${merchantId}/analyses`, options)

// ---------------------------------------------------------------- dashboard
const withAnalysis = (path, analysisId) =>
  analysisId ? `${path}?analysis_id=${encodeURIComponent(analysisId)}` : path

export const getPrivateDashboard = (merchantId, analysisId, options) =>
  request(withAnalysis(`/api/my/merchants/${merchantId}/dashboard`, analysisId), options)
export const getPrivateInsights = (merchantId, analysisId, options) =>
  request(withAnalysis(`/api/my/merchants/${merchantId}/insights`, analysisId), options)
export const getPrivateActionPlan = (merchantId, analysisId, options) =>
  request(withAnalysis(`/api/my/merchants/${merchantId}/action-plan`, analysisId), options)
export const getPrivateForecast = (merchantId, analysisId, options) =>
  request(withAnalysis(`/api/my/merchants/${merchantId}/forecast`, analysisId), options)

// ---------------------------------------------------------------- assistant
export const getPrivateAssistantStatus = (options) => request('/api/my/assistant/status', options)
export const askPrivateAssistant = (merchantId, question) =>
  request(`/api/my/merchants/${merchantId}/assistant/ask`, {
    method: 'POST',
    body: { question },
  })

// ------------------------------------------------------------------ reports
export const createReport = (merchantId, analysisId) =>
  request(`/api/my/merchants/${merchantId}/reports`, {
    method: 'POST',
    body: { analysis_id: analysisId ?? null },
  })
export const listReports = (merchantId, options) =>
  request(`/api/my/merchants/${merchantId}/reports`, options)
export const getReportDownloadUrl = (merchantId, reportId) =>
  request(`/api/my/merchants/${merchantId}/reports/${reportId}/download`)
export const deleteReport = (merchantId, reportId) =>
  request(`/api/my/merchants/${merchantId}/reports/${reportId}`, { method: 'DELETE' })
