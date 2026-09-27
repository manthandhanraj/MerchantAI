/**
 * The product's front door.
 *
 * Two columns on desktop — what MerchantAI does on the left, the form on the
 * right — and a single stacked column on mobile with the form first, because a
 * returning user is here to sign in, not to read.
 *
 * Both ways in are always on this page: sign in (or create an account), or try
 * the demo account. The demo credentials shown are real. They authenticate
 * through the same sign-in as any other account and open a seeded, synthetic,
 * read-only workspace. There is no UI-only shortcut.
 */
import { useEffect, useRef, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'

import { useAuth } from '../../auth/AuthProvider'
import { Alert, Button, Field, TextInput } from '../../components/ui'
import { useDemoCredentials } from '../../lib/demo'
import { isRemembered, setRemembered } from '../../lib/supabase'

const BENEFITS = [
  {
    title: 'See what actually happened',
    body: 'Revenue, orders, profit, customers and the weekly rhythm of your business, from your own data.',
  },
  {
    title: 'Understand what changed',
    body: 'Every finding carries the size of the move and the threshold that made it worth reporting.',
  },
  {
    title: 'Know what to do next',
    body: 'A short ranked plan, with the finding that justifies each action attached to it.',
  },
]

/** A small, honest sales chart: a rising bar series, drawn once and still. */
function BrandVisual() {
  const bars = [38, 52, 44, 66, 58, 82, 74, 96]
  return (
    <svg
      viewBox="0 0 320 120"
      className="mt-10 h-28 w-full max-w-sm"
      role="img"
      aria-label="An illustration of a rising monthly sales chart"
    >
      <defs>
        <linearGradient id="login-bar" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#b8e49d" stopOpacity="0.95" />
          <stop offset="100%" stopColor="#b8e49d" stopOpacity="0.25" />
        </linearGradient>
      </defs>
      {bars.map((height, index) => (
        <rect
          key={index}
          x={index * 40 + 6}
          y={110 - height}
          width={26}
          height={height}
          rx={5}
          fill={index === bars.length - 1 ? '#e5bd75' : 'url(#login-bar)'}
        />
      ))}
      <line x1="0" y1="112" x2="320" y2="112" stroke="#ffffff" strokeOpacity="0.12" />
    </svg>
  )
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

export default function LoginPage() {
  const { signIn } = useAuth()
  const demo = useDemoCredentials()
  const navigate = useNavigate()
  const location = useLocation()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [remember, setRemember] = useState(isRemembered)
  const [error, setError] = useState(null)
  const [demoError, setDemoError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [demoBusy, setDemoBusy] = useState(false)
  const demoRequested = useRef(false)

  async function attempt(credentials) {
    setRemembered(remember)
    await signIn(credentials)
    const from = location.state?.from
    navigate(from && from.startsWith('/app') ? from : '/app', { replace: true })
  }

  async function submit(event) {
    event.preventDefault()
    setError(null)
    setDemoError(null)
    setBusy(true)
    try {
      await attempt({ email, password })
    } catch (caught) {
      setError(caught.message)
      setBusy(false)
    }
  }

  async function signInAsDemo() {
    setError(null)
    setDemoError(null)
    setDemoBusy(true)
    try {
      // Fetched now if the page could not load them when it opened.
      const account = demo.available ? demo : await demo.load()
      // Fill the fields too, so it is visible that this is an ordinary sign-in
      // with the credentials printed above, not a hidden back door.
      setEmail(account.email)
      setPassword(account.password)
      await attempt({ email: account.email, password: account.password })
    } catch (caught) {
      setDemoError(caught.message)
      setDemoBusy(false)
    }
  }

  // "Try demo account" on the other auth pages lands here and starts the demo,
  // once, on arrival.
  useEffect(() => {
    if (!location.state?.startDemo || demoRequested.current) return
    demoRequested.current = true
    signInAsDemo()
  }, [])

  const working = busy || demoBusy

  return (
    <div className="min-h-screen bg-ink text-cream">
      <div className="mx-auto grid min-h-screen max-w-6xl grid-cols-1 gap-12 px-4 py-10 sm:px-6 lg:grid-cols-[1.05fr_1fr] lg:items-center lg:gap-16 lg:py-16">
        {/* ---- form first on mobile, right-hand column on desktop ---- */}
        <div className="order-1 lg:order-2">
          <div className="pulse-rise mx-auto w-full max-w-md rounded-2xl border border-white/8 bg-gradient-to-b from-raised to-surface p-6 shadow-[0_20px_50px_rgb(0_0_0/0.4)] sm:p-7">
            <div className="lg:hidden">
              <Link to="/login" className="inline-flex items-center gap-2.5">
                <span
                  aria-hidden="true"
                  className="inline-block h-3 w-3 rotate-45 rounded-[3px] bg-gradient-to-br from-gold to-sage"
                />
                <span className="text-[0.95rem] font-semibold tracking-tight text-gold">
                  merchant<span className="text-cream">AI</span>
                </span>
              </Link>
            </div>

            <h1 className="mt-5 text-xl font-semibold tracking-tight text-cream sm:text-2xl lg:mt-0">
              Sign in
            </h1>
            <p className="mt-1.5 text-sm text-muted">
              Open your private workspace to see your own business data.
            </p>

            <form onSubmit={submit} className="mt-6 flex flex-col gap-4" noValidate>
              {error && (
                <Alert tone="error" title="Could not sign you in">
                  {error}
                </Alert>
              )}

              <Field label="Email or account ID" id="login-email">
                <TextInput
                  id="login-email"
                  type="email"
                  autoComplete="email"
                  autoFocus
                  required
                  disabled={working}
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  placeholder="you@business.com"
                />
              </Field>

              <Field label="Password" id="login-password">
                <div className="relative">
                  <TextInput
                    id="login-password"
                    type={showPassword ? 'text' : 'password'}
                    autoComplete="current-password"
                    required
                    disabled={working}
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
              </Field>

              <div className="flex flex-wrap items-center justify-between gap-3">
                <label className="inline-flex cursor-pointer items-center gap-2 text-xs text-muted">
                  <input
                    type="checkbox"
                    checked={remember}
                    onChange={(event) => setRemember(event.target.checked)}
                    className="h-3.5 w-3.5 rounded border-white/20 bg-white/5 accent-[#b8e49d]"
                  />
                  Remember me
                </label>
                <Link to="/forgot-password" className="text-xs text-muted hover:text-sage">
                  Forgot your password?
                </Link>
              </div>

              <Button
                type="submit"
                as="button"
                disabled={working || !email || !password}
                className="w-full"
              >
                {busy ? 'Signing in…' : 'Sign in'}
              </Button>
            </form>

            <div className="mt-6 border-t border-white/8 pt-5 text-center">
              <p className="text-sm text-muted">New to MerchantAI?</p>
              <Button as="link" to="/signup" variant="ghost" className="mt-3 w-full">
                Create new account
              </Button>
            </div>

            {/* ---- demo account ---- */}
            {demo.offered && (
              <div className="mt-6 rounded-xl border border-gold/25 bg-gold/8 p-4">
                <p className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.14em] text-gold">
                  <span aria-hidden="true" className="pulse-sparkle text-sm leading-none">
                    ✦
                  </span>
                  Just exploring? Try the demo account
                </p>
                <p className="mt-2 text-xs leading-relaxed text-muted">
                  No sign-up needed. A working example with synthetic data. Read-only, so
                  everyone sees the same thing.
                </p>

                {demo.available ? (
                  <dl className="mt-3 space-y-1 text-xs">
                    <div className="flex gap-2">
                      <dt className="w-16 shrink-0 text-faint">Email</dt>
                      <dd className="break-all font-medium text-cream">{demo.email}</dd>
                    </div>
                    <div className="flex gap-2">
                      <dt className="w-16 shrink-0 text-faint">Password</dt>
                      <dd className="break-all font-medium text-cream">{demo.password}</dd>
                    </div>
                  </dl>
                ) : (
                  !demo.error && (
                    <p className="mt-3 text-xs text-faint">Loading the demo sign-in details…</p>
                  )
                )}

                {(demoError || demo.error) && !demoBusy && (
                  <div className="mt-3">
                    <Alert tone="error" title="The demo could not be opened">
                      {demoError || demo.error}
                    </Alert>
                  </div>
                )}

                <Button
                  variant="gold"
                  onClick={signInAsDemo}
                  disabled={working}
                  className="mt-4 w-full"
                >
                  {demoBusy ? 'Opening the demo…' : 'Try demo account'}
                </Button>
              </div>
            )}
          </div>
        </div>

        {/* ---- value proposition ---- */}
        <div className="order-2 lg:order-1">
          <Link to="/login" className="hidden items-center gap-2.5 lg:inline-flex">
            <span
              aria-hidden="true"
              className="inline-block h-3.5 w-3.5 rotate-45 rounded-[3px] bg-gradient-to-br from-gold to-sage"
            />
            <span className="text-base font-semibold tracking-tight text-gold">
              merchant<span className="text-cream">AI</span>
            </span>
          </Link>

          <h2 className="mt-8 text-2xl font-semibold leading-tight tracking-tight text-cream sm:text-3xl lg:mt-10 lg:text-[2.1rem]">
            Your business data, turned into the next three things to do.
          </h2>
          <p className="mt-4 max-w-lg text-sm leading-relaxed text-muted">
            Upload your sales data and get a dashboard, explainable insights, a short-term
            forecast and a ranked action plan — every figure computed from your own numbers.
          </p>

          <ul className="mt-8 space-y-5">
            {BENEFITS.map((benefit) => (
              <li key={benefit.title} className="flex gap-3">
                <span
                  aria-hidden="true"
                  className="mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full border border-sage/35 bg-sage/12 text-[0.6rem] font-semibold text-sage"
                >
                  ✓
                </span>
                <div>
                  <p className="text-sm font-medium text-cream">{benefit.title}</p>
                  <p className="mt-0.5 max-w-md text-sm leading-relaxed text-muted">
                    {benefit.body}
                  </p>
                </div>
              </li>
            ))}
          </ul>

          <BrandVisual />

          <p className="mt-8 max-w-lg text-xs leading-relaxed text-faint">
            Data you upload stays private to your account.{' '}
            <Link to="/about" className="underline hover:text-muted">
              About MerchantAI
            </Link>
            {' · '}
            <Link to="/demo" className="underline hover:text-muted">
              Public synthetic demo
            </Link>
          </p>
        </div>
      </div>
    </div>
  )
}
