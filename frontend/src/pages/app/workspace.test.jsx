/**
 * The private workspace screens: onboarding, the upload wizard, the dashboard
 * and the report flow.
 *
 * The API module is mocked, so these assert what the UI does with a given
 * response — that a validation failure is shown row by row and nothing is
 * stored, that an empty workspace explains itself rather than rendering zeroes,
 * and that a merchant is told where their figures came from.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import MerchantDashboardPage from './MerchantDashboardPage'
import OnboardingPage from './OnboardingPage'
import ReportsPage from './ReportsPage'
import UploadWizardPage from './UploadWizardPage'
import * as api from '../../services/privateApi'

vi.mock('../../services/privateApi', () => ({
  ApiError: class ApiError extends Error {},
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

// The shell reads the session for the avatar and the sign-out control.
vi.mock('../../auth/AuthProvider', () => ({
  useAuth: () => ({
    user: { id: 'u1', email: 'owner@example.com' },
    signOut: vi.fn(),
    updatePassword: vi.fn(),
  }),
}))

const MERCHANT_ID = 'aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa'

const MERCHANT = {
  id: MERCHANT_ID,
  name: 'Riya Bakery',
  business_type: 'Cafe or restaurant',
  currency: 'INR',
  created_at: '2026-09-01T10:00:00+00:00',
}

const SCHEMA = {
  max_bytes: 10 * 1024 * 1024,
  max_rows: 200000,
  types: {
    sales: [
      { name: 'date', kind: 'date', required: true, description: 'Business date.' },
      { name: 'product', kind: 'text', required: true, description: 'Product name.' },
      { name: 'revenue', kind: 'float', required: true, description: 'Gross revenue.' },
    ],
    customers: [
      { name: 'date', kind: 'date', required: true, description: 'Business date.' },
      { name: 'customers', kind: 'int', required: true, description: 'Distinct customers.' },
    ],
  },
}

const SUMMARY = {
  period_start: '2026-03-01',
  period_end: '2026-03-28',
  days: 28,
  total_revenue: 482400,
  total_orders: 1284,
  total_units_sold: 1500,
  total_expenses: 300000,
  total_profit: 182400,
  profit_margin: 0.378,
  average_order_value: 375,
  total_customers: 900,
  new_customers: 560,
  repeat_customers: 340,
  repeat_customer_rate: 0.372,
  revenue_per_customer: 536,
  revenue_growth_rate: 0.184,
  active_products: 2,
  active_categories: 2,
}

const DASHBOARD = {
  merchant: MERCHANT,
  analysis_id: 'run-1',
  status: 'completed',
  has_data: true,
  summary: SUMMARY,
  daily: [
    { date: '2026-03-01', revenue: 17000, profit: 6500, orders: 45, customers: 30, new_customers: 18, repeat_customers: 12 },
    { date: '2026-03-02', revenue: 18200, profit: 6900, orders: 47, customers: 32, new_customers: 19, repeat_customers: 13 },
  ],
  products: [
    { product: 'Croissant', revenue: 300000, units_sold: 900, revenue_share: 0.62, profit_margin: 0.4 },
    { product: 'Coffee', revenue: 182400, units_sold: 600, revenue_share: 0.38, profit_margin: 0.35 },
  ],
  categories: [{ category: 'Bakery', revenue: 300000, revenue_share: 0.62, profit_margin: 0.4 }],
  inventory: [
    { product: 'Croissant', inventory: 8, days_of_inventory_cover: 1.4, stock_status: 'critical' },
    { product: 'Coffee', inventory: 300, days_of_inventory_cover: 40, stock_status: 'healthy' },
  ],
  period: { start: '2026-03-01', end: '2026-03-28' },
  generated_at: '2026-03-29T09:00:00+00:00',
  source_upload: {
    id: 'up-1',
    original_filename: 'march-sales.csv',
    row_count: 56,
    created_at: '2026-03-29T08:00:00+00:00',
  },
}

const PLAN = {
  has_data: true,
  total_available: 4,
  included: 2,
  truncated: true,
  notes: ['Showing the 2 most significant of 4 suggestions.'],
  high: [
    {
      rank: 1,
      priority: 'High',
      title: 'Reorder Croissant before it runs out',
      action: 'Place a replenishment order now.',
      reason: 'Croissant has 1.4 days of stock cover.',
      category: 'Inventory',
      scope: 'Croissant',
      source_finding: 'inventory-critical-croissant',
    },
  ],
  medium: [
    {
      rank: 2,
      priority: 'Medium',
      title: 'Protect the revenue you have gained',
      action: 'Keep the growing lines in stock.',
      reason: 'Revenue rose 18.4% versus the previous period.',
      category: 'Revenue',
      scope: 'merchant',
      source_finding: 'total-revenue-up',
    },
  ],
  low: [],
}

const INSIGHTS = {
  has_data: true,
  comparison_basis: 'previous_period',
  severity_counts: { HIGH: 1, MEDIUM: 1, LOW: 0 },
  notes: [],
  findings: [
    {
      id: 'inventory-critical-croissant',
      category: 'Inventory',
      severity: 'HIGH',
      title: 'Croissant has 1.4 days of stock cover',
      description: 'Croissant closed at 8 units.',
      reason: 'Cover of 1.4 days is below the critical threshold of 3 days.',
      scope: 'Croissant',
    },
  ],
}

const FORECAST = { available: false, reason: 'Not enough history yet.' }

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
  api.getMerchant.mockResolvedValue({
    merchant: MERCHANT,
    upload_count: 2,
    analysis_count: 1,
    has_sales_data: true,
    has_customer_data: true,
  })
  api.getUploadSchema.mockResolvedValue(SCHEMA)
  api.listUploads.mockResolvedValue({ count: 0, uploads: [] })
  api.listAnalyses.mockResolvedValue({
    count: 1,
    analyses: [
      {
        id: 'run-1',
        status: 'completed',
        date_start: '2026-03-01',
        date_end: '2026-03-28',
        created_at: '2026-03-29T09:00:00+00:00',
      },
    ],
  })
  api.getPrivateDashboard.mockResolvedValue(DASHBOARD)
  api.getPrivateInsights.mockResolvedValue(INSIGHTS)
  api.getPrivateActionPlan.mockResolvedValue(PLAN)
  api.getPrivateForecast.mockResolvedValue(FORECAST)
  api.getPrivateAssistantStatus.mockResolvedValue({
    enabled: false,
    suggested_questions: ['What should I focus on today?'],
  })
  api.listReports.mockResolvedValue({ count: 0, reports: [] })
})

// ==========================================================================
describe('onboarding', () => {
  it('requires a business name before it will submit', async () => {
    const user = userEvent.setup()
    renderRoute('/app/onboarding', '/app/onboarding', <OnboardingPage />)

    const submit = screen.getByRole('button', { name: /create workspace/i })
    expect(submit).toBeDisabled()

    await user.type(screen.getByLabelText(/business name/i), 'Riya Bakery')
    expect(submit).toBeEnabled()
  })

  it('creates the merchant and goes straight to the upload wizard', async () => {
    const user = userEvent.setup()
    api.createMerchant.mockResolvedValue({ merchant: MERCHANT })
    render(
      <MemoryRouter initialEntries={['/app/onboarding']}>
        <Routes>
          <Route path="/app/onboarding" element={<OnboardingPage />} />
          <Route path="/app/merchant/:id/upload" element={<p>Upload wizard</p>} />
        </Routes>
      </MemoryRouter>,
    )

    await user.type(screen.getByLabelText(/business name/i), 'Riya Bakery')
    await user.click(screen.getByRole('button', { name: /create workspace/i }))

    // An empty dashboard would tell a new merchant nothing.
    expect(await screen.findByText('Upload wizard')).toBeInTheDocument()
  })

  it('defaults to INR but lets the currency be changed', async () => {
    const user = userEvent.setup()
    api.createMerchant.mockResolvedValue({ merchant: MERCHANT })
    renderRoute('/app/onboarding', '/app/onboarding', <OnboardingPage />)

    const currency = screen.getByLabelText(/currency/i)
    expect(currency).toHaveValue('INR')

    await user.selectOptions(currency, 'USD')
    await user.type(screen.getByLabelText(/business name/i), 'Shop')
    await user.click(screen.getByRole('button', { name: /create workspace/i }))

    await waitFor(() => expect(api.createMerchant).toHaveBeenCalled())
    expect(api.createMerchant.mock.calls[0][0]).toMatchObject({ currency: 'USD' })
  })

  it('reports a failure instead of pretending it worked', async () => {
    const user = userEvent.setup()
    api.createMerchant.mockRejectedValue(new Error('A business name is required.'))
    renderRoute('/app/onboarding', '/app/onboarding', <OnboardingPage />)

    await user.type(screen.getByLabelText(/business name/i), 'x')
    await user.click(screen.getByRole('button', { name: /create workspace/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/business name is required/i)
  })
})

// ==========================================================================
describe('upload wizard', () => {
  const path = `/app/merchant/${MERCHANT_ID}/upload`
  const pattern = '/app/merchant/:id/upload'

  const csvFile = (name = 'sales.csv') =>
    new File(['date,product,revenue\n2026-03-01,Croissant,100\n'], name, { type: 'text/csv' })

  it('explains which columns the file needs', async () => {
    renderRoute(path, pattern, <UploadWizardPage />)
    expect(await screen.findByText(/choose your sales data file/i)).toBeInTheDocument()
    await userEvent.setup().click(screen.getByText(/what columns does this file need/i))
    expect(screen.getByText(/Business date\./i)).toBeInTheDocument()
  })

  it('refuses a non-CSV file without calling the API', async () => {
    const user = userEvent.setup()
    renderRoute(path, pattern, <UploadWizardPage />)
    await screen.findByText(/choose your sales data file/i)

    const input = document.querySelector('input[type="file"]')
    const wrongType = new File(['x'], 'books.xlsx', { type: 'application/vnd.ms-excel' })
    // user.upload honours the input's accept filter, so the file would never
    // reach our handler. Fire the change directly to exercise the guard itself.
    fireEvent.change(input, { target: { files: [wrongType] } })

    expect(await screen.findByRole('alert')).toHaveTextContent(/only \.csv/i)
    expect(api.validateUpload).not.toHaveBeenCalled()
  })

  it('refuses a file above the size limit without calling the API', async () => {
    const user = userEvent.setup()
    api.getUploadSchema.mockResolvedValue({ ...SCHEMA, max_bytes: 10 })
    renderRoute(path, pattern, <UploadWizardPage />)
    await screen.findByText(/choose your sales data file/i)

    const input = document.querySelector('input[type="file"]')
    await user.upload(input, csvFile())

    expect(await screen.findByRole('alert')).toHaveTextContent(/above the/i)
    expect(api.validateUpload).not.toHaveBeenCalled()
  })

  it('shows the mapping, a preview and the store button for a valid file', async () => {
    const user = userEvent.setup()
    api.validateUpload.mockResolvedValue({
      ok: true,
      headers: ['date', 'product', 'revenue'],
      mapping: { date: 'date', product: 'product', revenue: 'revenue' },
      unmapped_required: [],
      row_count: 1,
      preview: [{ date: '2026-03-01', product: 'Croissant', revenue: 100 }],
      errors: [],
      error_count: 0,
      messages: ['1 row(s) read. No problems found.'],
      warnings: [],
    })
    renderRoute(path, pattern, <UploadWizardPage />)
    await screen.findByText(/choose your sales data file/i)

    await user.upload(document.querySelector('input[type="file"]'), csvFile())

    expect(await screen.findByText(/match your columns/i)).toBeInTheDocument()
    expect(screen.getByText('Croissant')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /store this sales data/i })).toBeInTheDocument()
  })

  it('lists the offending rows and stores nothing when validation fails', async () => {
    const user = userEvent.setup()
    api.validateUpload.mockResolvedValue({
      ok: false,
      headers: ['date', 'product', 'revenue'],
      mapping: { date: 'date', product: 'product', revenue: 'revenue' },
      unmapped_required: [],
      row_count: 2,
      preview: [],
      errors: [
        { row: 3, column: 'revenue', value: 'six hundred', problem: 'is not a number' },
      ],
      error_count: 1,
      messages: [],
      warnings: [],
    })
    renderRoute(path, pattern, <UploadWizardPage />)
    await screen.findByText(/choose your sales data file/i)

    await user.upload(document.querySelector('input[type="file"]'), csvFile())

    expect(await screen.findByText(/1 row\(s\) need fixing/i)).toBeInTheDocument()
    expect(screen.getByText('is not a number')).toBeInTheDocument()
    expect(screen.getByText('six hundred')).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: /store this sales data/i }),
    ).not.toBeInTheDocument()
    expect(api.createUpload).not.toHaveBeenCalled()
  })

  it('re-validates when a column is mapped by hand', async () => {
    const user = userEvent.setup()
    api.validateUpload.mockResolvedValue({
      ok: false,
      headers: ['when', 'thing', 'money'],
      mapping: { date: null, product: null, revenue: null },
      unmapped_required: ['date', 'product', 'revenue'],
      row_count: 1,
      preview: [],
      errors: [],
      error_count: 0,
      messages: ['These required columns could not be matched: date, product, revenue.'],
      warnings: [],
    })
    renderRoute(path, pattern, <UploadWizardPage />)
    await screen.findByText(/choose your sales data file/i)
    await user.upload(document.querySelector('input[type="file"]'), csvFile())

    await screen.findByText(/match your columns/i)
    api.validateUpload.mockClear()

    await user.selectOptions(screen.getByLabelText('date'), 'when')

    await waitFor(() => expect(api.validateUpload).toHaveBeenCalled())
    expect(api.validateUpload.mock.calls[0][1].mapping).toMatchObject({ date: 'when' })
  })

  it('confirms storage and offers the next file', async () => {
    const user = userEvent.setup()
    api.validateUpload.mockResolvedValue({
      ok: true,
      headers: ['date', 'product', 'revenue'],
      mapping: { date: 'date', product: 'product', revenue: 'revenue' },
      unmapped_required: [],
      row_count: 56,
      preview: [],
      errors: [],
      error_count: 0,
      messages: ['56 row(s) read.'],
      warnings: [],
    })
    api.createUpload.mockResolvedValue({
      upload: { id: 'up-1', row_count: 56, original_filename: 'sales.csv' },
    })
    renderRoute(path, pattern, <UploadWizardPage />)
    await screen.findByText(/choose your sales data file/i)

    await user.upload(document.querySelector('input[type="file"]'), csvFile())
    await user.click(await screen.findByRole('button', { name: /store this sales data/i }))

    expect(await screen.findByText(/sales data stored/i)).toBeInTheDocument()
    expect(api.createUpload).toHaveBeenCalledTimes(1)
    // A key is sent so a retried submission cannot create a second upload.
    expect(api.createUpload.mock.calls[0][1].idempotencyKey).toBeTruthy()
  })
})

// ==========================================================================
describe('private dashboard', () => {
  const path = `/app/merchant/${MERCHANT_ID}`
  const pattern = '/app/merchant/:id'

  it('renders the merchant name and their own figures', async () => {
    renderRoute(path, pattern, <MerchantDashboardPage />)

    expect(await screen.findByRole('heading', { name: 'Riya Bakery' })).toBeInTheDocument()
    expect(screen.getByText('₹4,82,400')).toBeInTheDocument()
    expect(screen.getByText('1,284')).toBeInTheDocument()
    expect(screen.getByText('37.2%')).toBeInTheDocument()
    expect(screen.getByText('₹375')).toBeInTheDocument()
  })

  it('says where the figures came from', async () => {
    renderRoute(path, pattern, <MerchantDashboardPage />)
    await screen.findByRole('heading', { name: 'Riya Bakery' })

    expect(screen.getByText('march-sales.csv')).toBeInTheDocument()
    expect(screen.getByText('56')).toBeInTheDocument()
  })

  it('shows product, category and inventory panels', async () => {
    renderRoute(path, pattern, <MerchantDashboardPage />)
    await screen.findByRole('heading', { name: 'Riya Bakery' })

    expect(screen.getByRole('heading', { name: /product performance/i })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /category performance/i })).toBeInTheDocument()

    const inventory = within(
      screen.getByRole('heading', { name: /inventory alerts/i }).closest('section'),
    )
    expect(inventory.getByText('critical')).toBeInTheDocument()
    // A healthy product is not an alert.
    expect(inventory.queryByText('Coffee')).not.toBeInTheDocument()
  })

  it('offers upload when nothing has been analysed yet', async () => {
    api.listAnalyses.mockResolvedValue({ count: 0, analyses: [] })
    api.getMerchant.mockResolvedValue({
      merchant: MERCHANT,
      upload_count: 0,
      analysis_count: 0,
      has_sales_data: false,
      has_customer_data: false,
    })
    renderRoute(path, pattern, <MerchantDashboardPage />)

    const empty = within(
      (await screen.findByText(/upload your data to get started/i)).closest('section'),
    )
    expect(empty.getByRole('link', { name: /upload data/i })).toBeInTheDocument()
    // Nothing is invented in place of the missing numbers.
    expect(screen.queryByText('₹0')).not.toBeInTheDocument()
  })

  it('offers to run the analysis once both files are present', async () => {
    api.listAnalyses.mockResolvedValue({ count: 0, analyses: [] })
    renderRoute(path, pattern, <MerchantDashboardPage />)

    expect(await screen.findByText(/ready to analyse/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /analyse my business/i })).toBeInTheDocument()
  })

  it('surfaces a failed analysis rather than hiding it', async () => {
    api.listAnalyses.mockResolvedValue({
      count: 1,
      analyses: [
        {
          id: 'run-bad',
          status: 'failed',
          error_message: 'The uploaded files do not form a consistent dataset.',
          created_at: '2026-03-29T09:00:00+00:00',
        },
      ],
    })
    renderRoute(path, pattern, <MerchantDashboardPage />)

    expect(await screen.findByText(/did not finish/i)).toBeInTheDocument()
    expect(screen.getByText(/do not form a consistent dataset/i)).toBeInTheDocument()
  })

  it('reports a load failure with a way to retry', async () => {
    api.getMerchant.mockRejectedValue(new Error('Merchant not found.'))
    renderRoute(path, pattern, <MerchantDashboardPage />)

    expect(await screen.findByText(/could not open this business/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument()
  })

  it('generates a report from the shown analysis', async () => {
    const user = userEvent.setup()
    api.createReport.mockResolvedValue({ report: { id: 'rep-1' } })
    renderRoute(path, pattern, <MerchantDashboardPage />)
    await screen.findByRole('heading', { name: 'Riya Bakery' })

    await user.click(screen.getByRole('button', { name: /generate report/i }))

    await waitFor(() => expect(api.createReport).toHaveBeenCalledWith(MERCHANT_ID, 'run-1'))
    expect(await screen.findByText(/report generated/i)).toBeInTheDocument()
  })

  it('asks the assistant only about this merchant', async () => {
    const user = userEvent.setup()
    api.askPrivateAssistant.mockResolvedValue({
      question: 'What should I focus on today?',
      answer: 'Reorder Croissant before it runs out.',
      source: 'deterministic',
      grounded_in: ['action_plan'],
    })
    renderRoute(path, pattern, <MerchantDashboardPage />)
    await screen.findByRole('heading', { name: 'Riya Bakery' })

    await user.click(screen.getByRole('button', { name: 'What should I focus on today?' }))

    await waitFor(() => expect(api.askPrivateAssistant).toHaveBeenCalled())
    expect(api.askPrivateAssistant).toHaveBeenCalledWith(
      MERCHANT_ID,
      'What should I focus on today?',
    )
    const assistant = within(
      screen.getByRole('heading', { name: /ask about this business/i }).closest('section'),
    )
    expect(await assistant.findByText(/reorder croissant before it runs out\./i)).toBeInTheDocument()
  })
})

// ==========================================================================
describe('reports', () => {
  const path = `/app/merchant/${MERCHANT_ID}/reports`
  const pattern = '/app/merchant/:id/reports'

  it('explains the empty state', async () => {
    renderRoute(path, pattern, <ReportsPage />)
    expect(await screen.findByText(/no reports yet/i)).toBeInTheDocument()
  })

  it('lists analyses and lets one be turned into a report', async () => {
    const user = userEvent.setup()
    api.createReport.mockResolvedValue({ report: { id: 'rep-1' } })
    api.listReports
      .mockResolvedValueOnce({ count: 0, reports: [] })
      .mockResolvedValue({
        count: 1,
        reports: [
          {
            id: 'rep-1',
            format: 'pdf',
            byte_size: 20480,
            created_at: '2026-03-29T10:00:00+00:00',
          },
        ],
      })

    renderRoute(path, pattern, <ReportsPage />)
    await screen.findByRole('heading', { name: 'Analysis history' })

    await user.click(screen.getByRole('button', { name: /generate report/i }))

    expect(await screen.findByText(/report generated and stored privately/i)).toBeInTheDocument()
    expect(await screen.findByRole('button', { name: /download/i })).toBeInTheDocument()
  })

  it('asks for a signed URL rather than linking to storage directly', async () => {
    const user = userEvent.setup()
    api.listReports.mockResolvedValue({
      count: 1,
      reports: [
        { id: 'rep-1', format: 'pdf', byte_size: 20480, created_at: '2026-03-29T10:00:00+00:00' },
      ],
    })
    api.getReportDownloadUrl.mockResolvedValue({ url: 'https://storage.test/signed', expires_in: 300 })
    vi.spyOn(window, 'open').mockImplementation(() => null)

    renderRoute(path, pattern, <ReportsPage />)
    await user.click(await screen.findByRole('button', { name: /download/i }))

    await waitFor(() =>
      expect(api.getReportDownloadUrl).toHaveBeenCalledWith(MERCHANT_ID, 'rep-1'),
    )
  })

  it('confirms before deleting a report', async () => {
    const user = userEvent.setup()
    api.listReports.mockResolvedValue({
      count: 1,
      reports: [
        { id: 'rep-1', format: 'pdf', byte_size: 20480, created_at: '2026-03-29T10:00:00+00:00' },
      ],
    })
    renderRoute(path, pattern, <ReportsPage />)

    await user.click(await screen.findByRole('button', { name: /^delete$/i }))
    expect(api.deleteReport).not.toHaveBeenCalled()

    await user.click(screen.getByRole('button', { name: /confirm delete/i }))
    await waitFor(() => expect(api.deleteReport).toHaveBeenCalledWith(MERCHANT_ID, 'rep-1'))
  })
})
