/**
 * Date range picker: quick presets plus explicit start/end inputs.
 *
 * Bounds come from the selected merchant's own first/last date, never from
 * today() — the dataset is a fixed deterministic window, so a "last 30 days"
 * relative to the real clock would select nothing.
 */
export const PRESETS = [
  { id: '7', label: '7D', days: 7 },
  { id: '30', label: '30D', days: 30 },
  { id: '90', label: '90D', days: 90 },
  { id: 'all', label: 'All', days: null },
]

export function DateRangeControls({
  start,
  end,
  minDate,
  maxDate,
  activePreset,
  onPresetChange,
  onStartChange,
  onEndChange,
  disabled,
}) {
  const inputClass =
    'rounded-lg border border-white/12 bg-white/5 px-3 py-2 text-sm text-cream shadow-sm transition focus:border-sage/70 disabled:cursor-not-allowed disabled:bg-white/4 disabled:text-faint'

  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:gap-4">
      <div className="flex flex-col gap-1">
        <span className="text-xs font-medium uppercase tracking-wide text-faint">Period</span>
        <div className="inline-flex rounded-lg border border-white/12 bg-white/5 p-0.5 shadow-sm">
          {PRESETS.map((preset) => {
            const isActive = activePreset === preset.id
            return (
              <button
                key={preset.id}
                type="button"
                disabled={disabled}
                aria-pressed={isActive}
                onClick={() => onPresetChange(preset)}
                className={[
                  'rounded-md px-3 py-1.5 text-sm font-medium transition',
                  isActive
                    ? 'bg-sage text-[#11251a] shadow-sm'
                    : 'text-muted hover:bg-white/10',
                  disabled ? 'cursor-not-allowed opacity-50' : '',
                ].join(' ')}
              >
                {preset.label}
              </button>
            )
          })}
        </div>
      </div>

      <div className="flex flex-col gap-1">
        <label htmlFor="start-date" className="text-xs font-medium uppercase tracking-wide text-faint">
          From
        </label>
        <input
          id="start-date"
          type="date"
          value={start ?? ''}
          min={minDate}
          max={end || maxDate}
          disabled={disabled}
          onChange={(event) => onStartChange(event.target.value)}
          className={inputClass}
        />
      </div>

      <div className="flex flex-col gap-1">
        <label htmlFor="end-date" className="text-xs font-medium uppercase tracking-wide text-faint">
          To
        </label>
        <input
          id="end-date"
          type="date"
          value={end ?? ''}
          min={start || minDate}
          max={maxDate}
          disabled={disabled}
          onChange={(event) => onEndChange(event.target.value)}
          className={inputClass}
        />
      </div>
    </div>
  )
}
