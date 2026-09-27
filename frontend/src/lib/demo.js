/**
 * The shared demo account, as the browser knows it.
 *
 * These credentials are deliberately public: they open a seeded, synthetic,
 * read-only workspace and nothing else. They are still read from environment
 * variables rather than hardcoded, so a deployment can point at its own demo
 * account — or omit one entirely, in which case the login page simply does not
 * offer it.
 *
 * Only `VITE_`-prefixed values appear here. Service-role keys and JWT secrets
 * are backend-only and are never imported into this bundle.
 */
import { useCallback, useEffect, useState } from 'react'

import { fetchDemoCredentials } from './localAuth'
import { isSupabaseConfigured } from './supabase'

const EMAIL = import.meta.env.VITE_DEMO_EMAIL ?? ''
const PASSWORD = import.meta.env.VITE_DEMO_PASSWORD ?? ''

export const demoAccount = {
  email: EMAIL,
  password: PASSWORD,
  workspaceUrl: null,
  /** Both halves are needed; half a credential helps nobody. */
  available: Boolean(EMAIL && PASSWORD),
}

export const DEMO_NOT_SET_UP = 'This installation does not offer a demo account.'

/**
 * The demo credentials to show on the login page, and `load()` to fetch them
 * on demand.
 *
 * With Supabase they come from the build environment. With built-in accounts
 * they come from the backend, which creates the demo account on first use — so
 * the password displayed is always the password that works.
 *
 * `offered` is false only when the installation has deliberately no demo. While
 * the details are still loading, or after fetching them failed, the demo stays
 * on offer: pressing its button fetches them again and, if that fails too, the
 * page can say why instead of the option silently disappearing.
 */
export function useDemoCredentials() {
  const [state, setState] = useState(() =>
    isSupabaseConfigured
      ? { ...demoAccount, offered: demoAccount.available, error: null }
      : { email: '', password: '', available: false, offered: true, error: null },
  )

  const load = useCallback(async () => {
    if (isSupabaseConfigured) {
      if (!demoAccount.available) throw new Error(DEMO_NOT_SET_UP)
      return demoAccount
    }

    let body
    try {
      body = await fetchDemoCredentials()
    } catch (caught) {
      setState((current) => ({ ...current, error: caught.message }))
      throw caught
    }
    if (!body?.available) {
      setState({ email: '', password: '', available: false, offered: false, error: null })
      throw new Error(DEMO_NOT_SET_UP)
    }

    const account = {
      email: body.email,
      password: body.password,
      workspaceUrl: body.workspace_url || null,
      available: true,
    }
    setState({ ...account, offered: true, error: null })
    return account
  }, [])

  useEffect(() => {
    if (isSupabaseConfigured) return
    load().catch(() => {
      // Recorded in `error`; the demo button retries and reports it.
    })
  }, [load])

  return { ...state, load }
}
