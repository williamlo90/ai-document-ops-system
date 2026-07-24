import { describe, expect, it } from 'vitest'
import { formatDate, formatMoney, humanize } from './format'

describe('shared formatters', () => {
  it('keeps empty and invalid values safe for operational tables', () => {
    expect(formatDate(null)).toBe('-')
    expect(formatDate('not-a-date')).toBe('not-a-date')
    expect(formatMoney(null, 'USD')).toBe('-')
    expect(formatMoney('not-a-number', 'USD')).toBe('-')
  })

  it('humanizes backend status identifiers consistently across features', () => {
    expect(humanize('needs_correction')).toBe('Needs Correction')
  })
})
