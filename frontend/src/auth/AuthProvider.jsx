/**
 * Authentication state for the whole application.
 *
 * One interface over two account systems:
 *
 *  - **Supabase**, when a project is configured. The Supabase client owns the
 *    session, persists it and refreshes it; this provider mirrors it into React.
 *  - **Built-in accounts** otherwise. The MerchantAI backend hashes passwords,
 *    signs tokens and verifies them on every request; the browser keeps only
 *    the signed token it was handed.
 *
 * Every screen calls the same `signUp`, `signIn`, `signOut` and
 * `updatePassword`, so nothing above this file knows or cares which is in use.
 * It never stores a password, in either mode.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'

import {
  UNAUTHORIZED_EVENT,
  changePasswordRequest,
  clearSession,
  deleteAccountRequest,
  readSession,
  signInRequest,
  signUpRequest,
  writeSession,
} from '../lib/localAuth'
import { friendlyAuthError, getSupabase } from '../lib/supabase'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const supabase = getSupabase()
  const local = !supabase

  // Built-in sessions are read synchronously, so there is nothing to wait for.
  const [session, setSession] = useState(() => (local ? readSession() : null))
  // With Supabase, start in a loading state so a signed-in user is not bounced
  // to the login page before the stored session has been read.
  const [loading, setLoading] = useState(!local)

  // ---- Supabase session mirror ------------------------------------------
  useEffect(() => {
    if (!supabase) return undefined
    let active = true

    supabase.auth
      .getSession()
      .then(({ data }) => {
        if (!active) return
        setSession(data?.session ?? null)
        setLoading(false)
      })
      .catch(() => {
        if (active) setLoading(false)
      })

    const { data: subscription } = supabase.auth.onAuthStateChange((_event, next) => {
      if (!active) return
      setSession(next)
      setLoading(false)
    })

    return () => {
      active = false
      subscription?.subscription?.unsubscribe()
    }
  }, [supabase])

  // ---- built-in: expiry and server-side rejection -----------------------
  useEffect(() => {
    if (!local) return undefined

    // A token the server refuses (expired, or the account was deleted) ends
    // the session here too, rather than leaving the UI signed in to nothing.
    function onUnauthorized() {
      clearSession()
      setSession(null)
    }
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized)

    // Another tab signing in or out is reflected in this one.
    function onStorage(event) {
      if (event.key === 'merchantai.session') setSession(readSession())
    }
    window.addEventListener('storage', onStorage)

    return () => {
      window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized)
      window.removeEventListener('storage', onStorage)
    }
  }, [local])

  // ---- actions ------------------------------------------------------------
  const signUp = useCallback(
    async ({ email, password, fullName }) => {
      if (local) {
        const created = await signUpRequest({ email, password, fullName })
        writeSession(created)
        setSession(created)
        // Same shape as Supabase's response, so the sign-up page handles both.
        return { user: created.user, session: created }
      }
      const { data, error } = await supabase.auth.signUp({
        email: email.trim(),
        password,
        options: {
          // Copied into the profile row by a database trigger.
          data: { full_name: (fullName ?? '').trim() || null },
          emailRedirectTo: `${window.location.origin}/app`,
        },
      })
      if (error) throw new Error(friendlyAuthError(error))
      return data
    },
    [local, supabase],
  )

  const signIn = useCallback(
    async ({ email, password }) => {
      if (local) {
        const signedIn = await signInRequest({ email, password })
        writeSession(signedIn)
        setSession(signedIn)
        return { user: signedIn.user, session: signedIn }
      }
      const { data, error } = await supabase.auth.signInWithPassword({
        email: email.trim(),
        password,
      })
      if (error) throw new Error(friendlyAuthError(error))
      return data
    },
    [local, supabase],
  )

  const signOut = useCallback(async () => {
    if (local) {
      clearSession()
    } else {
      await supabase.auth.signOut()
    }
    setSession(null)
  }, [local, supabase])

  const requestPasswordReset = useCallback(
    async (email) => {
      if (local) {
        // There is no email service behind built-in accounts. Saying so is
        // better than pretending a message was sent.
        throw new Error(
          'Password reset by email is not available on this installation. Ask the ' +
            'administrator to reset it with scripts/reset_password.py.',
        )
      }
      const { error } = await supabase.auth.resetPasswordForEmail(email.trim(), {
        redirectTo: `${window.location.origin}/reset-password`,
      })
      // A failure here would reveal whether the address has an account, so the
      // caller always reports the same thing. Genuine outages still surface.
      if (error && !/user|email/i.test(error.message ?? '')) {
        throw new Error(friendlyAuthError(error))
      }
    },
    [local, supabase],
  )

  const updatePassword = useCallback(
    async (password) => {
      if (local) {
        await changePasswordRequest(password)
        return
      }
      const { error } = await supabase.auth.updateUser({ password })
      if (error) throw new Error(friendlyAuthError(error))
    },
    [local, supabase],
  )

  const deleteAccount = useCallback(async () => {
    if (!local) {
      throw new Error(
        'Account deletion is handled by the administrator on this installation.',
      )
    }
    await deleteAccountRequest()
    clearSession()
    setSession(null)
  }, [local])

  const value = useMemo(
    () => ({
      // Accounts exist in both modes now; `configured` stays for callers that
      // still check it.
      configured: true,
      mode: local ? 'local' : 'supabase',
      canResetByEmail: !local,
      canDeleteAccount: local,
      loading,
      session,
      user: session?.user ?? null,
      signUp,
      signIn,
      signOut,
      requestPasswordReset,
      updatePassword,
      deleteAccount,
    }),
    [
      local,
      loading,
      session,
      signUp,
      signIn,
      signOut,
      requestPasswordReset,
      updatePassword,
      deleteAccount,
    ],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth must be used inside an AuthProvider.')
  return value
}
