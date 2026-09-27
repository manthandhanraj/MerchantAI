/**
 * How the interface behaves inside the shared demo workspace.
 *
 * The backend refuses every mutating call from the demo account regardless of
 * what the UI shows — these assert the courtesy layer on top of it: a visitor
 * is told where they are, is not offered controls that would be rejected, and
 * is pointed at creating their own workspace instead.
 */
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import AccountPage from './AccountPage'
import MerchantDashboardPage from './MerchantDashboardPage'
import OnboardingPage from './OnboardingPage'
import ReportsPage from './ReportsPage'
import WorkspacePage from './WorkspacePage'
import * as api from '../../services/privateApi'

let workspace = {
  loading: false,
  error: null,
  profile: { full_name: 'MerchantAI Demo' },
  merchantCount: 1,
  needsOnboarding: false,
  isDemo: true,
  readOnly: true,
  refresh: () => {},
}

vi.mock('../../auth/WorkspaceProvider', () => ({
  WorkspaceProvider: ({ children }) => children,
  useWorkspace: () => workspace,
}))

const signOut = vi.fn(async () => {})

vi.mock('../../auth/AuthProvider', () => ({
  useAuth: () => ({
    user: { id: 'demo', email: 'demo@merchantai.app' },
    signOut,
    updatePassword: vi.fn(),
  }),
}))

// This suite covers the *seeded* demo account, which only exists when Supabase
// is configured — so the no-Supabase fallback must be off.
vi.mock('../../lib/demo', () => ({
  demoAccount: { email: 'demo@merchantai.app', password: 'pw', available: true },
  useDemoCredentials: () => ({ email: 'demo@merchantai.app', password: 'pw', available: true, offered: true }),
}))

vi.mock('../../services/privateApi', () => ({
  ApiError: class extends Error {},
  getMe: vi.fn(),
  updateMe: vi.fn(),
  listMerchants: vi.fn(),
  createMerchant: vi.fn(),
  getMerchant: vi.fn(),
  updateMerchant: vi.fn(),
  deleteMerchant: vi.fn(),
  getUploadSchema: vi.fn(),
  validateUpload: vi.fn(),
  createUpload: vi.fn(),
  listUploads: vi.fn(),
  runAnalysis: vi.fn(),
  listAnalyses: vi.fn(),
  getPrivateDashboard: vi.fn(),
  getPrivateInsights: vi.fn(),
  getPrivateActionPlan: vi.fn(),
  getPrivateForecast: vi.fn(),
  getPrivateAssistantStatus: vi.fn(),
  askPrivateAssistant: vi.fn(),
  createReport: vi.fn(),
  listReports: vi.fn(),
  getReportDownloadUrl: vi.fn(),
  deleteReport: vi.fn(),
}))

const MERCHANT_ID = 'aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa'
const MERCHANT = {
  id: MERCHANT_ID,
  name: 'Chai Point Cafe (Demo)',
  business_type: 'Cafe or restaurant',
  currency: 'INR',
  created_at: '2026-09-01T10:00:00+00:00',
}

const SUMMARY = {
  period_start: '2026-06-18',
  period_end: '2026-09-15',
  days: 90,
  total_revenue: 606963,
  total_orders: 7621,
  total_units_sold: 10555,
  total_profit: 385281,
  profit_margin: 0.635,
  average_order_value: 79.64,
  total_customers: 6454,
  new_customers: 2140,
  repeat_customers: 4314,
  repeat_customer_rate: 0.668,
  revenue_per_customer: 94,
  revenue_growth_rate: -0.176,
}

function renderRoute(path, pattern, element) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path={pattern} element={element} />
        <Route path="*" element={<p>elsewhere</p>} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  workspace = { ...workspace, isDemo: true, readOnly: true }

  api.getMerchant.mockResolvedValue({
    merchant: MERCHANT,
    upload_count: 2,
    analysis_count: 1,
    has_sales_data: true,
    has_customer_data: true,
  })
  api.listAnalyses.mockResolvedValue({
    analyses: [
      {
        id: 'run-1',
        status: 'completed',
        date_start: '2026-06-18',
        date_end: '2026-09-15',
        created_at: '2026-09-16T09:00:00+00:00',
      },
    ],
  })
  api.getPrivateDashboard.mockResolvedValue({
    merchant: MERCHANT,
    analysis_id: 'run-1',
    status: 'completed',
    has_data: true,
    summary: SUMMARY,
    daily: [{ date: '2026-06-18', revenue: 6700, profit: 4200, orders: 84, customers: 70, new_customers: 25, repeat_customers: 45 }],
    products: [],
    categories: [],
    inventory: [],
    period: { start: '2026-06-18', end: '2026-09-15' },
    generated_at: '2026-09-16T09:00:00+00:00',
    source_upload: { id: 'u1', original_filename: 'demo-sales.csv', row_count: 1078, created_at: '2026-09-16T08:00:00+00:00' },
  })
  api.getPrivateInsights.mockResolvedValue({ has_data: true, findings: [], severity_counts: {} })
  api.getPrivateActionPlan.mockResolvedValue({ has_data: true, high: [], medium: [], low: [] })
  api.getPrivateForecast.mockResolvedValue({ available: false, reason: 'n/a' })
  api.getPrivateAssistantStatus.mockResolvedValue({ enabled: false, suggested_questions: [] })
  api.listReports.mockResolvedValue({ reports: [] })
  api.listMerchants.mockResolvedValue({ merchants: [MERCHANT] })
  api.getMe.mockResolvedValue({ profile: { full_name: 'MerchantAI Demo' } })
})

