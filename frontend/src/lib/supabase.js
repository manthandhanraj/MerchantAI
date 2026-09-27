/**
 * The browser's Supabase client.
 *
 * Only the anon key is ever used here. The service-role key bypasses Row Level
 * Security and must never reach a bundle that ships to a browser — it lives in
 * the backend environment alone, and nothing in `frontend/` reads it.
 *
 * The client is created lazily so the public demo still builds and runs on a
 * deployment with no Supabase project configured. `isSupabaseConfigured` is what
 * the UI checks before offering sign-in.
 */
import { createClient } from '@supabase/supabase-js'

import { currentToken } from './localAuth'

const URL = import.meta.env.VITE_SUPABASE_URL ?? ''
const ANON_KEY = import.meta.env.VITE_SUPABASE_ANON_KEY ?? ''

export const isSupabaseConfigured = Boolean(URL && ANON_KEY)

const REMEMBER_KEY = 'merchantai.remember'

/** Whether the last sign-in asked to be remembered. Defaults to true. */
export function isRemembered() {
  try {
    return window.localStorage.getItem(REMEMBER_KEY) !== 'false'
  } catch {
    return true
  }
}

export function setRemembered(remember) {
  try {
    window.localStorage.setItem(REMEMBER_KEY, remember ? 'true' : 'false')
  } catch {
    // Private mode or blocked storage: the session simply lasts the tab.
  }
}

/**
 * Session storage that honours "remember me".
 *
 * Remembered sessions go to localStorage and survive a browser restart.
 * Unremembered ones go to sessionStorage and end with the tab — which is the
 * behaviour a person expects on a shared or public machine. Every access is
 * guarded, because storage throws in private mode rather than returning null.
 */
const rememberAwareStorage = {
  getItem(key) {
    try {
      return window.localStorage.getItem(key) ?? window.sessionStorage.getItem(key)
    } catch {
      return null
    }
  },
  setItem(key, value) {
    try {
      const store = isRemembered() ? window.localStorage : window.sessionStorage
      store.setItem(key, value)
      // Moving between the two must not leave a stale copy behind.
      const other = isRemembered() ? window.sessionStorage : window.localStorage
      other.removeItem(key)
    } catch {
      // Nothing to do: the session lives in memory for this page instead.
    }
  },
  removeItem(key) {
    try {
      window.localStorage.removeItem(key)
      window.sessionStorage.removeItem(key)
    } catch {
      // Already unreachable.
    }
  },
}

let client = null

export function getSupabase() {
  if (!isSupabaseConfigured) return null
  if (!client) {
    client = createClient(URL, ANON_KEY, {
      auth: {
        persistSession: true,
        autoRefreshToken: true,
        // The password-reset link arrives as a URL fragment; letting the client
        // consume it is what turns that link into a usable session.
        detectSessionInUrl: true,
        storageKey: 'merchantai.auth',
        storage: rememberAwareStorage,
      },
    })
  }
  return client
}

/**
 * The current access token, or null.
 *
 * From the Supabase client when a project is configured (it refreshes the
 * token itself), otherwise from the built-in account session.
 */
export async function getAccessToken() {
  const supabase = getSupabase()
  if (!supabase) return currentToken()
  const { data } = await supabase.auth.getSession()
  return data?.session?.access_token ?? null
}

/**
 * Turn a Supabase auth error into something worth showing a person.
 *
 * The raw messages are written for developers ("Invalid login credentials"),
 * and some of them leak whether an account exists, which is a disclosure we do
 * not want to make.
 */
export function friendlyAuthError(error) {
  if (!error) return null
  const raw = String(error.message ?? error)
  const text = raw.toLowerCase()

  if (text.includes('invalid login credentials')) {
    return 'That email and password combination did not work. Check both and try again.'
  }
  if (text.includes('email not confirmed')) {
    return 'Confirm your email address first — check your inbox for the link we sent.'
  }
  if (text.includes('user already registered') || text.includes('already been registered')) {
    return 'An account already exists for that email. Try signing in instead.'
  }
  if (text.includes('password should be at least')) {
    return 'Choose a password of at least six characters.'
  }
  if (text.includes('rate limit') || text.includes('too many')) {
    return 'Too many attempts. Wait a minute and try again.'
  }
  if (text.includes('network') || text.includes('fetch')) {
    return 'Could not reach the server. Check your connection and try again.'
  }
  if (text.includes('token') && text.includes('expired')) {
    return 'That link has expired. Request a new one.'
  }
  return raw
}
