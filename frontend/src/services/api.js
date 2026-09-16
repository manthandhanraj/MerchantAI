/**
 * Single place where the frontend talks to the API.
 *
 * In development VITE_API_BASE_URL is empty and requests go to relative
 * '/api/...' paths, which the Vite proxy forwards to the backend.
 * In production set VITE_API_BASE_URL to the deployed API origin.
 */
const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? ''

/**
 * Pull a readable message out of a FastAPI error body.
 *
 * FastAPI returns `{detail: "..."}` for raised HTTPExceptions and
 * `{detail: [{msg, loc}, ...]}` for validation failures. Surfacing the real
 * message means the UI can say "Unknown merchant 'ZZZ'" instead of "500".
 */
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

async function request(path, { signal, method = 'GET', body } = {}) {
  const response = await fetch(`${BASE_URL}${path}`, {
    signal,
    method,
    ...(body === undefined
      ? {}
      : { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
  })

  if (!response.ok) {
    let message = `Request failed (${response.status})`
    try {
      message = extractDetail(await response.json(), message)
    } catch {
      // Body was not JSON; the status-code message is the best we have.
    }
    throw new Error(message)
  }

  return response.json()
}

export function getHealth(options) {
  return request('/api/health', options)
}

export function getMerchants(options) {
  return request('/api/merchants', options)
}

/**
 * Dashboard metrics for one merchant over an optional date range.
 * Omitted dates mean "the merchant's full history".
 */
export function getDashboard({ merchantId, start, end }, options) {
  const params = new URLSearchParams({ merchant_id: merchantId })
  if (start) params.set('start', start)
  if (end) params.set('end', end)
  return request(`/api/dashboard?${params.toString()}`, options)
}

/** Prioritised High / Medium / Low actions for one merchant. */
export function getActionPlan({ merchantId, start, end }, options) {
  const params = new URLSearchParams({ merchant_id: merchantId })
  if (start) params.set('start', start)
  if (end) params.set('end', end)
  return request(`/api/action-plan?${params.toString()}`, options)
}

/** Explainable business findings for one merchant. */
export function getInsights({ merchantId, start, end }, options) {
  const params = new URLSearchParams({ merchant_id: merchantId })
  if (start) params.set('start', start)
  if (end) params.set('end', end)
  return request(`/api/insights?${params.toString()}`, options)
}

/** Short-term projection for one merchant. */
export function getForecast({ merchantId, start, end }, options) {
  const params = new URLSearchParams({ merchant_id: merchantId })
  if (start) params.set('start', start)
  if (end) params.set('end', end)
  return request(`/api/forecast?${params.toString()}`, options)
}

/** Assistant configuration, so the UI can show the right state. */
export function getAssistantStatus(options) {
  return request('/api/assistant/status', options)
}

/** Ask the assistant a question about one merchant. */
export function askAssistant({ merchantId, question, start, end }, options) {
  return request('/api/assistant/ask', {
    ...options,
    method: 'POST',
    body: { merchant_id: merchantId, question, start: start || null, end: end || null },
  })
}
