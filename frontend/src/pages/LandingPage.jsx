/**
 * Public entry point.
 *
 * Two doors: the synthetic demo, which needs no account, and the private
 * workspace, which does. The demo is labelled as synthetic everywhere it is
 * offered so nobody mistakes M001's numbers for a real business.
 */
import { Link } from 'react-router-dom'

import { useAuth } from '../auth/AuthProvider'
import { Button, DemoBadge } from '../components/ui'

const CAPABILITIES = [
  {
    title: 'See what happened',
    body: 'Revenue, orders, gross profit, average order value, customer visits and the weekly rhythm of your business.',
  },
  {
    title: 'Understand what changed',
    body: 'Every finding states the size of the move and the documented threshold that made it worth reporting.',
  },
  {
    title: 'Know what to do next',
    body: 'A short ranked plan — High, Medium and Low — with the finding that justifies each action attached to it.',
  },
  {
    title: 'Look a week ahead',
    body: 'A short-term projection that publishes its own measured error instead of an interval it cannot support.',
  },
  {
    title: 'Ask in plain language',
    body: 'An assistant that answers from your computed numbers and is prevented from inventing any of them.',
  },
  {
    title: 'Take the report with you',
    body: 'Download a business analysis PDF built from exactly the figures on your dashboard.',
  },
]

export default function LandingPage() {
  const { session, configured } = useAuth()

  return (
    <div className="min-h-screen bg-ink text-cream">
      <header className="border-b border-white/8 bg-gradient-to-r from-[#111a15] via-ink to-ink/95">
        <div className="mx-auto flex max-w-6xl items-center gap-3 px-4 py-4 sm:px-6">
          <Link to="/" className="flex items-center gap-2.5 rounded-lg">
            <span
              aria-hidden="true"
              className="inline-block h-3 w-3 rotate-45 rounded-[3px] bg-gradient-to-br from-gold to-sage"
            />
            <span className="text-[0.95rem] font-semibold tracking-tight text-gold">
              merchant<span className="text-cream">AI</span>
            </span>
          </Link>

          <nav aria-label="Main" className="ml-auto flex items-center gap-2">
            <Link
              to="/demo"
              className="rounded-full px-3.5 py-1.5 text-sm text-muted transition hover:bg-white/5 hover:text-cream"
            >
              Demo
            </Link>
            {configured &&
              (session ? (
                <Button as="link" to="/app" className="px-4 py-2 text-xs">
                  Open my workspace
                </Button>
              ) : (
                <>
                  <Link
                    to="/login"
                    className="rounded-full px-3.5 py-1.5 text-sm text-muted transition hover:bg-white/5 hover:text-cream"
                  >
                    Sign in
                  </Link>
                  <Button as="link" to="/signup" className="px-4 py-2 text-xs">
                    Get started
                  </Button>
                </>
              ))}
          </nav>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-4 py-14 sm:px-6 sm:py-20">
        <section className="pulse-rise max-w-3xl">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-gold">
            Merchant Growth AI
          </p>
          <h1 className="mt-4 text-3xl font-semibold leading-tight tracking-tight text-cream sm:text-5xl">
            Your business data, turned into the next three things to do.
          </h1>
          <p className="mt-5 max-w-2xl text-base leading-relaxed text-muted">
            MerchantAI reads your own sales and customer data and answers the three questions a
            merchant actually has: what is happening, why it changed, and what to do today. Every
            number is computed from your data — never estimated, never invented.
          </p>

          <div className="mt-8 flex flex-wrap items-center gap-3">
            {configured ? (
              <Button as="link" to={session ? '/app' : '/signup'}>
                {session ? 'Open my workspace' : 'Create your workspace'}
              </Button>
            ) : null}
            <Button as="link" to="/demo" variant="ghost">
              Explore the demo
            </Button>
            <DemoBadge />
          </div>

          {!configured && (
            <p className="mt-5 max-w-xl text-xs leading-relaxed text-faint">
              Accounts are not configured on this deployment, so the private workspace is
              unavailable here. The demo below is fully working.
            </p>
          )}
        </section>

        <section className="mt-16 grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {CAPABILITIES.map((item, index) => (
            <div
              key={item.title}
              className="pulse-lift pulse-rise rounded-2xl border border-white/8 bg-gradient-to-b from-raised to-surface p-5 shadow-[0_12px_30px_rgb(0_0_0/0.25)]"
              style={{ animationDelay: `${index * 60}ms` }}
            >
              <h2 className="text-sm font-semibold text-cream">{item.title}</h2>
              <p className="mt-2 text-sm leading-relaxed text-muted">{item.body}</p>
            </div>
          ))}
        </section>

        <section className="mt-16 rounded-2xl border border-gold/25 bg-gradient-to-b from-[#1a1611] to-cocoa p-6 sm:p-8">
          <h2 className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.16em] text-gold">
            <span aria-hidden="true" className="pulse-sparkle text-sm leading-none">
              ✦
            </span>
            How the AI is kept honest
          </h2>
          <p className="mt-4 max-w-3xl text-sm leading-relaxed text-muted">
            The analysis is a deterministic, auditable engine — not a trained model. Thresholds are
            documented and stated on screen. The optional language model may phrase an answer, but
            any figure in its reply that cannot be traced back to your computed data causes the
            reply to be discarded in favour of the verified one.
          </p>
        </section>

        <footer className="mt-16 border-t border-white/8 pt-6 text-xs leading-relaxed text-faint">
          The demo workspace uses generated synthetic data for four example merchants. MerchantAI
          does not use, and does not claim access to, private Paytm data or APIs.
        </footer>
      </main>
    </div>
  )
}
