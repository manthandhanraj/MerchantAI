import { describe, expect, it } from 'vitest'

import { WEEKDAY_LABELS, weekdayRhythm } from './rhythm'

// 2026-06-01 is a Monday, so these dates run Mon → Sun in order.
const WEEK = [
  { date: '2026-06-01', revenue: 100 },
  { date: '2026-06-02', revenue: 200 },
  { date: '2026-06-03', revenue: 300 },
  { date: '2026-06-04', revenue: 400 },
  { date: '2026-06-05', revenue: 500 },
  { date: '2026-06-06', revenue: 900 },
  { date: '2026-06-07', revenue: 600 },
]

describe('weekdayRhythm', () => {
  it('returns Monday first, Sunday last', () => {
    expect(weekdayRhythm(WEEK).map((entry) => entry.label)).toEqual(WEEKDAY_LABELS)
  })

  it('places each date under the weekday it actually falls on', () => {
    const rhythm = weekdayRhythm(WEEK)
    expect(rhythm.find((entry) => entry.label === 'Mon').value).toBe(100)
    expect(rhythm.find((entry) => entry.label === 'Sat').value).toBe(900)
    expect(rhythm.find((entry) => entry.label === 'Sun').value).toBe(600)
  })

  it('averages repeated weekdays rather than summing them', () => {
    const rhythm = weekdayRhythm([
      { date: '2026-06-01', revenue: 100 },
      { date: '2026-06-08', revenue: 300 },
    ])
    const monday = rhythm.find((entry) => entry.label === 'Mon')

    expect(monday.value).toBe(200)
    expect(monday.days).toBe(2)
  })

  it('marks the strongest weekday, whichever one it is', () => {
    const peak = weekdayRhythm(WEEK).filter((entry) => entry.isPeak)

    expect(peak).toHaveLength(1)
    expect(peak[0].label).toBe('Sat')
  })

  it('scales every day against the peak so bars need no rescaling', () => {
    const rhythm = weekdayRhythm(WEEK)

    expect(rhythm.find((entry) => entry.label === 'Sat').share).toBe(1)
    expect(rhythm.find((entry) => entry.label === 'Mon').share).toBeCloseTo(100 / 900, 6)
  })

  it('reports weekdays with no data rather than inventing a value for them', () => {
    const rhythm = weekdayRhythm([{ date: '2026-06-01', revenue: 100 }])
    const tuesday = rhythm.find((entry) => entry.label === 'Tue')

    expect(tuesday.days).toBe(0)
    expect(tuesday.value).toBe(0)
    expect(tuesday.isPeak).toBe(false)
  })

  it('can group a field other than revenue', () => {
    const rhythm = weekdayRhythm(
      [{ date: '2026-06-06', revenue: 900, orders: 42 }],
      'orders',
    )
    expect(rhythm.find((entry) => entry.label === 'Sat').value).toBe(42)
  })

  it('skips malformed rows instead of throwing', () => {
    const rhythm = weekdayRhythm([
      { date: 'not-a-date', revenue: 100 },
      { date: '2026-06-01', revenue: null },
      { date: '2026-06-01', revenue: 250 },
      null,
    ])
    const monday = rhythm.find((entry) => entry.label === 'Mon')

    expect(monday.value).toBe(250)
    expect(monday.days).toBe(1)
  })

  it('survives an empty or missing series', () => {
    for (const input of [[], null, undefined]) {
      const rhythm = weekdayRhythm(input)
      expect(rhythm).toHaveLength(7)
      expect(rhythm.every((entry) => entry.days === 0 && entry.share === 0)).toBe(true)
    }
  })
})
