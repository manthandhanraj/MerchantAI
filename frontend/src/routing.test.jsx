/**
 * Application routing.
 *
 * The product starts at sign-in. These assert the three redirects that make
 * that true, that the public demo is still reachable without an account, and
 * that an unknown address lands somewhere useful.
 */
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AppRoutes } from './App'

let session = null
const configured = true

vi.mock('./auth/AuthProvider', () => ({
  AuthProvider: ({ children }) => children,
  useAuth: () => ({
    session,
    user: session?.user ?? null,
    loading: false,
    configured,
    isLocalDemo: false,
    localDemoEnabled: false,
    startLocalDemo: vi.fn(),
    signIn: vi.fn(),
    signUp: vi.fn(),
    signOut: vi.fn(),
    requestPasswordReset: vi.fn(),
    updatePassword: vi.fn(),
  }),
}))

// The workspace provider fetches on mount; stub it so routing is what is tested.
vi.mock('./auth/WorkspaceProvider', () => ({
  WorkspaceProvider: ({ children }) => children,
  useWorkspace: () => ({
    loading: false,
    error: null,
    profile: null,
    merchantCount: 1,
    needsOnboarding: false,
    isDemo: false,
    readOnly: false,
    refresh: () => {},
  }),
}))

vi.mock('./services/privateApi', () => ({
  ApiError: class extends Error {},
  getMe: vi.fn(async () => ({ profile: null, merchant_count: 0, needs_onboarding: true })),
  listMerchants: vi.fn(async () => ({ count: 0, merchants: [] })),
  getMerchant: vi.fn(async () => ({ merchant: {} })),
  listAnalyses: vi.fn(async () => ({ analyses: [] })),
  listReports: vi.fn(async () => ({ reports: [] })),
  listUploads: vi.fn(async () => ({ uploads: [] })),
  getUploadSchema: vi.fn(async () => ({ types: {} })),
  getPrivateDashboard: vi.fn(),
  getPrivateInsights: vi.fn(),
  getPrivateActionPlan: vi.fn(),
  getPrivateForecast: vi.fn(),
  getPrivateAssistantStatus: vi.fn(async () => ({ suggested_questions: [] })),
  createMerchant: vi.fn(),
  updateMe: vi.fn(),
  deleteMerchant: vi.fn(),
  runAnalysis: vi.fn(),
  createReport: vi.fn(),
  getReportDownloadUrl: vi.fn(),
  deleteReport: vi.fn(),
  askPrivateAssistant: vi.fn(),
  validateUpload: vi.fn(),
  createUpload: vi.fn(),
  updateMerchant: vi.fn(),
}))

// The public demo page talks to the public API.
vi.mock('./services/api', () => ({
  getMerchants: vi.fn(async () => ({ merchants: [] })),
  getDashboard: vi.fn(),
  getActionPlan: vi.fn(),
  getForecast: vi.fn(),
  getInsights: vi.fn(),
  getAssistantStatus: vi.fn(async () => ({})),
  askAssistant: vi.fn(),
  getHealth: vi.fn(),
}))

vi.mock('./lib/demo', () => {
  const demo = { email: 'demo@merchantai.app', password: 'pw', available: true, offered: true }
  return { demoAccount: demo, useDemoCredentials: () => demo }
})

vi.mock('./lib/supabase', () => ({
  isSupabaseConfigured: true,
  getSupabase: () => null,
  getAccessToken: vi.fn(),
  friendlyAuthError: (e) => String(e),
  isRemembered: () => true,
  setRemembered: () => {},
}))

function renderAt(path) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AppRoutes />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  session = null
})

describe('entry point', () => {
  it('sends the root URL to sign-in', async () => {
    renderAt('/')
    expect(await screen.findByRole('button', { name: /^sign in$/i })).toBeInTheDocument()
  })

  it('sends a signed-out visitor from a private route to sign-in', async () => {
    renderAt('/app/merchant/abc')
    expect(await screen.findByRole('button', { name: /^sign in$/i })).toBeInTheDocument()
  })

  it('keeps a signed-in user out of the login screen', async () => {
    session = { user: { id: 'u1', email: 'owner@example.com' } }
    renderAt('/login')
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: /^sign in$/i })).not.toBeInTheDocument(),
    )
  })
})

describe('public routes', () => {
  it('opens the synthetic demo without an account', async () => {
    renderAt('/demo')
    // The public dashboard renders its own controls, not the login form.
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: /^sign in$/i })).not.toBeInTheDocument(),
    )
    // The public dashboard's own merchant control, not the login form.
    expect(await screen.findByLabelText(/merchant/i)).toBeInTheDocument()
  })

  it('keeps the marketing page on a secondary address', async () => {
    renderAt('/about')
    expect(
      await screen.findByText(/turned into the next three things to do/i),
    ).toBeInTheDocument()
  })

  it('offers a way back from an unknown address', async () => {
    renderAt('/nothing-here')
    expect(await screen.findByText(/page not found/i)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /open the demo/i })).toBeInTheDocument()
  })
})
