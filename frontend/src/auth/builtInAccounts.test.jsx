/**
 * Built-in accounts in the browser — the mode used when no Supabase project is
 * configured.
 *
 * `fetch` is replaced with a small fake backend, so these exercise the real
 * AuthProvider, the real session storage and the real pages end to end: create
 * an account, land in a fresh workspace, sign out, sign back in, and have the
 * session survive a reload — or not, when "remember me" is off.
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { AppRoutes } from '../App'
import { AuthProvider, useAuth } from './AuthProvider'
import { UNAUTHORIZED_EVENT, readSession } from '../lib/localAuth'

// No Supabase project: the app must use built-in accounts.
vi.mock('../lib/supabase', async () => {
  let remember = true
  return {
    isSupabaseConfigured: false,
    getSupabase: () => null,
    friendlyAuthError: (error) => String(error?.message ?? error),
    isRemembered: () => remember,
    setRemembered: (value) => {
      remember = value
    },
    getAccessToken: async () => {
      const { currentToken } = await import('../lib/localAuth')
      return currentToken()
    },
  }
})

// The workspace screens are covered elsewhere; here they only need to render.
vi.mock('../services/privateApi', () => ({
  ApiError: class extends Error {},
  getMe: vi.fn(async () => ({
    profile: { full_name: 'Riya Sharma' },
    merchant_count: 0,
    needs_onboarding: true,
    is_demo: false,
    read_only: false,
    persistent_storage: true,
    auth_mode: 'local',
  })),
  listMerchants: vi.fn(async () => ({ count: 0, merchants: [] })),
  createMerchant: vi.fn(),
  updateMe: vi.fn(),
  deleteMerchant: vi.fn(),
}))

// ---- a fake backend ------------------------------------------------------
const accounts = new Map()
let demoAvailable = true
// How /api/auth/demo answers the next requests: 'ok', 'down' (network
// failure) or 'outdated' (a server from before accounts existed: 404).
let demoEndpoint = []

function jwtFor(user, expiresInSeconds = 3600) {
  const exp = Math.floor(Date.now() / 1000) + expiresInSeconds
  const payload = btoa(JSON.stringify({ sub: user.id, exp }))
  return { token: `header.${payload}.signature`, exp }
}

function sessionFor(user) {
  const { token, exp } = jwtFor(user)
  return {
    access_token: token,
    token_type: 'bearer',
    expires_at: exp,
    user: { id: user.id, email: user.email, user_metadata: { full_name: user.name } },
  }
}

function reply(status, body) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  })
}

const fetchCalls = []

function fakeFetch(url, options = {}) {
  const body = options.body ? JSON.parse(options.body) : {}
  fetchCalls.push({ url, method: options.method ?? 'GET', body })

  if (url.endsWith('/api/auth/demo')) {
    const behaviour = demoEndpoint.length > 1 ? demoEndpoint.shift() : demoEndpoint[0] ?? 'ok'
    if (behaviour === 'down') return Promise.reject(new TypeError('Failed to fetch'))
    if (behaviour === 'outdated') return reply(404, { detail: 'Not Found' })
    return reply(200, demoAvailable
      ? { available: true, email: 'demo@merchantai.app', password: 'merchant-demo-2026' }
      : { available: false })
  }
  if (url.endsWith('/api/auth/signup')) {
    const email = body.email.toLowerCase()
    if (accounts.has(email)) {
      return reply(409, { detail: 'An account already exists for that email. Try signing in instead.' })
    }
    const user = { id: `u-${accounts.size + 1}`, email, name: body.full_name, password: body.password }
    accounts.set(email, user)
    return reply(201, sessionFor(user))
  }
  if (url.endsWith('/api/auth/login')) {
    const user = accounts.get(String(body.email).toLowerCase())
    if (!user || user.password !== body.password) {
      return reply(401, {
        detail: 'That email and password combination did not work. Check both and try again.',
      })
    }
    return reply(200, sessionFor(user))
  }
  return reply(404, { detail: 'not found' })
}

function renderApp(path) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  accounts.clear()
  fetchCalls.length = 0
  demoAvailable = true
  demoEndpoint = []
  window.localStorage.clear()
  window.sessionStorage.clear()
  vi.stubGlobal('fetch', vi.fn(fakeFetch))
})

afterEach(() => {
  vi.unstubAllGlobals()
})

async function fillSignup(user, { name = 'Riya Sharma', email = 'riya@example.com', password = 'bakery2026' } = {}) {
  await user.type(screen.getByLabelText(/your name/i), name)
  await user.type(screen.getByLabelText(/^email$/i), email)
  await user.type(screen.getByLabelText(/^password$/i), password)
  await user.type(screen.getByLabelText(/confirm password/i), password)
  await user.click(screen.getByLabelText(/stays private to my account/i))
}

// ==========================================================================
describe('the login page offers a way in', () => {
  it('always shows "Create new account"', async () => {
    renderApp('/login')
    expect(await screen.findByRole('link', { name: /create new account/i })).toHaveAttribute(
      'href',
      '/signup',
    )
  })

  it('shows the demo credentials the backend actually uses', async () => {
    renderApp('/login')
    expect(await screen.findByText('merchant-demo-2026')).toBeInTheDocument()
    expect(screen.getByText('demo@merchantai.app')).toBeInTheDocument()
    expect(fetchCalls.some((c) => c.url.endsWith('/api/auth/demo'))).toBe(true)
  })

  it('hides the demo section when the backend offers none', async () => {
    demoAvailable = false
    renderApp('/login')
    await screen.findByRole('link', { name: /create new account/i })
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: /try demo account/i })).not.toBeInTheDocument(),
    )
  })
})

describe('the demo never silently disappears', () => {
  const DEMO_USER = {
    id: 'u-demo',
    email: 'demo@merchantai.app',
    name: 'MerchantAI Demo',
    password: 'merchant-demo-2026',
  }

  beforeEach(() => {
    accounts.set(DEMO_USER.email, DEMO_USER)
  })

  it('keeps the demo button when the server cannot be reached, and says why', async () => {
    demoEndpoint = ['down']
    renderApp('/login')

    expect(await screen.findByRole('alert')).toHaveTextContent(/could not reach the server/i)
    expect(screen.getByRole('button', { name: /try demo account/i })).toBeEnabled()
    expect(screen.getByRole('link', { name: /create new account/i })).toBeInTheDocument()
  })

  it('names an out-of-date server instead of saying "Not Found"', async () => {
    demoEndpoint = ['outdated']
    renderApp('/login')

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/older version/i)
    expect(alert).not.toHaveTextContent(/not found/i)
    expect(screen.getByRole('button', { name: /try demo account/i })).toBeEnabled()
  })

  it('opens the demo once the server answers', async () => {
    demoEndpoint = ['down', 'ok']
    const user = userEvent.setup()
    renderApp('/login')
    await screen.findByRole('alert')

    await user.click(screen.getByRole('button', { name: /try demo account/i }))

    await waitFor(() =>
      expect(fetchCalls.some((c) => c.url.endsWith('/api/auth/login'))).toBe(true),
    )
    const login = fetchCalls.find((c) => c.url.endsWith('/api/auth/login'))
    expect(login.body).toEqual({ email: DEMO_USER.email, password: DEMO_USER.password })
    await waitFor(() => expect(readSession()?.user.email).toBe(DEMO_USER.email))
  })

  it('offers the demo from the sign-up page too, as a real sign-in', async () => {
    const user = userEvent.setup()
    renderApp('/signup')

    expect(screen.getByRole('button', { name: /create account/i })).toBeInTheDocument()
    const demoLinks = screen.getAllByRole('link', { name: /try demo account/i })
    expect(demoLinks.length).toBeGreaterThan(0)
    await user.click(demoLinks[demoLinks.length - 1])

    await waitFor(() => expect(readSession()?.user.email).toBe(DEMO_USER.email))
    const logins = fetchCalls.filter((c) => c.url.endsWith('/api/auth/login'))
    expect(logins).toHaveLength(1)
    expect(logins[0].body).toEqual({ email: DEMO_USER.email, password: DEMO_USER.password })
  })
})

describe('creating an account', () => {
  it('creates the account and opens a fresh workspace', async () => {
    const user = userEvent.setup()
    renderApp('/signup')

    await fillSignup(user)
    await user.click(screen.getByRole('button', { name: /create account/i }))

    // A brand-new account has no business yet, so it lands on onboarding.
    expect(await screen.findByLabelText(/business name/i)).toBeInTheDocument()

    const signupCall = fetchCalls.find((c) => c.url.endsWith('/api/auth/signup'))
    expect(signupCall.method).toBe('POST')
    expect(signupCall.body).toMatchObject({ email: 'riya@example.com', full_name: 'Riya Sharma' })
  })

  it('stores a signed token, never the password', async () => {
    const user = userEvent.setup()
    renderApp('/signup')
    await fillSignup(user)
    await user.click(screen.getByRole('button', { name: /create account/i }))
    await screen.findByLabelText(/business name/i)

    const stored = JSON.stringify({ ...window.localStorage }) + JSON.stringify({ ...window.sessionStorage })
    expect(stored).not.toContain('bakery2026')
    expect(readSession()?.access_token).toBeTruthy()
  })

  it('explains a duplicate account in plain words', async () => {
    accounts.set('riya@example.com', { id: 'u-0', email: 'riya@example.com', password: 'x' })
    const user = userEvent.setup()
    renderApp('/signup')

    await fillSignup(user)
    await user.click(screen.getByRole('button', { name: /create account/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/already exists/i)
  })

  it('reports an unreachable server instead of hanging', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new TypeError('Failed to fetch'))))
    const user = userEvent.setup()
    renderApp('/signup')

    await fillSignup(user)
    await user.click(screen.getByRole('button', { name: /create account/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/could not reach the server/i)
  })
})

describe('signing in and out', () => {
  beforeEach(() => {
    accounts.set('riya@example.com', {
      id: 'u-1',
      email: 'riya@example.com',
      name: 'Riya Sharma',
      password: 'bakery2026',
    })
  })

  async function signIn(user, password = 'bakery2026') {
    await user.type(await screen.findByLabelText(/email or account id/i), 'riya@example.com')
    await user.type(screen.getByLabelText(/^password$/i), password)
    await user.click(screen.getByRole('button', { name: /^sign in$/i }))
  }

  it('signs in and reaches the workspace', async () => {
    const user = userEvent.setup()
    renderApp('/login')
    await signIn(user)
    expect(await screen.findByLabelText(/business name/i)).toBeInTheDocument()
  })

  it('refuses a wrong password', async () => {
    const user = userEvent.setup()
    renderApp('/login')
    await signIn(user, 'wrong-password1')
    expect(await screen.findByRole('alert')).toHaveTextContent(/did not work/i)
    expect(readSession()).toBeNull()
  })

  it('keeps a remembered session across a reload', async () => {
    const user = userEvent.setup()
    const { unmount } = renderApp('/login')
    await signIn(user)
    await screen.findByLabelText(/business name/i)

    unmount()
    renderApp('/app')
    expect(await screen.findByLabelText(/business name/i)).toBeInTheDocument()
    expect(window.localStorage.getItem('merchantai.session')).toBeTruthy()
  })

  it('keeps an unremembered session for this tab only', async () => {
    const user = userEvent.setup()
    renderApp('/login')

    await user.click(await screen.findByLabelText(/remember me/i))
    await signIn(user)
    await screen.findByLabelText(/business name/i)

    expect(window.sessionStorage.getItem('merchantai.session')).toBeTruthy()
    expect(window.localStorage.getItem('merchantai.session')).toBeNull()
  })

  it('discards an expired session instead of trusting it', () => {
    const { token } = jwtFor({ id: 'u-1' }, -60)
    window.localStorage.setItem(
      'merchantai.session',
      JSON.stringify({ access_token: token, expires_at: Math.floor(Date.now() / 1000) - 60 }),
    )
    expect(readSession()).toBeNull()
    expect(window.localStorage.getItem('merchantai.session')).toBeNull()
  })

  it('signs out and clears the stored session', async () => {
    const user = userEvent.setup()

    function Probe() {
      const { session, signOut } = useAuth()
      return (
        <>
          <p>{session ? 'signed in' : 'signed out'}</p>
          <button type="button" onClick={signOut}>
            Sign out
          </button>
        </>
      )
    }

    window.localStorage.setItem(
      'merchantai.session',
      JSON.stringify(sessionFor({ id: 'u-1', email: 'riya@example.com', name: 'Riya' })),
    )
    render(
      <MemoryRouter>
        <AuthProvider>
          <Probe />
        </AuthProvider>
      </MemoryRouter>,
    )
    expect(screen.getByText('signed in')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /sign out/i }))
    expect(await screen.findByText('signed out')).toBeInTheDocument()
    expect(readSession()).toBeNull()
  })

  it('ends the session when the server rejects the token', async () => {
    window.localStorage.setItem(
      'merchantai.session',
      JSON.stringify(sessionFor({ id: 'u-1', email: 'riya@example.com', name: 'Riya' })),
    )

    function Probe() {
      const { session } = useAuth()
      return <p>{session ? 'signed in' : 'signed out'}</p>
    }
    render(
      <MemoryRouter>
        <AuthProvider>
          <Probe />
        </AuthProvider>
      </MemoryRouter>,
    )
    expect(screen.getByText('signed in')).toBeInTheDocument()

    window.dispatchEvent(new Event(UNAUTHORIZED_EVENT))
    await waitFor(() => expect(screen.getByText('signed out')).toBeInTheDocument())
    expect(readSession()).toBeNull()
  })
})

describe('password recovery without an email service', () => {
  it('says plainly that reset emails are unavailable', async () => {
    renderApp('/forgot-password')
    expect(await screen.findByText(/reset by email is not available here/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /send reset link/i })).not.toBeInTheDocument()
  })
})
