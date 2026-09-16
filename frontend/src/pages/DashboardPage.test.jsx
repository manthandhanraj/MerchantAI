import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import DashboardPage from './DashboardPage'
import {
  askAssistant,
  getActionPlan,
  getAssistantStatus,
  getDashboard,
  getForecast,
  getInsights,
  getMerchants,
} from '../services/api'

vi.mock('../services/api', () => ({
  getMerchants: vi.fn(),
  getDashboard: vi.fn(),
  getActionPlan: vi.fn(),
  getForecast: vi.fn(),
  getInsights: vi.fn(),
  getAssistantStatus: vi.fn(),
  askAssistant: vi.fn(),
  getHealth: vi.fn(),
}))

// A six-month merchant, so the 30D preset and the All preset differ and a
// date change is actually observable.
const MERCHANTS = {
  count: 2,
  merchants: [
    {
      merchant_id: 'M001',
      total_revenue: 17518564.5,
      total_orders: 12385,
      products: 7,
      categories: 2,
      first_date: '2026-01-01',
      last_date: '2026-06-30',
    },
    {
      merchant_id: 'M003',
      total_revenue: 1335230.57,
      total_orders: 16425,
      products: 6,
      categories: 3,
      first_date: '2026-01-01',
      last_date: '2026-06-30',
    },
  ],
}

function buildDashboard(overrides = {}) {
  return {
    merchant_id: 'M001',
    requested_start: '2026-06-01',
    requested_end: '2026-06-30',
    has_data: true,
    summary: {
      period_start: '2026-06-01',
      period_end: '2026-06-30',
      days: 30,
      total_revenue: 3464429.0,
      total_orders: 2362,
      total_units_sold: 2873,
      total_expenses: 2422798.0,
      total_profit: 1041631.0,
      profit_margin: 0.3007,
      average_order_value: 1467.0,
      total_customers: 2111,
      new_customers: 887,
      repeat_customers: 1224,
      repeat_customer_rate: 0.5798,
      revenue_per_customer: 1641.0,
      revenue_growth_rate: -0.149,
      active_products: 7,
      active_categories: 2,
    },
    daily: [
      {
        date: '2026-06-01',
        revenue: 114400.0,
        expenses: 79371.0,
        profit: 35029.0,
        average_order_value: 1430.0,
        orders: 80,
        units_sold: 96,
        customers: 71,
        new_customers: 71,
        repeat_customers: 0,
        profit_margin: 0.3062,
        repeat_customer_rate: 0.0,
      },
    ],
    ...overrides,
  }
}

const EMPTY_SUMMARY = {
  period_start: null,
  period_end: null,
  days: 0,
  total_revenue: 0.0,
  total_orders: 0,
  total_units_sold: 0,
  total_expenses: 0.0,
  total_profit: 0.0,
  profit_margin: 0.0,
  average_order_value: 0.0,
  total_customers: 0,
  new_customers: 0,
  repeat_customers: 0,
  repeat_customer_rate: 0.0,
  revenue_per_customer: 0.0,
  revenue_growth_rate: 0.0,
  active_products: 0,
  active_categories: 0,
}

function buildActionPlan(overrides = {}) {
  return {
    merchant_id: 'M001',
    has_data: true,
    period: { start: '2026-06-01', end: '2026-06-30', days: 30 },
    comparison_period: { start: '2026-05-02', end: '2026-05-31', days: 30 },
    comparison_basis: 'previous_period',
    total_available: 9,
    included: 3,
    truncated: true,
    notes: ['Showing the 3 most significant of 9 suggestions.'],
    high: [
      {
        rank: 1,
        priority: 'High',
        title: 'Reorder Power Bank before it runs out',
        action: 'Power Bank has only a few days of cover left. Place a replenishment order now.',
        reason: 'Power Bank has 1.6 days of stock cover. Cover is below the critical threshold.',
        category: 'Inventory',
        scope: 'Power Bank',
        source_finding: 'inventory-critical-power-bank',
      },
    ],
    medium: [
      {
        rank: 2,
        priority: 'Medium',
        title: 'Protect the revenue you have gained',
        action: 'Identify which products drove the increase and keep them in stock.',
        reason: 'Revenue rose 19.5% versus the previous 30 days.',
        category: 'Revenue',
        scope: 'merchant',
        source_finding: 'total-revenue-up',
      },
    ],
    low: [
      {
        rank: 3,
        priority: 'Low',
        title: 'Decide what to do about Screen Guard',
        action: 'Screen Guard contributes very little revenue. Give it a push or free the shelf space.',
        reason: 'Screen Guard contributes only 2.1% of revenue.',
        category: 'Product',
        scope: 'Screen Guard',
        source_finding: 'product-weak-screen-guard',
      },
    ],
    ...overrides,
  }
}

