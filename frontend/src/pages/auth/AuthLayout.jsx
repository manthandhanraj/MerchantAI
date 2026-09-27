/** Shared frame for the four authentication screens. */
import { Link } from 'react-router-dom'

export function AuthLayout({ title, description, children, footer }) {
  return (
    <div className="min-h-screen bg-ink text-cream">
      <header className="border-b border-white/8 bg-gradient-to-r from-[#111a15] via-ink to-ink/95">
        <div className="mx-auto flex max-w-5xl items-center gap-2.5 px-4 py-4 sm:px-6">
          <Link to="/" className="flex items-center gap-2.5 rounded-lg">
            <span
              aria-hidden="true"
              className="inline-block h-3 w-3 rotate-45 rounded-[3px] bg-gradient-to-br from-gold to-sage"
            />
            <span className="text-[0.95rem] font-semibold tracking-tight text-gold">
              merchant<span className="text-cream">AI</span>
            </span>
          </Link>
          <Link
            to="/login"
            state={{ startDemo: true }}
            className="ml-auto rounded-full border border-white/12 px-3 py-1.5 text-xs text-muted transition hover:border-sage/40 hover:text-sage"
          >
            Try demo account
          </Link>
        </div>
      </header>

      <main className="mx-auto flex max-w-md flex-col px-4 py-12 sm:px-6 sm:py-16">
        <h1 className="text-2xl font-semibold tracking-tight text-cream sm:text-[1.75rem]">
          {title}
        </h1>
        {description && <p className="mt-2.5 text-sm leading-relaxed text-muted">{description}</p>}

        <div className="pulse-rise mt-7 rounded-2xl border border-white/8 bg-gradient-to-b from-raised to-surface p-6 shadow-[0_18px_40px_rgb(0_0_0/0.35)]">
          {children}
        </div>

        {footer && <div className="mt-5 text-center text-sm text-muted">{footer}</div>}
      </main>
    </div>
  )
}
