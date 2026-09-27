/**
 * Route guards.
 *
 * These are a convenience for the person using the app, not a security control.
 * The real boundary is the verified token the backend checks on every private
 * endpoint and the Row Level Security policies in the database — removing these
 * components would change what the UI shows, not what data is reachable.
 */
import { Navigate, Outlet, useLocation } from 'react-router-dom'

import { useAuth } from './AuthProvider'
import { WorkspaceProvider } from './WorkspaceProvider'
import { FullPageState, Spinner } from '../components/ui'

/** Requires a session. Sends anyone else to sign in, remembering where they were. */
export function RequireAuth() {
  const { loading, session, configured } = useAuth()
  const location = useLocation()

  if (!configured) {
    // No account system on this deployment. The login page explains that and
    // offers the local demo, so it is a better destination than a dead end.
    return <Navigate to="/login" replace />
  }

  if (loading) {
    return (
      <FullPageState>
        <Spinner label="Checking your session…" />
      </FullPageState>
    )
  }

  if (!session) {
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />
  }

  return (
    <WorkspaceProvider>
      <Outlet />
    </WorkspaceProvider>
  )
}

/** Keeps a signed-in person out of the sign-in and sign-up screens. */
export function RequireAnon() {
  const { loading, session, configured } = useAuth()
  const location = useLocation()

  if (loading && configured) {
    return (
      <FullPageState>
        <Spinner label="Checking your session…" />
      </FullPageState>
    )
  }

  if (session) {
    const target = location.state?.from
    return <Navigate to={target && target.startsWith('/app') ? target : '/app'} replace />
  }

  return <Outlet />
}
