/**
 * Small shared primitives for the authenticated screens.
 *
 * These exist so the new pages inherit the Business Pulse language — obsidian
 * background, forest surfaces, sage for action, champagne gold for AI — without
 * each one re-deriving it. Focus states come from the global :focus-visible rule
 * in index.css, so nothing here has to remember them.
 */
import { Link } from 'react-router-dom'

const BASE_BUTTON =
  'inline-flex items-center justify-center gap-2 rounded-full px-5 py-2.5 text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-50'

const VARIANTS = {
  primary: 'bg-sage text-[#11251a] hover:bg-[#c8eeb0]',
  gold: 'focus-gold bg-gold text-[#221a0c] hover:bg-[#f0cd8d]',
  ghost: 'border border-white/12 text-muted hover:border-sage/40 hover:text-sage',
  danger: 'border border-alert/35 text-alert hover:bg-alert/10',
  quiet: 'text-muted hover:text-cream',
}

export function Button({ variant = 'primary', className = '', as, to, ...props }) {
  const classes = `${BASE_BUTTON} ${VARIANTS[variant] ?? VARIANTS.primary} ${className}`
  if (as === 'link') {
    return <Link to={to} className={classes} {...props} />
  }
  return <button type="button" className={classes} {...props} />
}

export function Card({ className = '', accent = false, children, ...props }) {
  return (
    <section
      className={[
        'rounded-2xl border p-5 shadow-[0_12px_30px_rgb(0_0_0/0.25)] sm:p-6',
        accent
          ? 'border-gold/25 bg-gradient-to-b from-[#1a1611] to-cocoa'
          : 'border-white/8 bg-gradient-to-b from-raised to-surface',
        className,
      ].join(' ')}
      {...props}
    >
      {children}
    </section>
  )
}

export function Field({ label, hint, error, id, children }) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-xs font-medium uppercase tracking-[0.12em] text-faint">
        {label}
      </label>
      {children}
      {hint && !error && <p className="text-xs text-faint">{hint}</p>}
      {error && (
        <p className="text-xs text-alert" role="alert">
          {error}
        </p>
      )}
    </div>
  )
}

export const inputClass =
  'w-full rounded-lg border border-white/12 bg-white/5 px-3 py-2.5 text-sm text-cream shadow-sm transition placeholder:text-faint focus:border-sage/70 disabled:cursor-not-allowed disabled:bg-white/4 disabled:text-faint'

export function TextInput({ className = '', ...props }) {
  return <input className={`${inputClass} ${className}`} {...props} />
}

export function Select({ className = '', children, ...props }) {
  return (
    <select className={`${inputClass} ${className}`} {...props}>
      {children}
    </select>
  )
}

export function Alert({ tone = 'error', title, children, action }) {
  const tones = {
    error: 'border-alert/25 bg-alert/8 text-alert',
    info: 'border-white/8 bg-white/4 text-muted',
    success: 'border-sage/30 bg-sage/10 text-sage',
    warning: 'border-gold/30 bg-gold/10 text-gold',
  }
  return (
    <div
      role={tone === 'error' ? 'alert' : 'status'}
      className={`rounded-xl border p-4 ${tones[tone] ?? tones.info}`}
    >
      {title && <p className="text-sm font-semibold">{title}</p>}
      {children && <div className="mt-1 text-sm leading-relaxed">{children}</div>}
      {action && <div className="mt-3">{action}</div>}
    </div>
  )
}

export function Spinner({ label = 'Loading' }) {
  return (
    <span className="inline-flex items-center gap-2 text-sm text-muted" role="status">
      <span
        aria-hidden="true"
        className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/15 border-t-sage"
      />
      {label}
    </span>
  )
}

export function PageHeader({ eyebrow, title, description, children }) {
  return (
    <header className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
      <div className="min-w-0 max-w-2xl">
        {eyebrow && (
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-gold">{eyebrow}</p>
        )}
        <h1 className="mt-2.5 text-2xl font-semibold leading-tight tracking-tight text-cream sm:text-3xl">
          {title}
        </h1>
        {description && (
          <p className="mt-2.5 text-sm leading-relaxed text-muted">{description}</p>
        )}
      </div>
      {children && <div className="shrink-0">{children}</div>}
    </header>
  )
}

export function EmptyState({ title, message, action }) {
  return (
    <Card className="text-center">
      <p className="text-sm font-semibold text-cream">{title}</p>
      {message && <p className="mx-auto mt-2 max-w-prose text-sm text-muted">{message}</p>}
      {action && <div className="mt-5 flex justify-center">{action}</div>}
    </Card>
  )
}

/** A full-page centred state, used while a session or a merchant is resolving. */
export function FullPageState({ children }) {
  return (
    <div className="grid min-h-screen place-items-center bg-ink px-4">
      <div className="text-center">{children}</div>
    </div>
  )
}

export function DemoBadge({ className = '' }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border border-gold/30 bg-gold/10 px-2.5 py-1 text-xs font-medium text-gold ${className}`}
      title="This workspace shows generated demonstration data, not a real business."
    >
      <span aria-hidden="true">●</span> Synthetic demo data
    </span>
  )
}
