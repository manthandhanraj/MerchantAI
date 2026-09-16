import { describe, expect, it } from 'vitest'

import {
  formatCurrency,
  formatCurrencyCompact,
  formatDate,
  formatDateRange,
  formatNumber,
  formatPercent,
  formatSignedPercent,
  maxIsoDate,
  parseIsoDate,
  shiftDays,
} from './format'

describe('currency', () => {
  it('uses Indian digit grouping', () => {
    // 17,51,857 not 1,751,857 — lakh grouping, not thousands.
    expect(formatCurrency(1751857)).toBe('₹17,51,857')
  })

  it('formats zero as a real value, not a dash', () => {
    expect(formatCurrency(0)).toBe('₹0')
  })

  it('returns a dash for missing or non-finite values', () => {
    expect(formatCurrency(null)).toBe('—')
    expect(formatCurrency(undefined)).toBe('—')
    expect(formatCurrency(NaN)).toBe('—')
    expect(formatCurrency(Infinity)).toBe('—')
  })

  it('compacts using Indian scale words for chart axes', () => {
    expect(formatCurrencyCompact(1500)).toBe('₹2K')
    expect(formatCurrencyCompact(250000)).toBe('₹2.5L')
    expect(formatCurrencyCompact(17518564)).toBe('₹1.8Cr')
    expect(formatCurrencyCompact(0)).toBe('₹0')
  })
})

describe('numbers', () => {
  it('groups and rounds', () => {
    expect(formatNumber(12385)).toBe('12,385')
    expect(formatNumber(0)).toBe('0')
  })

  it('returns a dash for non-finite values', () => {
    expect(formatNumber(NaN)).toBe('—')
    expect(formatNumber(null)).toBe('—')
  })
})

describe('percentages', () => {
  it('renders an API fraction as a percentage', () => {
    // The API sends 0.3022, the UI must show 30.2% — not 0.3% and not 3022%.
    expect(formatPercent(0.3022)).toBe('30.2%')
    expect(formatPercent(0)).toBe('0.0%')
    expect(formatPercent(1)).toBe('100.0%')
  })

  it('always signs a change value', () => {
    expect(formatSignedPercent(0.31)).toBe('+31.0%')
    expect(formatSignedPercent(-0.149)).toBe('-14.9%')
    expect(formatSignedPercent(0)).toBe('0.0%')
  })

  it('returns a dash for non-finite values', () => {
    expect(formatPercent(NaN)).toBe('—')
    expect(formatSignedPercent(undefined)).toBe('—')
  })
})

describe('dates', () => {
  it('parses an ISO date in local time', () => {
    // Parsing as UTC would render 19 March in any negative-offset timezone.
    const date = parseIsoDate('2026-03-20')
    expect(date.getFullYear()).toBe(2026)
    expect(date.getMonth()).toBe(2)
    expect(date.getDate()).toBe(20)
  })

  it('rejects malformed input instead of producing Invalid Date', () => {
    expect(parseIsoDate('not-a-date')).toBeNull()
    expect(parseIsoDate('')).toBeNull()
    expect(parseIsoDate(null)).toBeNull()
    expect(formatDate('garbage')).toBe('—')
  })

  it('shifts by days across month boundaries', () => {
    expect(shiftDays('2026-03-01', -1)).toBe('2026-02-28')
    expect(shiftDays('2026-09-15', -29)).toBe('2026-08-17')
    expect(shiftDays('bad', -1)).toBe('')
  })

  it('clamps a preset start to the earliest available date', () => {
    expect(maxIsoDate('2026-03-20', '2026-01-01')).toBe('2026-03-20')
    expect(maxIsoDate('2026-01-01', '2026-03-20')).toBe('2026-03-20')
  })

  it('formats a range and collapses a single day', () => {
    expect(formatDateRange('2026-03-20', '2026-09-15')).toContain('–')
    expect(formatDateRange('2026-03-20', '2026-03-20')).not.toContain('–')
    expect(formatDateRange(null, null)).toBe('—')
  })
})
