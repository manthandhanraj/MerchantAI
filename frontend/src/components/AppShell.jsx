/**
 * Chrome for the authenticated workspace: navigation, merchant switcher and
 * the sign-out control. Mirrors the public dashboard's TopNav so the private
 * product reads as the same application rather than a bolted-on admin area.
 */
import { useState } from 'react'
import { Link, NavLink, useNavigate } from 'react-router-dom'

import { useAuth } from '../auth/AuthProvider'
import { useStartOwnAccount } from '../auth/useStartOwnAccount'
import { useWorkspace } from '../auth/WorkspaceProvider'

function initials(email, name) {
  const source = (name || email || '').trim()
  if (!source) return '—'
  const parts = source.split(/[\s@._-]+/).filter(Boolean)
  return (parts[0]?.[0] ?? '').concat(parts[1]?.[0] ?? '').toUpperCase() || source[0].toUpperCase()
}

export function AppShell({ children, merchants = [], activeMerchantId = null }) {
  const { user, signOut } = useAuth()
  const workspace = useWorkspace()
  const isDemo = workspace.isDemo
  const navigate = useNavigate()
  const [signingOut, setSigningOut] = useState(false)
  const { start: startOwnAccount, leaving: leavingDemo } = useStartOwnAccount()

  const links = [
    { to: '/app', label: 'Overview', end: true },
    ...(activeMerchantId
      ? [
          { to: `/app/merchant/${activeMerchantId}`, label: 'Dashboard', end: true },
          ...(isDemo ? [] : [{ to: `/app/merchant/${activeMerchantId}/upload`, label: 'Upload Data' }]),
          { to: `/app/merchant/${activeMerchantId}/reports`, label: 'Reports' },
        ]
      : []),
    { to: '/app/account', label: 'Account' },
  ]

  async function handleSignOut() {
    setSigningOut(true)
    await signOut()
    navigate('/login', { replace: true })
  }

  const linkClass = ({ isActive }) =>
    [
      'shrink-0 rounded-full px-3.5 py-1.5 text-sm transition',
      isActive ? 'bg-white/8 font-medium text-cream' : 'text-muted hover:bg-white/5 hover:text-cream',
    ].join(' ')

  return (
    <div className="min-h-screen bg-ink text-cream">
      <header className="sticky top-0 z-30 border-b border-white/8 bg-gradient-to-r from-[#111a15] via-ink to-ink/95 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center gap-4 px-4 py-3.5 sm:px-6 lg:px-8">
          <Link to="/app" className="flex shrink-0 items-center gap-2.5 rounded-lg">
            <span
              aria-hidden="true"
              className="inline-block h-3 w-3 rotate-45 rounded-[3px] bg-gradient-to-br from-gold to-sage"
            />
            <span className="text-[0.95rem] font-semibold tracking-tight text-gold">
              merchant<span className="text-cream">AI</span>
            </span>
          </Link>

          <nav aria-label="Workspace" className="ml-auto hidden items-center gap-1 md:flex">
            {links.map((link) => (
              <NavLink key={link.to} to={link.to} end={link.end} className={linkClass}>
                {link.label}
              </NavLink>
            ))}
          </nav>

          <div className="ml-auto flex items-center gap-3 md:ml-4">
            {merchants.length > 1 && activeMerchantId && (
              <>
                <label htmlFor="merchant-switcher" className="sr-only">
                  Switch business
                </label>
                <select
                  id="merchant-switcher"
                  value={activeMerchantId}
                  onChange={(event) => navigate(`/app/merchant/${event.target.value}`)}
                  className="hidden max-w-[12rem] rounded-lg border border-white/12 bg-white/5 px-2.5 py-1.5 text-xs text-cream sm:block"
                >
                  {merchants.map((merchant) => (
                    <option key={merchant.id} value={merchant.id}>
                      {merchant.name}
                    </option>
                  ))}
                </select>
              </>
            )}

            <span
              aria-hidden="true"
              className="grid h-8 w-8 place-items-center rounded-full border border-white/10 bg-raised text-xs font-semibold text-sage"
              title={user?.email ?? ''}
            >
              {initials(user?.email, user?.user_metadata?.full_name)}
            </span>

            <button
              type="button"
              onClick={handleSignOut}
              disabled={signingOut}
              className="rounded-full border border-white/12 px-3 py-1.5 text-xs font-medium text-muted transition hover:border-alert/40 hover:text-alert disabled:opacity-50"
            >
              {signingOut ? 'Signing out…' : 'Sign out'}
            </button>
          </div>
        </div>

        <nav
          aria-label="Workspace"
          className="flex items-center gap-1 overflow-x-auto border-t border-white/5 px-4 pb-2 pt-1.5 md:hidden"
        >
          {links.map((link) => (
            <NavLink
              key={link.to}
              to={link.to}
              end={link.end}
              className={({ isActive }) =>
                [
                  'shrink-0 rounded-full px-3 py-1 text-xs transition',
                  isActive ? 'bg-white/8 font-medium text-cream' : 'text-muted',
                ].join(' ')
              }
            >
              {link.label}
            </NavLink>
          ))}
        </nav>
      </header>

      {isDemo && (
        <div className="border-b border-gold/20 bg-gold/8">
          <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2.5 sm:px-6 lg:px-8">
            <span className="inline-flex items-center gap-1.5 rounded-full bg-gold/15 px-2.5 py-0.5 text-xs font-semibold text-gold">
              <span aria-hidden="true">●</span> Demo mode
            </span>
            <p className="text-xs text-muted">
              Synthetic example data, shared and read-only. Nothing here is a real business.
            </p>
            <button
              type="button"
              onClick={startOwnAccount}
              disabled={leavingDemo}
              className="ml-auto text-xs font-medium text-sage hover:underline disabled:opacity-60"
            >
              {leavingDemo ? 'Leaving the demo…' : 'Create your own account →'}
            </button>
          </div>
        </div>
      )}

      {workspace.persistentStorage === false && !isDemo && (
        <div className="border-b border-alert/25 bg-alert/8">
          <p className="mx-auto max-w-7xl px-4 py-2.5 text-xs text-alert sm:px-6 lg:px-8">
            This server keeps accounts in temporary storage, so your data may be lost when it
            restarts. Connect Supabase for permanent storage.
          </p>
        </div>
      )}

      <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">{children}</main>

      <footer className="mx-auto max-w-7xl px-4 pb-10 sm:px-6 lg:px-8">
        <p className="border-t border-white/8 pt-5 text-xs text-faint">
          {isDemo
            ? 'This demo workspace contains generated synthetic data only. MerchantAI does not use, and does not claim access to, private Paytm data or APIs.'
            : 'Your uploaded data is private to your account. MerchantAI does not use, and does not claim access to, private Paytm data or APIs.'}
        </p>
      </footer>
    </div>
  )
}
