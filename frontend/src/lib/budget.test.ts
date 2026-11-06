import { describe, expect, it } from 'vitest'
import { stepBudget } from './budget'

describe('budget adjustments', () => {
  it('changes by exactly 1,000 SAR without halala increments', () => {
    expect(stepBudget('9000', 1)).toBe('10000')
    expect(stepBudget('9000', -1)).toBe('8000')
    expect(stepBudget('4500', 1)).toBe('5500')
  })
  it('preserves existing cents without floating point rounding', () => {
    expect(stepBudget('9000.02', 1)).toBe('10000.02')
    expect(stepBudget('4500.50', -1)).toBe('3500.50')
  })
  it('never crosses the saved-budget constraints or replaces invalid draft input', () => {
    expect(stepBudget('1000', -1)).toBe('1000')
    expect(stepBudget('9999999999.99', 1)).toBe('9999999999.99')
    expect(stepBudget('9000abc', 1)).toBe('9000abc')
    expect(stepBudget(null, 1)).toBe('1000')
    expect(stepBudget(null, -1)).toBeNull()
  })
})
