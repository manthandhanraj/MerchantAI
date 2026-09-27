/**
 * Leave the shared demo and open sign-up.
 *
 * The sign-up page is for signed-out visitors, so a plain link from inside the
 * demo bounces straight back to the workspace. Signing out of the demo first
 * is what makes "Create your own account" actually lead somewhere.
 */
import { useCallback, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { useAuth } from './AuthProvider'

export function useStartOwnAccount() {
  const { signOut } = useAuth()
  const navigate = useNavigate()
  const [leaving, setLeaving] = useState(false)

  const start = useCallback(async () => {
    setLeaving(true)
    await signOut()
    navigate('/signup', { replace: true })
  }, [signOut, navigate])

  return { start, leaving }
}
