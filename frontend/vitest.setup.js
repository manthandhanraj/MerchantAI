import { configure } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'

// Several private screens await four parallel requests and then render a chart.
// Testing Library waits 1s by default, which is comfortable on an idle machine
// and marginal on a loaded one — a suite run alongside the backend tests was
// timing out here. This changes how long the same assertions wait, not what
// they assert.
configure({ asyncUtilTimeout: 5000 })
