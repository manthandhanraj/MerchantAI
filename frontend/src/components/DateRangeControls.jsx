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
    'rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 shadow-sm transition focus:border-teal-600 focus:outline-none focus-visible:ring-2 focus-visible:ring-teal-600/30 disabled:cursor-not-allowed disabled:bg-slate-100 disabled:text-slate-400'

  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:gap-4">
      <div className="flex flex-col gap-1">
        <span className="text-xs font-medium uppercase tracking-wide text-slate-500">Period</span>
        <div className="inline-flex rounded-lg border border-slate-300 bg-white p-0.5 shadow-sm">
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
                  'rounded-md px-3 py-1.5 text-sm font-medium transition focus:outline-none focus-visible:ring-2 focus-visible:ring-teal-600',
                  isActive
                    ? 'bg-teal-700 text-white shadow-sm'
                    : 'text-slate-600 hover:bg-slate-100',
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
        <label htmlFor="start-date" className="text-xs font-medium uppercase tracking-wide text-slate-500">
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
        <label htmlFor="end-date" className="text-xs font-medium uppercase tracking-wide text-slate-500">
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
