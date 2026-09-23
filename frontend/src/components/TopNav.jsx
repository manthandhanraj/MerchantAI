/**
 * Application header.
 *
 * The navigation links move to real sections of this page rather than to routes
 * that do not exist — the app is a single dashboard, and a link that goes
 * nowhere is worse than no link.
 */
const LINKS = [
  { id: 'business-pulse', label: 'Business pulse' },
  { id: 'growth-lab', label: 'Growth lab' },
  { id: 'customers', label: 'Customers' },
]

export function TopNav({ activeSection = 'business-pulse', live = false, merchantId }) {
  return (
    <header className="sticky top-0 z-30 border-b border-white/8 bg-gradient-to-r from-[#111a15] via-ink to-ink/95 backdrop-blur">
      <div className="mx-auto flex max-w-7xl items-center gap-4 px-4 py-3.5 sm:px-6 lg:px-8">
        <a
          href="#business-pulse"
          className="flex shrink-0 items-center gap-2.5 rounded-lg"
        >
          <span
            aria-hidden="true"
            className="inline-block h-3 w-3 rotate-45 rounded-[3px] bg-gradient-to-br from-gold to-sage"
          />
          <span className="text-[0.95rem] font-semibold tracking-tight text-gold">
            merchant<span className="text-cream">AI</span>
          </span>
        </a>

        <nav aria-label="Sections" className="ml-auto hidden items-center gap-1 md:flex">
          {LINKS.map((link) => {
            const isActive = activeSection === link.id
            return (
              <a
                key={link.id}
                href={`#${link.id}`}
                aria-current={isActive ? 'page' : undefined}
                className={[
                  'rounded-full px-3.5 py-1.5 text-sm transition',
                  isActive
                    ? 'bg-white/8 font-medium text-cream'
                    : 'text-muted hover:bg-white/5 hover:text-cream',
                ].join(' ')}
              >
                {link.label}
              </a>
            )
          })}
        </nav>

        <div className="ml-auto flex items-center gap-3 md:ml-4">
          <span
            className="hidden items-center gap-1.5 rounded-full border border-white/8 px-2.5 py-1 text-xs text-muted sm:inline-flex"
            title={live ? 'Connected to the API' : 'Waiting for data'}
          >
            <span
              aria-hidden="true"
              className={`inline-block h-1.5 w-1.5 rounded-full ${
                live ? 'bg-sage' : 'bg-faint'
              }`}
            />
            {live ? 'Live' : 'Connecting'}
          </span>

          {/* The dataset carries merchant ids, not trading names, so the avatar
              shows the id rather than inventing initials for a business. */}
          <span
            aria-hidden="true"
            className="grid h-8 w-8 place-items-center rounded-full border border-white/10 bg-raised text-[0.65rem] font-semibold tracking-tight text-sage"
          >
            {merchantId || '—'}
          </span>
          <span className="sr-only">
            {merchantId ? `Viewing merchant ${merchantId}` : 'No merchant selected'}
          </span>
        </div>
      </div>

      {/* Compact navigation: the same links, below the bar, on small screens. */}
      <nav
        aria-label="Sections"
        className="flex items-center gap-1 overflow-x-auto border-t border-white/5 px-4 pb-2 pt-1.5 md:hidden"
      >
        {LINKS.map((link) => {
          const isActive = activeSection === link.id
          return (
            <a
              key={link.id}
              href={`#${link.id}`}
              aria-current={isActive ? 'page' : undefined}
              className={[
                'shrink-0 rounded-full px-3 py-1 text-xs transition',
                isActive ? 'bg-white/8 font-medium text-cream' : 'text-muted',
              ].join(' ')}
            >
              {link.label}
            </a>
          )
        })}
      </nav>
    </header>
  )
}
