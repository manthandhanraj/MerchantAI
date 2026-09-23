/**
 * Merchant picker.
 *
 * Options come entirely from GET /api/merchants — no merchant ids are hardcoded
 * here, so the API stays the source of truth.
 */
export function MerchantSelector({ merchants, value, onChange, disabled }) {
  return (
    <div className="flex flex-col gap-1">
      <label
        htmlFor="merchant-select"
        className="text-xs font-medium uppercase tracking-wide text-faint"
      >
        Merchant
      </label>
      <select
        id="merchant-select"
        value={value ?? ''}
        disabled={disabled || merchants.length === 0}
        onChange={(event) => onChange(event.target.value)}
        className="w-full min-w-[13rem] rounded-lg border border-white/12 bg-white/5 px-3 py-2 text-sm font-medium text-cream shadow-sm transition focus:border-sage/70 disabled:cursor-not-allowed disabled:bg-white/4 disabled:text-faint"
      >
        {merchants.length === 0 && <option value="">No merchants available</option>}
        {merchants.map((merchant) => (
          <option key={merchant.merchant_id} value={merchant.merchant_id}>
            {merchant.merchant_id} · {merchant.products} products
          </option>
        ))}
      </select>
    </div>
  )
}
