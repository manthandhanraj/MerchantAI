/**
 * Authentication surface: session states, route guards, and the four forms.
 *
 * Supabase itself is mocked. What these assert is our behaviour around it —
 * that a loading session does not bounce a signed-in user to the login page,
 * that a signed-out visitor cannot reach a private route, and that failures are
 * shown in language a person can act on.
 */
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AuthProvider, useAuth } from './AuthProvider'
import { RequireAnon, RequireAuth } from './ProtectedRoute'
import LoginPage from '../pages/auth/LoginPage'
import SignupPage from '../pages/auth/SignupPage'
import ForgotPasswordPage from '../pages/auth/ForgotPasswordPage'

// --- Supabase double -------------------------------------------------------
const authApi = {
  getSession: vi.fn(),
  onAuthStateChange: vi.fn(),
  signInWithPassword: vi.fn(),
  signUp: vi.fn(),
  signOut: vi.fn(),
  resetPasswordForEmail: vi.fn(),
  updateUser: vi.fn(),
}

let configured = true

// One stable object, matching the real module: getSupabase() caches its client,
// and a fresh object per call would re-run the provider's effect endlessly.
const supabaseDouble = { auth: authApi }

vi.mock('./../lib/supabase', () => ({
  get isSupabaseConfigured() {
    return configured
  },
  getSupabase: () => (configured ? supabaseDouble : null),
  getAccessToken: vi.fn(async () => 'token'),
  friendlyAuthError: (error) => String(error?.message ?? error),
  isRemembered: () => true,
  setRemembered: vi.fn(),
}))

vi.mock('./../lib/demo', () => ({
  demoAccount: { email: 'demo@merchantai.app', password: 'demo-pass-1234', available: true },
  useDemoCredentials: () => ({ email: 'demo@merchantai.app', password: 'pw', available: true, offered: true }),
}))

const SESSION = { access_token: 'abc', user: { id: 'u1', email: 'owner@example.com' } }

function setSession(session, { delay = 0 } = {}) {
  authApi.getSession.mockImplementation(
    () =>
      new Promise((resolve) => setTimeout(() => resolve({ data: { session } }), delay)),
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  configured = true
  setSession(null)
  authApi.onAuthStateChange.mockReturnValue({ subscription: { unsubscribe: vi.fn() } })
})

function renderAt(path, element) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>{element}</AuthProvider>
    </MemoryRouter>,
  )
}

const Private = () => <p>Private workspace</p>
const guardedRoutes = (
  <Routes>
    <Route path="/login" element={<p>Login screen</p>} />
    <Route element={<RequireAuth />}>
      <Route path="/app" element={<Private />} />
    </Route>
    <Route element={<RequireAnon />}>
      <Route path="/signup" element={<p>Signup screen</p>} />
    </Route>
  </Routes>
)

// ==========================================================================
describe('session state', () => {
  it('shows a loading state before the session is known', async () => {
    setSession(SESSION, { delay: 50 })
    renderAt('/app', guardedRoutes)

    expect(screen.getByRole('status')).toHaveTextContent(/checking your session/i)
    expect(screen.queryByText('Login screen')).not.toBeInTheDocument()

    await screen.findByText('Private workspace')
  })

  it('does not send a signed-in user to login while the session is still loading', async () => {
    setSession(SESSION, { delay: 40 })
    renderAt('/app', guardedRoutes)

    // The bug this guards: redirecting before getSession resolves.
    expect(screen.queryByText('Login screen')).not.toBeInTheDocument()
    await screen.findByText('Private workspace')
  })

  it('exposes the signed-in user', async () => {
    setSession(SESSION)
    function Probe() {
      const { user, loading } = useAuth()
      return <p>{loading ? 'loading' : (user?.email ?? 'nobody')}</p>
    }
    renderAt('/app', <Probe />)
    expect(await screen.findByText('owner@example.com')).toBeInTheDocument()
  })
})

describe('route guards', () => {
  it('redirects a signed-out visitor away from a private route', async () => {
    setSession(null)
    renderAt('/app', guardedRoutes)
    expect(await screen.findByText('Login screen')).toBeInTheDocument()
    expect(screen.queryByText('Private workspace')).not.toBeInTheDocument()
  })

  it('lets a signed-in user through', async () => {
    setSession(SESSION)
    renderAt('/app', guardedRoutes)
    expect(await screen.findByText('Private workspace')).toBeInTheDocument()
  })

  it('keeps a signed-in user out of the sign-up screen', async () => {
    setSession(SESSION)
    renderAt('/signup', guardedRoutes)
    await waitFor(() => expect(screen.queryByText('Signup screen')).not.toBeInTheDocument())
  })

  it('sends a visitor to login when accounts are not configured', async () => {
    // A dead-end page told the visitor nothing useful. The login screen
    // explains the situation and offers the local demo instead.
    configured = false
    renderAt('/app', guardedRoutes)
    expect(await screen.findByText('Login screen')).toBeInTheDocument()
    expect(screen.queryByText('Private workspace')).not.toBeInTheDocument()
  })
})

