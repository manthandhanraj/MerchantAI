/**
 * Tracks the user's reduced-motion preference.
 *
 * CSS handles the animations declared in index.css, but Recharts decides
 * whether to animate in JavaScript — a media query cannot reach it. This hook
 * is what lets the charts honour the same preference as everything else.
 */
import { useEffect, useState } from 'react'

const QUERY = '(prefers-reduced-motion: reduce)'

function readPreference() {
  // jsdom and older browsers have no matchMedia; assume motion is fine.
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return false
  return window.matchMedia(QUERY).matches
}

export function usePrefersReducedMotion() {
  const [prefersReduced, setPrefersReduced] = useState(readPreference)

  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return undefined

    const list = window.matchMedia(QUERY)
    const onChange = (event) => setPrefersReduced(event.matches)

    // Safari below 14 only has the deprecated listener API.
    if (typeof list.addEventListener === 'function') {
      list.addEventListener('change', onChange)
      return () => list.removeEventListener('change', onChange)
    }
    list.addListener(onChange)
    return () => list.removeListener(onChange)
  }, [])

  return prefersReduced
}