function buildInsights(overrides = {}) {
  return {
    merchant_id: 'M001',
    requested_start: '2026-06-01',
    requested_end: '2026-06-30',
    has_data: true,
    period: { start: '2026-06-01', end: '2026-06-30', days: 30 },
    comparison_period: { start: '2026-05-02', end: '2026-05-31', days: 30 },
    comparison_basis: 'previous_period',
    finding_count: 2,
    severity_counts: { HIGH: 1, MEDIUM: 1, LOW: 0 },
    notes: [],
    findings: [
      {
        id: 'product-riser-smart-watch',
        category: 'Product',
        severity: 'HIGH',
        title: 'Smart Watch grew 34.7% versus the previous 30 days',
        description: 'Smart Watch earned more this period than over the previous 30 days.',
        metric: 'revenue',
        value: 554000.0,
        unit: 'currency',
        scope: 'Smart Watch',
        reason: 'A change of 34.7% meets the high threshold of 20%.',
        period: { start: '2026-06-01', end: '2026-06-30', days: 30 },
        change: 0.347,
        comparison_value: 411000.0,
        evidence: {},
      },
      {
        id: 'total-revenue-up',
        category: 'Revenue',
        severity: 'MEDIUM',
        title: 'Revenue rose 19.5% versus the previous 30 days',
        description: 'Revenue was higher than over the previous 30 days.',
        metric: 'total_revenue',
        value: 3464429.0,
        unit: 'currency',
        scope: 'merchant',
        reason: 'A change of 19.5% meets the medium threshold of 10%.',
        period: { start: '2026-06-01', end: '2026-06-30', days: 30 },
        change: 0.195,
        comparison_value: 2899000.0,
        evidence: {},
      },
    ],
    ...overrides,
  }
}

function buildForecast(overrides = {}) {
  return {
    merchant_id: 'M001',
    metric: 'revenue',
    available: true,
    reason: null,
    method: 'linear_trend_with_weekday_seasonality',
    history: { start: '2026-06-01', end: '2026-06-30', days: 30 },
    forecast_period: { start: '2026-07-01', end: '2026-07-07', days: 7 },
    points: [
      { date: '2026-07-01', value: 118000.0, weekday: 'Wednesday' },
      { date: '2026-07-02', value: 121000.0, weekday: 'Thursday' },
    ],
    horizon_days: 7,
    requested_horizon_days: 7,
    trend_direction: 'rising',
    trend_per_day: 145.77,
    fit_r_squared: 0.2479,
    backtest: {
      days: 7,
      mean_absolute_error: 21000.0,
      mean_absolute_percentage_error: 0.1988,
      note: 'Measured by refitting on the earlier history. Past accuracy, not a guarantee.',
    },
    confidence_interval: null,
    history_daily_mean: 114400.0,
    forecast_total: 812000.0,
    limitations: [
      'This is a short-term projection only.',
      'No confidence interval is given.',
    ],
    ...overrides,
  }
}

