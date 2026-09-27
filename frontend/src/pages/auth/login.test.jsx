/**
 * The login page as the product's front door.
 *
 * The behaviour worth protecting: the demo button performs a *real* sign-in
 * with the credentials printed on screen, not a UI-only shortcut; the password
 * can be revealed; "remember me" is recorded before the session is created; and
 * a failure says something a person can act on.
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import LoginPage from './LoginPage'

const signIn = vi.fn()
const setRemembered = vi.fn()
const DEMO = { email: 'demo@merchantai.app', password: 'demo-pass-1234', available: true }
let demo = { ...DEMO, offered: true, error: null, load: vi.fn() }

vi.mock('../../auth/AuthProvider', () => ({
  useAuth: () => ({ signIn, configured: true, loading: false, session: null }),
}))

vi.mock('../../lib/demo', () => ({
  get demoAccount() {
    return demo
  },
  // The page reads the credentials through this hook, which fetches them from
  // the backend with built-in accounts.
  useDemoCredentials: () => demo,
}))

vi.mock('../../lib/supabase', () => ({
  isRemembered: () => true,
  setRemembered: (value) => setRemembered(value),
}))

function renderLogin(entry = '/login') {
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/app" element={<p>Workspace</p>} />
        <Route path="/demo" element={<p>Public demo dashboard</p>} />
        <Route path="/signup" element={<p>Signup screen</p>} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  demo = { ...DEMO, offered: true, error: null, load: vi.fn(async () => DEMO) }
  signIn.mockResolvedValue({ session: {} })
})

// ==========================================================================
describe('the form', () => {
  it('shows the brand, both fields and the primary action', () => {
    renderLogin()
    expect(screen.getAllByText(/merchant/i).length).toBeGreaterThan(0)
    expect(screen.getByLabelText(/email or account id/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/^password$/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^sign in$/i })).toBeInTheDocument()
  })

  it('links to account creation and password recovery', () => {
    renderLogin()
    expect(screen.getByRole('link', { name: /create new account/i })).toHaveAttribute(
      'href',
      '/signup',
    )
    expect(screen.getByRole('link', { name: /forgot your password/i })).toHaveAttribute(
      'href',
      '/forgot-password',
    )
  })

  it('keeps sign-in disabled until both fields are filled', async () => {
    const user = userEvent.setup()
    renderLogin()

    const submit = screen.getByRole('button', { name: /^sign in$/i })
    expect(submit).toBeDisabled()

    await user.type(screen.getByLabelText(/email or account id/i), 'owner@example.com')
    await user.type(screen.getByLabelText(/^password$/i), 'secret')
    expect(submit).toBeEnabled()
  })

  it('reveals and re-hides the password', async () => {
    const user = userEvent.setup()
    renderLogin()

    const field = screen.getByLabelText(/^password$/i)
    expect(field).toHaveAttribute('type', 'password')

    await user.click(screen.getByRole('button', { name: /show password/i }))
    expect(field).toHaveAttribute('type', 'text')

    await user.click(screen.getByRole('button', { name: /hide password/i }))
    expect(field).toHaveAttribute('type', 'password')
  })

  it('records the remember-me choice before creating the session', async () => {
    const user = userEvent.setup()
    renderLogin()

    await user.click(screen.getByLabelText(/remember me/i))
    await user.type(screen.getByLabelText(/email or account id/i), 'owner@example.com')
    await user.type(screen.getByLabelText(/^password$/i), 'secret')
    await user.click(screen.getByRole('button', { name: /^sign in$/i }))

    await waitFor(() => expect(signIn).toHaveBeenCalled())
    // Recorded first: the storage choice decides where the session is written.
    expect(setRemembered).toHaveBeenCalledWith(false)
  })

  it('signs in and moves to the workspace', async () => {
    const user = userEvent.setup()
    renderLogin()

    await user.type(screen.getByLabelText(/email or account id/i), 'owner@example.com')
    await user.type(screen.getByLabelText(/^password$/i), 'correct-horse')
    await user.click(screen.getByRole('button', { name: /^sign in$/i }))

    expect(await screen.findByText('Workspace')).toBeInTheDocument()
    expect(signIn).toHaveBeenCalledWith({
      email: 'owner@example.com',
      password: 'correct-horse',
    })
  })

  it('shows a readable message when the credentials are wrong', async () => {
    const user = userEvent.setup()
    signIn.mockRejectedValue(
      new Error('That email and password combination did not work. Check both and try again.'),
    )
    renderLogin()

    await user.type(screen.getByLabelText(/email or account id/i), 'owner@example.com')
    await user.type(screen.getByLabelText(/^password$/i), 'wrong')
    await user.click(screen.getByRole('button', { name: /^sign in$/i }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/did not work/i)
    // The form stays usable so the password can be corrected.
    expect(screen.getByRole('button', { name: /^sign in$/i })).toBeEnabled()
  })
})

// ==========================================================================
describe('demo account', () => {
  it('prints the credentials it is about to use', () => {
    renderLogin()
    expect(screen.getByText('demo@merchantai.app')).toBeInTheDocument()
    expect(screen.getByText('demo-pass-1234')).toBeInTheDocument()
  })

  it('says the demo is synthetic and read-only', () => {
    renderLogin()
    const panel = screen
      .getByRole('button', { name: /try demo account/i })
      .closest('div')
    expect(panel).toHaveTextContent(/synthetic/i)
    expect(panel).toHaveTextContent(/read-only/i)
  })

  it('signs in through the real auth path with exactly those credentials', async () => {
    const user = userEvent.setup()
    renderLogin()

    await user.click(screen.getByRole('button', { name: /try demo account/i }))

    await waitFor(() => expect(signIn).toHaveBeenCalled())
    // The same signIn every other user takes — not a bypass.
    expect(signIn).toHaveBeenCalledWith({
      email: 'demo@merchantai.app',
      password: 'demo-pass-1234',
    })
    expect(await screen.findByText('Workspace')).toBeInTheDocument()
  })

  it('fills the visible fields so the sign-in is not hidden from the user', async () => {
    const user = userEvent.setup()
    signIn.mockImplementation(() => new Promise(() => {}))
    renderLogin()

    await user.click(screen.getByRole('button', { name: /try demo account/i }))

    await waitFor(() =>
      expect(screen.getByLabelText(/email or account id/i)).toHaveValue('demo@merchantai.app'),
    )
    expect(screen.getByLabelText(/^password$/i)).toHaveValue('demo-pass-1234')
  })

  it('opens the stateless demo on a serverless local deployment without creating a broken session', async () => {
    const user = userEvent.setup()
    demo = {
      ...DEMO,
      workspaceUrl: '/demo',
      offered: true,
      error: null,
      load: vi.fn(),
    }
    renderLogin()

    await user.click(screen.getByRole('button', { name: /try demo account/i }))

    expect(await screen.findByText('Public demo dashboard')).toBeInTheDocument()
    expect(signIn).not.toHaveBeenCalled()
  })

  it('reports a demo failure instead of hanging', async () => {
    const user = userEvent.setup()
    signIn.mockRejectedValue(new Error('That email and password combination did not work.'))
    renderLogin()

    await user.click(screen.getByRole('button', { name: /try demo account/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/did not work/i)
    expect(screen.getByRole('button', { name: /try demo account/i })).toBeEnabled()
  })

  it('hides the section entirely when no demo is configured', () => {
    demo = { email: '', password: '', available: false, offered: false, error: null, load: vi.fn() }
    renderLogin()

    expect(screen.queryByRole('button', { name: /try demo account/i })).not.toBeInTheDocument()
    expect(screen.queryByText('demo@merchantai.app')).not.toBeInTheDocument()
    // The real form is untouched.
    expect(screen.getByRole('button', { name: /^sign in$/i })).toBeInTheDocument()
  })
})

// ==========================================================================
describe('both ways in', () => {
  it('offers creating an account and trying the demo side by side', () => {
    renderLogin()
    expect(screen.getByRole('link', { name: /create new account/i })).toHaveAttribute(
      'href',
      '/signup',
    )
    expect(screen.getByRole('button', { name: /try demo account/i })).toBeEnabled()
  })

  it('keeps the demo on offer while its details are still loading', () => {
    demo = { email: '', password: '', available: false, offered: true, error: null, load: vi.fn() }
    renderLogin()

    expect(screen.getByRole('button', { name: /try demo account/i })).toBeEnabled()
    expect(screen.getByText(/loading the demo sign-in details/i)).toBeInTheDocument()
  })

  it('keeps the demo when its details could not be loaded, and fetches them on click', async () => {
    const user = userEvent.setup()
    demo = {
      email: '',
      password: '',
      available: false,
      offered: true,
      error: 'Could not reach the server. Check that MerchantAI is running and try again.',
      load: vi.fn(async () => DEMO),
    }
    renderLogin()

    // The reason is on screen, and the option has not vanished.
    expect(screen.getByRole('alert')).toHaveTextContent(/could not reach the server/i)
    await user.click(screen.getByRole('button', { name: /try demo account/i }))

    await waitFor(() => expect(demo.load).toHaveBeenCalled())
    expect(signIn).toHaveBeenCalledWith({ email: DEMO.email, password: DEMO.password })
    expect(await screen.findByText('Workspace')).toBeInTheDocument()
  })

  it('says why the demo still cannot be opened', async () => {
    const user = userEvent.setup()
    demo = {
      email: '',
      password: '',
      available: false,
      offered: true,
      error: null,
      load: vi.fn(async () => {
        throw new Error('This MerchantAI server is running an older version without accounts.')
      }),
    }
    renderLogin()

    await user.click(screen.getByRole('button', { name: /try demo account/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/older version/i)
    expect(signIn).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: /try demo account/i })).toBeEnabled()
  })

  it('starts the demo when arriving from "Try demo account" on another page', async () => {
    renderLogin({ pathname: '/login', state: { startDemo: true } })

    await waitFor(() =>
      expect(signIn).toHaveBeenCalledWith({ email: DEMO.email, password: DEMO.password }),
    )
    expect(signIn).toHaveBeenCalledTimes(1)
    expect(await screen.findByText('Workspace')).toBeInTheDocument()
  })

  it('does not start the demo on an ordinary visit', () => {
    renderLogin()
    expect(signIn).not.toHaveBeenCalled()
  })
})
