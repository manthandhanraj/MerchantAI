import { Link, useLocation } from 'react-router-dom'

import { useAuth } from '../auth/AuthProvider'
import { Button } from '../components/ui'

export default function NotFoundPage() {
  const { pathname } = useLocation()
  const { session } = useAuth()

  return (
    <div className="grid min-h-screen place-items-center bg-ink px-4 text-cream">
      <div className="max-w-lg text-center">
        <Link to="/" className="inline-flex items-center gap-2.5 rounded-lg">
          <span
            aria-hidden="true"
            className="inline-block h-3 w-3 rotate-45 rounded-[3px] bg-gradient-to-br from-gold to-sage"
          />
          <span className="text-[0.95rem] font-semibold tracking-tight text-gold">
            merchant<span className="text-cream">AI</span>
          </span>
        </Link>

        <p className="mt-10 text-xs font-semibold uppercase tracking-[0.18em] text-gold">
          Page not found
        </p>
        <h1 className="mt-3 text-2xl font-semibold tracking-tight sm:text-3xl">
          There is nothing at that address.
        </h1>
        <p className="mt-3 break-all text-sm text-muted">
          <code className="rounded bg-white/5 px-1.5 py-0.5 text-xs">{pathname}</code>
        </p>
        <p className="mt-4 text-sm leading-relaxed text-muted">
          The link may be out of date, or the business it pointed to may have been deleted.
        </p>

        <div className="mt-8 flex flex-wrap justify-center gap-3">
          <Button as="link" to={session ? '/app' : '/'}>
            {session ? 'Back to my workspace' : 'Back to the home page'}
          </Button>
          <Button as="link" to="/demo" variant="ghost">
            Open the demo
          </Button>
        </div>
      </div>
    </div>
  )
}