function buildAssistantAnswer(overrides = {}) {
  return {
    merchant_id: 'M001',
    question: 'Why did my sales decrease?',
    answer: 'Revenue rose 19.5% versus the previous 30 days, so nothing reads as a decline.',
    source: 'deterministic',
    llm_enabled: false,
    has_data: true,
    grounded_in: ['summary', 'findings'],
    warnings: [],
    suggested_questions: ['Why did my sales decrease?', 'What should I focus on today?'],
    limitations: ['All figures come from synthetic demo data.'],
    context: null,
    ...overrides,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  getMerchants.mockResolvedValue(MERCHANTS)
  getDashboard.mockResolvedValue(buildDashboard())
  getActionPlan.mockResolvedValue(buildActionPlan())
  getForecast.mockResolvedValue(buildForecast())
  getInsights.mockResolvedValue(buildInsights())
  getAssistantStatus.mockResolvedValue({
    enabled: false,
    flag_set: false,
    key_present: false,
    provider: 'anthropic',
    model: 'claude-sonnet-5',
    suggested_questions: ['Why did my sales decrease?', 'What should I focus on today?'],
  })
  askAssistant.mockResolvedValue(buildAssistantAnswer())
})

describe('loading', () => {
  it('shows a loading state before data arrives', async () => {
    let resolveMerchants
    getMerchants.mockReturnValue(new Promise((resolve) => { resolveMerchants = resolve }))

    render(<DashboardPage />)

    // Assert on the KPI value rather than the label "Revenue", which also
    // appears as an action-plan category chip once the plan loads.
    expect(screen.queryByText('₹34,64,429')).not.toBeInTheDocument()
    expect(document.querySelectorAll('.animate-pulse').length).toBeGreaterThan(0)

    resolveMerchants(MERCHANTS)
    await waitFor(() => expect(screen.getByText('₹34,64,429')).toBeInTheDocument())
  })
})

describe('merchant selector', () => {
  it('is populated from the API, not hardcoded', async () => {
    render(<DashboardPage />)

    const select = await screen.findByLabelText('Merchant')
    const options = within(select).getAllByRole('option')

    expect(options).toHaveLength(2)
    expect(options[0]).toHaveTextContent('M001')
    expect(options[0]).toHaveTextContent('7 products')
    expect(options[1]).toHaveTextContent('M003')
  })

  it('selects the first merchant and requests its data', async () => {
    render(<DashboardPage />)

    await waitFor(() => expect(getDashboard).toHaveBeenCalled())
    expect(getDashboard.mock.calls[0][0]).toMatchObject({ merchantId: 'M001' })
  })

  it('refetches when the merchant changes', async () => {
    const user = userEvent.setup()
    render(<DashboardPage />)

    const select = await screen.findByLabelText('Merchant')
    await waitFor(() => expect(getDashboard).toHaveBeenCalled())
    getDashboard.mockClear()

    await user.selectOptions(select, 'M003')

    await waitFor(() => expect(getDashboard).toHaveBeenCalled())
    expect(getDashboard.mock.calls.at(-1)[0]).toMatchObject({ merchantId: 'M003' })
  })
})

describe('KPI cards', () => {
  it('render values from the API response', async () => {
    render(<DashboardPage />)

    expect(await screen.findByText('₹34,64,429')).toBeInTheDocument() // revenue
    expect(screen.getByText('2,362')).toBeInTheDocument() // orders
    expect(screen.getByText('2,111')).toBeInTheDocument() // customer visits
    expect(screen.getByText('₹10,41,631')).toBeInTheDocument() // gross profit
    expect(screen.getByText('₹1,467')).toBeInTheDocument() // AOV
  })

  it('render rates as percentages, not raw fractions', async () => {
    render(<DashboardPage />)

    expect(await screen.findByText('58.0% repeat')).toBeInTheDocument()
    expect(screen.getByText('30.1% margin')).toBeInTheDocument()
  })

  it('show the revenue change with an explicit comparison label', async () => {
    render(<DashboardPage />)

    expect(await screen.findByText('▼ -14.9%')).toBeInTheDocument()
    expect(screen.getByText('vs previous 7 days')).toBeInTheDocument()
  })

  it('hide the change badge when the period is too short to support it', async () => {
    getDashboard.mockResolvedValue(
      buildDashboard({ summary: { ...buildDashboard().summary, days: 5 } }),
    )
    render(<DashboardPage />)

    await screen.findByText('₹34,64,429')
    expect(screen.queryByText('vs previous 7 days')).not.toBeInTheDocument()
  })

  it('never render NaN, Infinity or undefined', async () => {
    render(<DashboardPage />)
    await screen.findByText('₹34,64,429')

    const text = document.body.textContent
    expect(text).not.toMatch(/NaN|Infinity|undefined|\[object Object\]/)
  })
})

