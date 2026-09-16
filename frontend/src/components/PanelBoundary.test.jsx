import { render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { PanelBoundary } from './PanelBoundary'

function Exploding() {
  throw new Error('payload was not what the panel expected')
}

beforeEach(() => {
  // React logs the caught error; silence it so the run stays readable.
  vi.spyOn(console, 'error').mockImplementation(() => {})
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('PanelBoundary', () => {
  it('renders its children when nothing goes wrong', () => {
    render(
      <PanelBoundary name="Forecast">
        <p>chart goes here</p>
      </PanelBoundary>,
    )
    expect(screen.getByText('chart goes here')).toBeInTheDocument()
  })

  it('contains a render failure and names the panel', () => {
    render(
      <PanelBoundary name="Forecast">
        <Exploding />
      </PanelBoundary>,
    )

    expect(screen.getByRole('alert')).toBeInTheDocument()
    expect(screen.getByText('Forecast could not be displayed')).toBeInTheDocument()
    expect(screen.getByText(/payload was not what the panel expected/)).toBeInTheDocument()
  })

  it('tells the reader the rest of the page is unaffected', () => {
    render(
      <PanelBoundary name="Insights">
        <Exploding />
      </PanelBoundary>,
    )
    expect(screen.getByText(/rest of the dashboard is unaffected/)).toBeInTheDocument()
  })

  it('leaves sibling content standing', () => {
    render(
      <div>
        <PanelBoundary name="Forecast">
          <Exploding />
        </PanelBoundary>
        <p>KPI cards</p>
      </div>,
    )

    expect(screen.getByRole('alert')).toBeInTheDocument()
    expect(screen.getByText('KPI cards')).toBeInTheDocument()
  })
})
