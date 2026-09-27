/**
 * Private workspace overview: the businesses this account owns.
 *
 * A user with no merchant yet is sent to onboarding — there is nothing useful
 * to show them here, and bouncing them forward is kinder than an empty list.
 */
import { useCallback, useEffect, useState } from 'react'
import { Link, Navigate } from 'react-router-dom'

import { useStartOwnAccount } from '../../auth/useStartOwnAccount'
import { useWorkspace } from '../../auth/WorkspaceProvider'
import { AppShell } from '../../components/AppShell'
import { Alert, Button, Card, FullPageState, PageHeader, Spinner } from '../../components/ui'
import { getMe, listMerchants } from '../../services/privateApi'
import { formatDate } from '../../utils/format'

export default function WorkspacePage() {
  const { isDemo } = useWorkspace()
  const { start: startOwnAccount, leaving: leavingDemo } = useStartOwnAccount()
  const [state, setState] = useState({ loading: true, error: null, merchants: [], profile: null })

  const load = useCallback(async (signal) => {
    setState((current) => ({ ...current, loading: true, error: null }))
    try {
      const [me, list] = await Promise.all([getMe({ signal }), listMerchants({ signal })])
      if (signal?.aborted) return
      setState({ loading: false, error: null, merchants: list.merchants ?? [], profile: me.profile })
    } catch (error) {
      if (signal?.aborted) return
      setState({ loading: false, error: error.message, merchants: [], profile: null })
    }
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    load(controller.signal)
    return () => controller.abort()
  }, [load])

  if (state.loading) {
    return (
      <FullPageState>
        <Spinner label="Opening your workspace…" />
      </FullPageState>
    )
  }

  if (state.error) {
    return (
      <AppShell>
        <Alert
          tone="error"
          title="Could not load your workspace"
          action={
            <Button variant="ghost" onClick={() => load()}>
              Try again
            </Button>
          }
        >
          {state.error}
        </Alert>
      </AppShell>
    )
  }

  if (state.merchants.length === 0) {
    return <Navigate to="/app/onboarding" replace />
  }

  const greetingName = state.profile?.full_name?.split(' ')[0]

  return (
    <AppShell merchants={state.merchants}>
      <PageHeader
        eyebrow="Your workspace"
        title={greetingName ? `Welcome back, ${greetingName}.` : 'Welcome back.'}
        description="Everything here is private to your account. Pick a business to see its dashboard, upload new data or generate a report."
      >
        {isDemo ? (
          // The demo is read-only; its way forward is an account of one's own.
          <Button variant="gold" onClick={startOwnAccount} disabled={leavingDemo}>
            {leavingDemo ? 'Leaving the demo…' : 'Create your own account'}
          </Button>
        ) : (
          <Button as="link" to="/app/onboarding" variant="ghost">
            Add a business
          </Button>
        )}
      </PageHeader>

      <div className="mt-8 grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
        {state.merchants.map((merchant, index) => (
          <Link
            key={merchant.id}
            to={`/app/merchant/${merchant.id}`}
            className="pulse-lift pulse-rise block rounded-2xl border border-white/8 bg-gradient-to-b from-raised to-surface p-5 shadow-[0_12px_30px_rgb(0_0_0/0.25)] sm:p-6"
            style={{ animationDelay: `${index * 60}ms` }}
          >
            <p className="text-xs font-medium uppercase tracking-[0.12em] text-faint">
              {merchant.business_type || 'Business'}
            </p>
            <h2 className="mt-2 truncate text-lg font-semibold text-cream">{merchant.name}</h2>
            {merchant.description && (
              <p className="mt-2 line-clamp-2 text-sm text-muted">{merchant.description}</p>
            )}
            <p className="mt-4 text-xs text-faint">
              {merchant.currency} · added {formatDate(String(merchant.created_at).slice(0, 10), { withYear: true })}
            </p>
          </Link>
        ))}
      </div>

      <Card className="mt-8">
        <h2 className="text-sm font-semibold text-cream">Working with your own data</h2>
        <ol className="mt-3 space-y-2 text-sm text-muted">
          <li>1. Upload a sales file and a customer file for the business.</li>
          <li>2. MerchantAI validates them and tells you about any rows it cannot read.</li>
          <li>3. Run the analysis to get insights, a ranked plan and a short-term forecast.</li>
          <li>4. Download the report, or ask the assistant about the numbers.</li>
        </ol>
      </Card>
    </AppShell>
  )
}