describe('date range', () => {
  it('defaults to the last 30 days of the merchant data, not today', async () => {
    render(<DashboardPage />)

    await waitFor(() => expect(getDashboard).toHaveBeenCalled())
    // last_date is 2026-06-30, so a 30-day window starts 2026-06-01.
    expect(getDashboard.mock.calls[0][0]).toMatchObject({
      start: '2026-06-01',
      end: '2026-06-30',
    })
  })

  it('refetches with a wider range when a preset changes', async () => {
    const user = userEvent.setup()
    render(<DashboardPage />)

    await waitFor(() => expect(getDashboard).toHaveBeenCalled())
    getDashboard.mockClear()

    await user.click(screen.getByRole('button', { name: 'All' }))

    await waitFor(() => expect(getDashboard).toHaveBeenCalled())
    expect(getDashboard.mock.calls.at(-1)[0]).toMatchObject({
      start: '2026-01-01',
      end: '2026-06-30',
    })
  })

  it('refetches when a date input is edited directly', async () => {
    render(<DashboardPage />)

    const startInput = await screen.findByLabelText('From')
    await waitFor(() => expect(getDashboard).toHaveBeenCalled())
    getDashboard.mockClear()

    // fireEvent-style change: date inputs do not accept typed text reliably.
    const { fireEvent } = await import('@testing-library/react')
    fireEvent.change(startInput, { target: { value: '2026-03-15' } })

    await waitFor(() => expect(getDashboard).toHaveBeenCalled())
    expect(getDashboard.mock.calls.at(-1)[0]).toMatchObject({ start: '2026-03-15' })
  })

  it('shows the period actually returned by the API', async () => {
    render(<DashboardPage />)
    // Scoped to the "Showing …" line: "30 days" also appears inside action
    // reasons such as "versus the previous 30 days".
    const summaryLine = await screen.findByText(
      (_content, element) =>
        element?.tagName.toLowerCase() === 'p' &&
        element.textContent.trim().startsWith('Showing'),
    )
    expect(summaryLine).toHaveTextContent('30 days')
  })
})

