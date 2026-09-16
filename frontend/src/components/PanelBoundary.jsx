/**
 * Keeps one panel's render failure from blanking the page.
 *
 * Every section fetches independently, so a failed *request* is already
 * isolated. A failed *render* is not: without a boundary, one malformed payload
 * unmounts the whole dashboard. This makes that failure local and visible.
 */
import { Component } from 'react'

export class PanelBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { error: null }
  }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error) {
    // Surface it for debugging; the panel below shows the user-facing message.
    console.error(`[${this.props.name}] failed to render:`, error)
  }

  render() {
    if (this.state.error) {
      return (
        <section
          role="alert"
          className="rounded-xl border border-red-200 bg-red-50 p-4 shadow-sm sm:p-5"
        >
          <h3 className="text-sm font-semibold text-red-700">
            {this.props.name} could not be displayed
          </h3>
          <p className="mt-1 text-sm text-red-700">
            The rest of the dashboard is unaffected. {this.state.error.message}
          </p>
        </section>
      )
    }
    return this.props.children
  }
}
