import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { AuthLayout } from './AuthLayout'
import { useAuth } from '../../auth/AuthProvider'
import { Alert, Button, Field, TextInput } from '../../components/ui'

const MIN_PASSWORD = 8

/** Shown live so the rule is visible before it is broken, not after. */
function requirements(password) {
  return [
    { label: `At least ${MIN_PASSWORD} characters`, met: password.length >= MIN_PASSWORD },
    { label: 'One letter', met: /[a-zA-Z]/.test(password) },
    { label: 'One number', met: /\d/.test(password) },
  ]
}

function EyeIcon({ open }) {
  return (
    <svg viewBox="0 0 24 24" width="17" height="17" fill="none" aria-hidden="true">
      <path
        d="M2 12s3.6-6.5 10-6.5S22 12 22 12s-3.6 6.5-10 6.5S2 12 2 12Z"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="12" cy="12" r="2.6" stroke="currentColor" strokeWidth="1.7" />
      {!open && (
        <line x1="4" y1="20" x2="20" y2="4" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
      )}
    </svg>
  )
}

export default function SignupPage() {
  const { signUp } = useAuth()
  const navigate = useNavigate()

  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [accepted, setAccepted] = useState(false)
  const [error, setError] = useState(null)
  const [needsConfirmation, setNeedsConfirmation] = useState(false)
  const [busy, setBusy] = useState(false)

  const rules = requirements(password)
  const strongEnough = rules.every((rule) => rule.met)
  const mismatch = confirm.length > 0 && confirm !== password
  const tooShort = password.length > 0 && !strongEnough

  async function submit(event) {
    event.preventDefault()
    setError(null)
    if (mismatch || !strongEnough || !accepted) return

    setBusy(true)
    try {
      const result = await signUp({ email, password, fullName })
      // With email confirmation enabled, Supabase returns a user but no
      // session — the account is not usable until the link is opened.
      if (result?.session) {
        navigate('/app/onboarding', { replace: true })
      } else {
        setNeedsConfirmation(true)
        setBusy(false)
      }
    } catch (caught) {
      setError(caught.message)
      setBusy(false)
    }
  }

  if (needsConfirmation) {
    return (
      <AuthLayout
        title="Check your inbox"
        description="One more step before your workspace is ready."
        footer={
          <Link to="/login" className="font-medium text-sage hover:underline">
            Back to sign in
          </Link>
        }
      >
        <Alert tone="success" title="Confirmation email sent">
          We sent a link to <span className="font-medium">{email}</span>. Open it to activate your
          account, then sign in.
        </Alert>
      </AuthLayout>
    )
  }

  return (
    <AuthLayout
      title="Create your workspace"
      description="Upload your own sales data and get the same analysis the demo runs on synthetic merchants."
      footer={
        <>
          Already have an account?{' '}
          <Link to="/login" className="font-medium text-sage hover:underline">
            Sign in
          </Link>
        </>
      }
    >
      <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
        {error && (
          <Alert tone="error" title="Could not create your account">
            {error}
          </Alert>
        )}

        <Field label="Your name" id="signup-name" hint="Optional. Used to address you in the app.">
          <TextInput
            id="signup-name"
            autoComplete="name"
            value={fullName}
            onChange={(event) => setFullName(event.target.value)}
            placeholder="Riya Sharma"
          />
        </Field>

        <Field label="Email" id="signup-email">
          <TextInput
            id="signup-email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="you@business.com"
          />
        </Field>

        <Field label="Password" id="signup-password">
          <div className="relative">
            <TextInput
              id="signup-password"
              type={showPassword ? 'text' : 'password'}
              autoComplete="new-password"
              required
              minLength={MIN_PASSWORD}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className="pr-11"
            />
            <button
              type="button"
              onClick={() => setShowPassword((current) => !current)}
              aria-pressed={showPassword}
              aria-label={showPassword ? 'Hide password' : 'Show password'}
              className="absolute inset-y-0 right-0 grid w-11 place-items-center rounded-r-lg text-faint transition hover:text-cream"
            >
              <EyeIcon open={showPassword} />
            </button>
          </div>
          <ul className="mt-2 space-y-1">
            {rules.map((rule) => (
              <li
                key={rule.label}
                className={`flex items-center gap-1.5 text-xs ${
                  rule.met ? 'text-sage' : 'text-faint'
                }`}
              >
                <span aria-hidden="true">{rule.met ? '✓' : '○'}</span>
                {rule.label}
              </li>
            ))}
          </ul>
        </Field>

        <Field
          label="Confirm password"
          id="signup-confirm"
          error={mismatch ? 'The two passwords do not match.' : null}
        >
          <TextInput
            id="signup-confirm"
            type={showPassword ? 'text' : 'password'}
            autoComplete="new-password"
            required
            value={confirm}
            onChange={(event) => setConfirm(event.target.value)}
          />
        </Field>

        <label className="flex cursor-pointer items-start gap-2.5 text-xs leading-relaxed text-muted">
          <input
            type="checkbox"
            checked={accepted}
            onChange={(event) => setAccepted(event.target.checked)}
            className="mt-0.5 h-3.5 w-3.5 shrink-0 rounded border-white/20 bg-white/5 accent-[#b8e49d]"
          />
          <span>
            I understand that data I upload stays private to my account, is never made public,
            and is never shared with other users.
          </span>
        </label>

        <Button
          type="submit"
          as="button"
          disabled={busy || !email || !strongEnough || mismatch || !accepted}
          className="w-full"
        >
          {busy ? 'Creating your account…' : 'Create account'}
        </Button>
      </form>

      <div className="mt-6 border-t border-white/8 pt-5 text-center">
        <p className="text-sm text-muted">Just want to look around first?</p>
        <Button
          as="link"
          to="/login"
          state={{ startDemo: true }}
          variant="gold"
          className="mt-3 w-full"
        >
          Try demo account
        </Button>
        <p className="mt-2 text-xs text-faint">Synthetic data, read-only, no sign-up needed.</p>
      </div>
    </AuthLayout>
  )
}
