/**
 * Workspace-level facts that every private screen needs: the profile, whether
 * onboarding is still outstanding, and whether this is the shared demo.
 *
 * Fetched once at the layout level rather than per page, so opening the
 * dashboard does not re-ask who you are.
 *
 * `readOnly` here only drives the interface. The backend refuses every mutating
 * call from the demo account regardless, so hiding a button is a courtesy and
 * not the control.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'

import { getMe } from '../services/privateApi'

const WorkspaceContext = createContext(null)

export function WorkspaceProvider({ children }) {
  const [state, setState] = useState({ loading: true, error: null, me: null })

  const load = useCallback(async (signal) => {
    setState((current) => ({ ...current, loading: true, error: null }))
    try {
      const me = await getMe({ signal })
      if (signal?.aborted) return
      setState({ loading: false, error: null, me })
    } catch (error) {
      if (signal?.aborted) return
      setState({ loading: false, error: error.message, me: null })
    }
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    load(controller.signal)
    return () => controller.abort()
  }, [load])

  const value = useMemo(
    () => ({
      loading: state.loading,
      error: state.error,
      profile: state.me?.profile ?? null,
      merchantCount: state.me?.merchant_count ?? 0,
      needsOnboarding: Boolean(state.me?.needs_onboarding),
      isDemo: Boolean(state.me?.is_demo),
      readOnly: Boolean(state.me?.read_only),
      // Undefined until known, so no warning flashes while loading.
      persistentStorage: state.me ? state.me.persistent_storage !== false : undefined,
      authMode: state.me?.auth_mode ?? null,
      refresh: () => load(),
    }),
    [state, load],
  )

  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>
}

export function useWorkspace() {
  // Defaulted rather than thrown, so a component rendered in isolation by a
  // test does not have to be wrapped just to read a flag it may not use.
  return (
    useContext(WorkspaceContext) ?? {
      loading: false,
      error: null,
      profile: null,
      merchantCount: 0,
      needsOnboarding: false,
      isDemo: false,
      readOnly: false,
      persistentStorage: undefined,
      authMode: null,
      refresh: () => {},
    }
  )
}