describe('sign in', () => {
  it('signs in and does not keep the password anywhere', async () => {
    const user = userEvent.setup()
    authApi.signInWithPassword.mockResolvedValue({ data: { session: SESSION }, error: null })
    renderAt('/login', <LoginPage />)

    await user.type(screen.getByLabelText(/email or account id/i), 'owner@example.com')
    await user.type(screen.getByLabelText(/^password$/i), 'correct-horse')
    await user.click(screen.getByRole('button', { name: /^sign in$/i }))

    await waitFor(() => expect(authApi.signInWithPassword).toHaveBeenCalled())
    expect(authApi.signInWithPassword).toHaveBeenCalledWith({
      email: 'owner@example.com',
      password: 'correct-horse',
    })
  })

  it('reports a rejected sign-in without saying which field was wrong', async () => {
    const user = userEvent.setup()
    authApi.signInWithPassword.mockResolvedValue({
      data: null,
      error: { message: 'That email and password combination did not work.' },
    })
    renderAt('/login', <LoginPage />)

    await user.type(screen.getByLabelText(/email or account id/i), 'owner@example.com')
    await user.type(screen.getByLabelText(/^password$/i), 'wrong')
    await user.click(screen.getByRole('button', { name: /^sign in$/i }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/did not work/i)
    // It must not disclose whether the account exists.
    expect(alert).not.toHaveTextContent(/no account|not registered/i)
  })

  it('keeps the button disabled until both fields are filled', async () => {
    const user = userEvent.setup()
    renderAt('/login', <LoginPage />)

    const submit = screen.getByRole('button', { name: /^sign in$/i })
    expect(submit).toBeDisabled()

    await user.type(screen.getByLabelText(/email or account id/i), 'owner@example.com')
    expect(submit).toBeDisabled()

    await user.type(screen.getByLabelText(/^password$/i), 'secret')
    expect(submit).toBeEnabled()
  })
})

describe('sign up', () => {
  it('refuses to submit when the two passwords differ', async () => {
    const user = userEvent.setup()
    renderAt('/signup', <SignupPage />)

    await user.type(screen.getByLabelText(/^email$/i), 'new@example.com')
    await user.type(screen.getByLabelText(/^password$/i), 'longenough1')
    await user.type(screen.getByLabelText(/confirm password/i), 'different1')

    expect(screen.getByText(/do not match/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /create account/i })).toBeDisabled()
    expect(authApi.signUp).not.toHaveBeenCalled()
  })

  it('shows each password requirement until it is met', async () => {
    const user = userEvent.setup()
    renderAt('/signup', <SignupPage />)

    const field = screen.getByLabelText(/^password$/i)
    await user.type(field, 'abc')
    expect(screen.getByText(/at least 8 characters/i)).toBeInTheDocument()
    expect(screen.getByText(/one number/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /create account/i })).toBeDisabled()

    await user.type(field, 'defgh12')
    // Every rule satisfied, but the acknowledgement is still outstanding.
    expect(screen.getByRole('button', { name: /create account/i })).toBeDisabled()
  })

  it('asks the user to confirm their email when no session is returned', async () => {
    const user = userEvent.setup()
    authApi.signUp.mockResolvedValue({ data: { user: { id: 'u2' }, session: null }, error: null })
    renderAt('/signup', <SignupPage />)

    await user.type(screen.getByLabelText(/^email$/i), 'new@example.com')
    await user.type(screen.getByLabelText(/^password$/i), 'longenough1')
    await user.type(screen.getByLabelText(/confirm password/i), 'longenough1')
    await user.click(screen.getByLabelText(/stays private to my account/i))
    await user.click(screen.getByRole('button', { name: /create account/i }))

    expect(await screen.findByText(/confirmation email sent/i)).toBeInTheDocument()
  })

  it('surfaces a duplicate account without crashing', async () => {
    const user = userEvent.setup()
    authApi.signUp.mockResolvedValue({
      data: null,
      error: { message: 'An account already exists for that email.' },
    })
    renderAt('/signup', <SignupPage />)

    await user.type(screen.getByLabelText(/^email$/i), 'taken@example.com')
    await user.type(screen.getByLabelText(/^password$/i), 'longenough1')
    await user.type(screen.getByLabelText(/confirm password/i), 'longenough1')
    await user.click(screen.getByLabelText(/stays private to my account/i))
    await user.click(screen.getByRole('button', { name: /create account/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/already exists/i)
  })
})

describe('forgot password', () => {
  it('gives the same answer whether or not the address has an account', async () => {
    const user = userEvent.setup()
    authApi.resetPasswordForEmail.mockResolvedValue({ error: null })
    renderAt('/forgot-password', <ForgotPasswordPage />)

    await user.type(screen.getByLabelText(/email/i), 'maybe@example.com')
    await user.click(screen.getByRole('button', { name: /send reset link/i }))

    const status = await screen.findByRole('status')
    expect(status).toHaveTextContent(/if an account exists/i)
  })
})

describe('sign out', () => {
  it('clears the session', async () => {
    setSession(SESSION)
    authApi.signOut.mockResolvedValue({ error: null })

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

    const user = userEvent.setup()
    renderAt('/app', <Probe />)
    await screen.findByText('signed in')

    await user.click(screen.getByRole('button', { name: /sign out/i }))

    await waitFor(() => expect(authApi.signOut).toHaveBeenCalled())
    expect(await screen.findByText('signed out')).toBeInTheDocument()
  })
})