describe('empty state', () => {
  it('explains an empty range instead of showing zeros as if they were real', async () => {
    getDashboard.mockResolvedValue(
      buildDashboard({ has_data: false, summary: EMPTY_SUMMARY, daily: [] }),
    )
    render(<DashboardPage />)

    expect(await screen.findByText('No activity in this period')).toBeInTheDocument()
    expect(screen.queryByText('Revenue')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Show all data' })).toBeInTheDocument()
  })
})

describe('error state', () => {
  it('surfaces the API error message for the merchant list', async () => {
    getMerchants.mockRejectedValue(new Error('Dataset not found'))
    render(<DashboardPage />)

    expect(await screen.findByText('Could not load merchants')).toBeInTheDocument()
    expect(screen.getByText('Dataset not found')).toBeInTheDocument()
  })

  it('surfaces the API error message for the dashboard', async () => {
    getDashboard.mockRejectedValue(new Error("Unknown merchant 'ZZZ'"))
    render(<DashboardPage />)

    expect(await screen.findByText('Could not load dashboard data')).toBeInTheDocument()
    expect(screen.getByText("Unknown merchant 'ZZZ'")).toBeInTheDocument()
  })

  it('recovers when the retry action succeeds', async () => {
    const user = userEvent.setup()
    getDashboard.mockRejectedValueOnce(new Error('Boom'))
    render(<DashboardPage />)

    await screen.findByText('Could not load dashboard data')

    getDashboard.mockResolvedValue(buildDashboard())
    await user.click(screen.getByRole('button', { name: 'Try again' }))

    expect(await screen.findByText('₹34,64,429')).toBeInTheDocument()
    expect(screen.queryByText('Could not load dashboard data')).not.toBeInTheDocument()
  })
})

describe('action plan', () => {
  it('renders the prioritised buckets from the API', async () => {
    render(<DashboardPage />)

    expect(await screen.findByRole('heading', { name: 'Action plan' })).toBeInTheDocument()
    expect(screen.getByText('High priority')).toBeInTheDocument()
    expect(screen.getByText('Medium priority')).toBeInTheDocument()
    expect(screen.getByText('Low priority')).toBeInTheDocument()
  })

  it('shows each action with the finding that justifies it', async () => {
    render(<DashboardPage />)

    expect(
      await screen.findByText('1. Reorder Power Bank before it runs out'),
    ).toBeInTheDocument()
    expect(
      screen.getByText(/Power Bank has 1\.6 days of stock cover/),
    ).toBeInTheDocument()
  })

  it('requests the plan for the selected merchant and range', async () => {
    render(<DashboardPage />)

    await waitFor(() => expect(getActionPlan).toHaveBeenCalled())
    expect(getActionPlan.mock.calls[0][0]).toMatchObject({
      merchantId: 'M001',
      start: '2026-06-01',
      end: '2026-06-30',
    })
  })

  it('refetches the plan when the merchant changes', async () => {
    const user = userEvent.setup()
    render(<DashboardPage />)

    const select = await screen.findByLabelText('Merchant')
    await waitFor(() => expect(getActionPlan).toHaveBeenCalled())
    getActionPlan.mockClear()

    await user.selectOptions(select, 'M003')

    await waitFor(() => expect(getActionPlan).toHaveBeenCalled())
    expect(getActionPlan.mock.calls.at(-1)[0]).toMatchObject({ merchantId: 'M003' })
  })

  it('reports what was left out rather than hiding it', async () => {
    render(<DashboardPage />)
    expect(
      await screen.findByText('Showing the 3 most significant of 9 suggestions.'),
    ).toBeInTheDocument()
  })

  it('says so plainly when nothing needs attention', async () => {
    getActionPlan.mockResolvedValue(
      buildActionPlan({
        high: [],
        medium: [],
        low: [],
        total_available: 0,
        included: 0,
        truncated: false,
        notes: [],
      }),
    )
    render(<DashboardPage />)

    expect(await screen.findByText(/Nothing needs attention/)).toBeInTheDocument()
  })

  it('keeps the dashboard usable when only the plan fails', async () => {
    getActionPlan.mockRejectedValue(new Error('plan unavailable'))
    render(<DashboardPage />)

    // KPI cards still render; only the plan shows an error.
    expect(await screen.findByText('₹34,64,429')).toBeInTheDocument()
    expect(screen.getByText('Could not load the action plan')).toBeInTheDocument()
    expect(screen.getByText('plan unavailable')).toBeInTheDocument()
  })

  it('is hidden while the dashboard itself has no data', async () => {
    getDashboard.mockResolvedValue(
      buildDashboard({ has_data: false, summary: EMPTY_SUMMARY, daily: [] }),
    )
    render(<DashboardPage />)

    await screen.findByText('No activity in this period')
    expect(screen.queryByRole('heading', { name: 'Action plan' })).not.toBeInTheDocument()
  })
})

describe('forecast', () => {
  it('renders the projection with its measured error and method', async () => {
    render(<DashboardPage />)

    expect(await screen.findByRole('heading', { name: 'Revenue forecast' })).toBeInTheDocument()
    expect(screen.getByText('₹8,12,000')).toBeInTheDocument() // projected total
    expect(screen.getByText('19.9%')).toBeInTheDocument() // measured backtest error
    expect(screen.getByText(/linear trend with weekday seasonality/)).toBeInTheDocument()
    expect(screen.getByText('Rising trend')).toBeInTheDocument()
  })

  it('always states what the forecast cannot do', async () => {
    render(<DashboardPage />)

    expect(await screen.findByText('This is a short-term projection only.')).toBeInTheDocument()
    expect(screen.getByText('No confidence interval is given.')).toBeInTheDocument()
  })

  it('explains an unavailable forecast instead of drawing an empty chart', async () => {
    getForecast.mockResolvedValue(
      buildForecast({
        available: false,
        reason: 'Only 6 day(s) of history in this period.',
        points: [],
        forecast_period: null,
      }),
    )
    render(<DashboardPage />)

    expect(
      await screen.findByText('Only 6 day(s) of history in this period.'),
    ).toBeInTheDocument()
    expect(screen.queryByText('Rising trend')).not.toBeInTheDocument()
  })

  it('requests the forecast for the selected merchant and range', async () => {
    render(<DashboardPage />)

    await waitFor(() => expect(getForecast).toHaveBeenCalled())
    expect(getForecast.mock.calls[0][0]).toMatchObject({
      merchantId: 'M001',
      start: '2026-06-01',
      end: '2026-06-30',
    })
  })

  it('keeps the dashboard usable when only the forecast fails', async () => {
    getForecast.mockRejectedValue(new Error('forecast unavailable'))
    render(<DashboardPage />)

    expect(await screen.findByText('₹34,64,429')).toBeInTheDocument() // KPIs survive
    expect(screen.getByText('Could not load the forecast')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Action plan' })).toBeInTheDocument()
  })
})

describe('assistant', () => {
  it('offers starter questions', async () => {
    render(<DashboardPage />)

    expect(
      await screen.findByRole('heading', { name: 'Ask about this business' }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: 'What should I focus on today?' }),
    ).toBeInTheDocument()
  })

  it('says it is answering from data when the model is off', async () => {
    render(<DashboardPage />)
    expect(await screen.findByText('Answering from data')).toBeInTheDocument()
  })

  it('asks and renders a grounded answer', async () => {
    const user = userEvent.setup()
    render(<DashboardPage />)

    await user.click(await screen.findByRole('button', { name: 'Why did my sales decrease?' }))

    await waitFor(() => expect(askAssistant).toHaveBeenCalled())
    expect(askAssistant.mock.calls[0][0]).toMatchObject({
      merchantId: 'M001',
      question: 'Why did my sales decrease?',
    })
    expect(await screen.findByText(/nothing reads as a decline/)).toBeInTheDocument()
    expect(screen.getByText(/Composed directly from this merchant/)).toBeInTheDocument()
  })

  it('accepts a typed question', async () => {
    const user = userEvent.setup()
    render(<DashboardPage />)

    const input = await screen.findByLabelText('Your question')
    await user.type(input, 'How are my customers?')
    await user.click(screen.getByRole('button', { name: 'Ask' }))

    await waitFor(() => expect(askAssistant).toHaveBeenCalled())
    expect(askAssistant.mock.calls.at(-1)[0].question).toBe('How are my customers?')
  })

  it('surfaces a warning when a model reply was rejected', async () => {
    askAssistant.mockResolvedValue(
      buildAssistantAnswer({
        warnings: ['The language model’s reply contained figures that could not be traced.'],
      }),
    )
    const user = userEvent.setup()
    render(<DashboardPage />)

    await user.click(await screen.findByRole('button', { name: 'Why did my sales decrease?' }))

    expect(await screen.findByText(/could not be traced/)).toBeInTheDocument()
  })

  it('keeps the dashboard usable when the assistant fails', async () => {
    askAssistant.mockRejectedValue(new Error('assistant unavailable'))
    const user = userEvent.setup()
    render(<DashboardPage />)

    await user.click(await screen.findByRole('button', { name: 'Why did my sales decrease?' }))

    expect(await screen.findByText('assistant unavailable')).toBeInTheDocument()
    expect(screen.getByText('₹34,64,429')).toBeInTheDocument() // KPIs survive
    expect(screen.getByRole('heading', { name: 'Revenue forecast' })).toBeInTheDocument()
  })
})

describe('insights', () => {
  it('renders findings with the threshold that flagged them', async () => {
    render(<DashboardPage />)

    expect(await screen.findByRole('heading', { name: 'AI insights' })).toBeInTheDocument()
    expect(
      screen.getByText('Smart Watch grew 34.7% versus the previous 30 days'),
    ).toBeInTheDocument()
    expect(
      screen.getByText(/A change of 34\.7% meets the high threshold of 20%/),
    ).toBeInTheDocument()
  })

  it('summarises severity at a glance', async () => {
    render(<DashboardPage />)

    expect(await screen.findByText('1 high')).toBeInTheDocument()
    expect(screen.getByText('1 medium')).toBeInTheDocument()
  })

  it('says so plainly when nothing was flagged', async () => {
    getInsights.mockResolvedValue(
      buildInsights({ findings: [], finding_count: 0, severity_counts: { HIGH: 0, MEDIUM: 0, LOW: 0 } }),
    )
    render(<DashboardPage />)

    expect(await screen.findByText(/Nothing in this period moved far enough/)).toBeInTheDocument()
  })

  it('requests insights for the selected merchant and range', async () => {
    render(<DashboardPage />)

    await waitFor(() => expect(getInsights).toHaveBeenCalled())
    expect(getInsights.mock.calls[0][0]).toMatchObject({
      merchantId: 'M001',
      start: '2026-06-01',
      end: '2026-06-30',
    })
  })
})

describe('integration', () => {
  it('lays the sections out in the intended reading order', async () => {
    render(<DashboardPage />)
    await screen.findByRole('heading', { name: 'AI insights' })

    const order = Array.from(document.querySelectorAll('h3')).map((h) => h.textContent)
    const position = (label) => order.indexOf(label)

    expect(position('Revenue and gross profit')).toBeLessThan(position('AI insights'))
    expect(position('AI insights')).toBeLessThan(position('Action plan'))
    expect(position('Action plan')).toBeLessThan(position('Revenue forecast'))
    expect(position('Revenue forecast')).toBeLessThan(position('Ask about this business'))
  })

  it('drives every feature from one merchant and date selection', async () => {
    render(<DashboardPage />)
    await waitFor(() => expect(getInsights).toHaveBeenCalled())

    const expected = { merchantId: 'M001', start: '2026-06-01', end: '2026-06-30' }
    expect(getDashboard.mock.calls[0][0]).toMatchObject(expected)
    expect(getInsights.mock.calls[0][0]).toMatchObject(expected)
    expect(getActionPlan.mock.calls[0][0]).toMatchObject(expected)
    expect(getForecast.mock.calls[0][0]).toMatchObject(expected)
  })

  it('refetches every feature when the merchant changes', async () => {
    const user = userEvent.setup()
    render(<DashboardPage />)

    const select = await screen.findByLabelText('Merchant')
    await waitFor(() => expect(getForecast).toHaveBeenCalled())
    ;[getDashboard, getInsights, getActionPlan, getForecast].forEach((fn) => fn.mockClear())

    await user.selectOptions(select, 'M003')

    await waitFor(() => expect(getForecast).toHaveBeenCalled())
    for (const fn of [getDashboard, getInsights, getActionPlan, getForecast]) {
      expect(fn.mock.calls.at(-1)[0]).toMatchObject({ merchantId: 'M003' })
    }
  })

  it('refetches every feature when the date preset changes', async () => {
    const user = userEvent.setup()
    render(<DashboardPage />)

    await waitFor(() => expect(getForecast).toHaveBeenCalled())
    ;[getDashboard, getInsights, getActionPlan, getForecast].forEach((fn) => fn.mockClear())

    await user.click(screen.getByRole('button', { name: 'All' }))

    await waitFor(() => expect(getForecast).toHaveBeenCalled())
    for (const fn of [getDashboard, getInsights, getActionPlan, getForecast]) {
      expect(fn.mock.calls.at(-1)[0]).toMatchObject({ start: '2026-01-01', end: '2026-06-30' })
    }
  })

  it('isolates failures so one broken feature cannot blank the others', async () => {
    getInsights.mockRejectedValue(new Error('insights down'))
    getForecast.mockRejectedValue(new Error('forecast down'))
    render(<DashboardPage />)

    // The two failures are reported...
    expect(await screen.findByText('insights down')).toBeInTheDocument()
    expect(screen.getByText('forecast down')).toBeInTheDocument()

    // ...while everything else still renders.
    expect(screen.getByText('₹34,64,429')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Action plan' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Ask about this business' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Revenue and gross profit' })).toBeInTheDocument()
  })

  it('hides every downstream feature when the period has no data', async () => {
    getDashboard.mockResolvedValue(
      buildDashboard({ has_data: false, summary: EMPTY_SUMMARY, daily: [] }),
    )
    render(<DashboardPage />)

    await screen.findByText('No activity in this period')
    for (const heading of ['AI insights', 'Action plan', 'Revenue forecast', 'Ask about this business']) {
      expect(screen.queryByRole('heading', { name: heading })).not.toBeInTheDocument()
    }
  })

  it('keeps the rest of the dashboard when only the forecast lacks history', async () => {
    getForecast.mockResolvedValue(
      buildForecast({ available: false, reason: 'Only 7 day(s) of history.', points: [] }),
    )
    render(<DashboardPage />)

    expect(await screen.findByText('Only 7 day(s) of history.')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'AI insights' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Action plan' })).toBeInTheDocument()
    expect(screen.getByText('₹34,64,429')).toBeInTheDocument()
  })
})

describe('malformed payloads', () => {
  /**
   * Regression: ForecastPanel dereferenced `method`, `forecast_period` and
   * `limitations` unguarded. A response missing any of them threw during
   * render, which — with no boundary — unmounted the entire dashboard rather
   * than just that panel.
   */
  const broken = {
    'null method': { method: null },
    'null forecast_period': { forecast_period: null },
    'missing limitations': { limitations: undefined },
    'missing points': { points: undefined },
  }

  for (const [label, override] of Object.entries(broken)) {
    it(`survives a forecast payload with ${label}`, async () => {
      getForecast.mockResolvedValue(buildForecast(override))
      render(<DashboardPage />)

      // The rest of the dashboard still renders.
      expect(await screen.findByText('₹34,64,429')).toBeInTheDocument()
      expect(screen.getByRole('heading', { name: 'AI insights' })).toBeInTheDocument()
      expect(screen.getByRole('heading', { name: 'Action plan' })).toBeInTheDocument()
    })
  }

  it('survives an insights payload with null findings', async () => {
    getInsights.mockResolvedValue(
      buildInsights({ findings: null, severity_counts: null, notes: null }),
    )
    render(<DashboardPage />)

    expect(await screen.findByText('₹34,64,429')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Action plan' })).toBeInTheDocument()
  })

  it('survives an action-plan payload with null buckets', async () => {
    getActionPlan.mockResolvedValue(
      buildActionPlan({ high: null, medium: null, low: null, notes: null }),
    )
    render(<DashboardPage />)

    expect(await screen.findByText('₹34,64,429')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'AI insights' })).toBeInTheDocument()
  })

  it('survives a merchants payload with no merchants key', async () => {
    getMerchants.mockResolvedValue({})
    render(<DashboardPage />)

    const select = await screen.findByLabelText('Merchant')
    expect(select).toBeInTheDocument()
    expect(screen.getByText('No merchants available')).toBeInTheDocument()
  })
})

describe('charts', () => {
  it('renders a chart panel per trend once data is present', async () => {
    render(<DashboardPage />)

    // Queried by heading role: "Orders" is also a KPI card label, so a plain
    // text query matches two elements.
    expect(
      await screen.findByRole('heading', { name: 'Revenue and gross profit' }),
    ).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Orders' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Customers: new vs repeat' })).toBeInTheDocument()
  })
})
