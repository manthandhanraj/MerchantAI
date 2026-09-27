/**
 * Built-in accounts, as the browser sees them.
 *
 * Used when no Supabase project is configured. The backend owns everything
 * that matters: it hashes the password, signs the token and checks that token
 * on every request. The browser only keeps the signed token it was given and
 * sends it back — it never sees a password hash, and it never decides who a
 * user is.
 *
 * "Remember me" chooses where the token lives: localStorage survives a browser
 * restart, sessionStorage ends with the tab. Every storage access is guarded,
 * because storage throws in private browsing rather than returning null.
 */
import { isRemembered } from './supabase'

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? ''
const SESSION_KEY = 'merchantai.session'

/** Fired when the backend rejects the token, so the app can sign out cleanly. */
export const UNAUTHORIZED_EVENT = 'merchantai:unauthorized'

function stores() {
  try {
    return [window.localStorage, window.sessionStorage]
  } catch {
    return []
  }
}

/** Decode a JWT payload without verifying it — for reading `exp` only. */
function payloadOf(token) {
  try {
    const part = token.split('.')[1]
    const json = atob(part.replace(/-/g, '+').replace(/_/g, '/'))
    return JSON.parse(json)
  } catch {
    return null
  }
}

function isExpired(session) {
  const exp = session?.expires_at ?? payloadOf(session?.access_token)?.exp
  // A few seconds early, so a request is not sent with a token that expires
  // on the way to the server.
  return !exp || exp * 1000 <= Date.now() + 5000
}

/** The stored session, or null if absent, unreadable or expired. */
export function readSession() {
  for (const store of stores()) {
    try {
      const raw = store.getItem(SESSION_KEY)
      if (!raw) continue
      const session = JSON.parse(raw)
      if (session?.access_token && !isExpired(session)) return session
      store.removeItem(SESSION_KEY)
    } catch {
      // Corrupt entry: ignore it and fall through to signed out.
    }
  }
  return null
}

export function writeSession(session) {
  const remember = isRemembered()
  try {
    const [persistent, temporary] = [window.localStorage, window.sessionStorage]
    const target = remember ? persistent : temporary
    const other = remember ? temporary : persistent
    target.setItem(SESSION_KEY, JSON.stringify(session))
    other.removeItem(SESSION_KEY)
  } catch {
    // Storage is blocked: the session lasts until the page reloads.
  }
}

export function clearSession() {
  for (const store of stores()) {
    try {
      store.removeItem(SESSION_KEY)
    } catch {
      // Already unreachable.
    }
  }
}

export function currentToken() {
  return readSession()?.access_token ?? null
}

// --------------------------------------------------------------------------
async function call(path, { method = 'GET', body, token } = {}) {
  let response
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      method,
      headers: {
        ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch {
    throw new Error('Could not reach the server. Check that MerchantAI is running and try again.')
  }

  if (response.status === 204) return null

  let data = null
  try {
    data = await response.json()
  } catch {
    // No JSON body.
  }

  if (!response.ok) {
    // Every route called from here exists on a current server, so a 404 means
    // the server predates built-in accounts — "Not Found" would not say that.
    if (response.status === 404) throw new Error(OUTDATED_SERVER)
    const detail = typeof data?.detail === 'string' ? data.detail : null
    throw new Error(detail || `Request failed (${response.status}).`)
  }
  return data
}

export const OUTDATED_SERVER =
  'This MerchantAI server is running an older version without accounts. Restart it ' +
  '(python runner.py) or redeploy the latest code, then try again.'

export function signUpRequest({ email, password, fullName }) {
  return call('/api/auth/signup', {
    method: 'POST',
    body: { email: email.trim(), password, full_name: (fullName ?? '').trim() || null },
  })
}

export function signInRequest({ email, password }) {
  return call('/api/auth/login', { method: 'POST', body: { email: email.trim(), password } })
}

export function changePasswordRequest(password) {
  return call('/api/auth/password', { method: 'POST', body: { password }, token: currentToken() })
}

export function deleteAccountRequest() {
  return call('/api/auth/account', { method: 'DELETE', token: currentToken() })
}

export function fetchDemoCredentials() {
  return call('/api/auth/demo')
}
