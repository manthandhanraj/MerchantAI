import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { AuthLayout } from './AuthLayout'
import { useAuth } from '../../auth/AuthProvider'
import { Alert, Button, Field, Spinner, TextInput } from '../../components/ui'

const MIN_PASSWORD = 8

export default function ResetPasswordPage() {
  const { updatePassword, session, loading, canResetByEmail } = useAuth()
  const navigate = useNavigate()

  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState(null)
  const [done, setDone] = useState(false)
  const [busy, setBusy] = useState(false)

  // The reset link carries a recovery session in the URL fragment, which the
  // Supabase client exchanges on load. Until that lands there is no session to
  // update, so the form waits rather than reporting a failure that is not one.
  const [settling, setSettling] = useState(true)
  useEffect(() => {
    if (loading) return undefined
    const timer = setTimeout(() => setSettling(false), 400)
    return () => clearTimeout(timer)
  }, [loading])

  const mismatch = confirm.length > 0 && confirm !== password
  const tooShort = password.length > 0 && password.length < MIN_PASSWORD

  async function submit(event) {
    event.preventDefault()
    setError(null)
    if (mismatch || tooShort) return
    setBusy(true)
    try {
      await updatePassword(password)
      setDone(true)
      setTimeout(() => navigate('/app', { replace: true }), 1500)
    } catch (caught) {
      setError(caught.message)
      setBusy(false)
    }
  }

  if (!canResetByEmail) {
    return (
      <AuthLayout
        title="Reset links are not used here"
        footer={
          <Link to="/login" className="font-medium text-sage hover:underline">
            Back to sign in
          </Link>
        }
      >
        <Alert tone="info" title="This installation manages accounts itself">
          Password reset links are only sent when MerchantAI is connected to Supabase. Sign in and
          change your password from Account, or ask the administrator to reset it.
        </Alert>
      </AuthLayout>
    )
  }

  if (loading || settling) {
    return (
      <AuthLayout title="Choose a new password">
        <Spinner label="Opening your reset link…" />
      </AuthLayout>
    )
  }

  if (!session) {
    return (
      <AuthLayout
        title="That link is no longer valid"
        footer={
          <Link to="/forgot-password" className="font-medium text-sage hover:underline">
            Request a new link
          </Link>
        }
      >
        <Alert tone="error" title="Reset link expired or already used">
          Password reset links are single-use and expire quickly. Request a new one and open it in
          the same browser.
        </Alert>
      </AuthLayout>
    )
  }

  return (
    <AuthLayout
      title="Choose a new password"
      description="Pick something you have not used here before."
    >
      {done ? (
        <Alert tone="success" title="Password updated">
          Taking you to your workspace…
        </Alert>
      ) : (
        <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
          {error && (
            <Alert tone="error" title="Could not update your password">
              {error}
            </Alert>
          )}

          <Field
            label="New password"
            id="reset-password"
            hint={`At least ${MIN_PASSWORD} characters.`}
            error={tooShort ? `Use at least ${MIN_PASSWORD} characters.` : null}
          >
            <TextInput
              id="reset-password"
              type="password"
              autoComplete="new-password"
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </Field>

          <Field
            label="Confirm new password"
            id="reset-confirm"
            error={mismatch ? 'The two passwords do not match.' : null}
          >
            <TextInput
              id="reset-confirm"
              type="password"
              autoComplete="new-password"
              required
              value={confirm}
              onChange={(event) => setConfirm(event.target.value)}
            />
          </Field>

          <Button
            type="submit"
            as="button"
            disabled={busy || !password || mismatch || tooShort}
            className="w-full"
          >
            {busy ? 'Updating…' : 'Update password'}
          </Button>
        </form>
      )}
    </AuthLayout>
  )
}
