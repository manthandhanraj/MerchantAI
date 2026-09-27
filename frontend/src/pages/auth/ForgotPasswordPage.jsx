import { useState } from 'react'
import { Link } from 'react-router-dom'

import { AuthLayout } from './AuthLayout'
import { useAuth } from '../../auth/AuthProvider'
import { Alert, Button, Field, TextInput } from '../../components/ui'

export default function ForgotPasswordPage() {
  const { requestPasswordReset, canResetByEmail } = useAuth()
  const [email, setEmail] = useState('')
  const [sent, setSent] = useState(false)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  async function submit(event) {
    event.preventDefault()
    setError(null)
    setBusy(true)
    try {
      await requestPasswordReset(email)
      setSent(true)
    } catch (caught) {
      setError(caught.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <AuthLayout
      title="Reset your password"
      description="We will email you a link to choose a new one."
      footer={
        <Link to="/login" className="font-medium text-sage hover:underline">
          Back to sign in
        </Link>
      }
    >
      {!canResetByEmail ? (
        // Built-in accounts have no email service. Saying so beats a form that
        // pretends to send something.
        <Alert tone="info" title="Reset by email is not available here">
          This installation keeps accounts itself rather than through an email provider, so it
          cannot send reset links. Ask the person who runs it to reset your password with{' '}
          <code className="rounded bg-white/5 px-1 py-0.5 text-xs">
            python scripts/reset_password.py
          </code>
          . If you are still signed in somewhere, you can change it from Account.
        </Alert>
      ) : sent ? (
        // Worded the same whether or not the address has an account: saying
        // which it is would disclose who is registered.
        <Alert tone="success" title="Check your inbox">
          If an account exists for <span className="font-medium">{email}</span>, a reset link is on
          its way. The link expires after a short while.
        </Alert>
      ) : (
        <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
          {error && (
            <Alert tone="error" title="Could not send the email">
              {error}
            </Alert>
          )}
          <Field label="Email" id="forgot-email">
            <TextInput
              id="forgot-email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="you@business.com"
            />
          </Field>
          <Button type="submit" as="button" disabled={busy || !email} className="w-full">
            {busy ? 'Sending…' : 'Send reset link'}
          </Button>
        </form>
      )}
    </AuthLayout>
  )
}