// ==========================================================================
describe('dashboard in demo mode', () => {
  const path = `/app/merchant/${MERCHANT_ID}`
  const pattern = '/app/merchant/:id'

  it('labels the workspace as a demo', async () => {
    renderRoute(path, pattern, <MerchantDashboardPage />)
    await screen.findByRole('heading', { name: /chai point cafe/i })
    expect(screen.getByText(/demo mode/i)).toBeInTheDocument()
    expect(screen.getByText(/synthetic example data/i)).toBeInTheDocument()
  })

  it('still shows the seeded figures', async () => {
    renderRoute(path, pattern, <MerchantDashboardPage />)
    expect(await screen.findByText('₹6,06,963')).toBeInTheDocument()
    expect(screen.getByText('7,621')).toBeInTheDocument()
  })

  it('says the data is seeded rather than naming an uploaded file', async () => {
    renderRoute(path, pattern, <MerchantDashboardPage />)
    expect(await screen.findByText(/seeded synthetic demo data/i)).toBeInTheDocument()
    expect(screen.queryByText('demo-sales.csv')).not.toBeInTheDocument()
  })

  it('hides the controls the backend would refuse', async () => {
    renderRoute(path, pattern, <MerchantDashboardPage />)
    await screen.findByText('₹6,06,963')

    expect(screen.queryByRole('button', { name: /re-run analysis/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /upload new data/i })).not.toBeInTheDocument()
  })

  it('keeps report generation, which the demo journey needs', async () => {
    renderRoute(path, pattern, <MerchantDashboardPage />)
    await screen.findByRole('heading', { name: /chai point cafe/i })
    expect(screen.getByRole('button', { name: /generate report/i })).toBeInTheDocument()
  })

  it('restores those controls for a real account', async () => {
    workspace = { ...workspace, isDemo: false, readOnly: false }
    renderRoute(path, pattern, <MerchantDashboardPage />)
    await screen.findByText('₹6,06,963')

    expect(screen.getByRole('button', { name: /re-run analysis/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /upload new data/i })).toBeInTheDocument()
    expect(screen.queryByText(/demo mode/i)).not.toBeInTheDocument()
  })
})

describe('reports in demo mode', () => {
  const path = `/app/merchant/${MERCHANT_ID}/reports`
  const pattern = '/app/merchant/:id/reports'

  it('offers download but not deletion', async () => {
    api.listReports.mockResolvedValue({
      reports: [
        { id: 'rep-1', format: 'pdf', byte_size: 20480, created_at: '2026-09-16T10:00:00+00:00' },
      ],
    })
    renderRoute(path, pattern, <ReportsPage />)

    expect(await screen.findByRole('button', { name: /download/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^delete$/i })).not.toBeInTheDocument()
  })
})

describe('account in demo mode', () => {
  it('explains why the shared password cannot be changed', async () => {
    renderRoute('/app/account', '/app/account', <AccountPage />)
    await screen.findByRole('heading', { name: /your account/i })

    expect(screen.getByText(/shared, so its password cannot be changed/i)).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: /update password/i }),
    ).not.toBeInTheDocument()
  })

  it('does not offer to delete the shared merchant', async () => {
    renderRoute('/app/account', '/app/account', <AccountPage />)
    await screen.findByRole('heading', { name: /your account/i })

    expect(screen.getByText(/read-only in demo mode/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^delete$/i })).not.toBeInTheDocument()
  })
})

describe('from the demo to an account of your own', () => {
  it('offers creating an account where a real account adds a business', async () => {
    renderRoute('/app', '/app', <WorkspacePage />)
    await screen.findByText('Chai Point Cafe (Demo)')

    expect(screen.queryByRole('link', { name: /add a business/i })).not.toBeInTheDocument()
    expect(
      screen.getAllByRole('button', { name: /create your own account/i }).length,
    ).toBeGreaterThan(0)
  })

  it('explains instead of showing a form the demo could never submit', () => {
    renderRoute('/app/onboarding', '/app/onboarding', <OnboardingPage />)

    expect(
      screen.getByRole('heading', { name: /add your own business with your own account/i }),
    ).toBeInTheDocument()
    expect(screen.queryByLabelText(/business name/i)).not.toBeInTheDocument()
  })

  it('signs out of the demo first, so sign-up is not bounced back to the demo', async () => {
    const user = userEvent.setup()
    render(
      <MemoryRouter initialEntries={['/app/onboarding']}>
        <Routes>
          <Route path="/app/onboarding" element={<OnboardingPage />} />
          <Route path="/signup" element={<p>Signup screen</p>} />
        </Routes>
      </MemoryRouter>,
    )

    // Offered by both the demo banner and the page; either does the same.
    const buttons = screen.getAllByRole('button', { name: /create your own account/i })
    expect(buttons.length).toBe(2)
    await user.click(buttons[buttons.length - 1])

    expect(signOut).toHaveBeenCalledTimes(1)
    expect(await screen.findByText('Signup screen')).toBeInTheDocument()
  })

  it('keeps the business form for a real account', async () => {
    workspace = { ...workspace, isDemo: false, readOnly: false }
    renderRoute('/app', '/app', <WorkspacePage />)
    expect(await screen.findByRole('link', { name: /add a business/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /create your own account/i })).not.toBeInTheDocument()
  })

  it('keeps the onboarding form for a real account', () => {
    workspace = { ...workspace, isDemo: false, readOnly: false }
    renderRoute('/app/onboarding', '/app/onboarding', <OnboardingPage />)
    expect(screen.getByLabelText(/business name/i)).toBeInTheDocument()
  })
})
