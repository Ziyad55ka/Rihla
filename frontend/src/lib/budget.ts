const STEP = 100000n // 1,000 SAR, in halalas. Never use floating-point money.
const MAXIMUM = 999999999999n

/** Explicit +/- controls keep native step validation from rejecting custom budgets. */
export function stepBudget(value: string | null, direction: 1 | -1): string | null {
  if (!value?.trim()) return direction === 1 ? '1000' : null
  if (!/^\d+(\.\d{1,2})?$/.test(value)) return value
  const [whole, fraction = ''] = value.split('.')
  const current = BigInt(whole) * 100n + BigInt(fraction.padEnd(2, '0'))
  const next = current + STEP * BigInt(direction)
  // A limit is never silently rounded, cleared, or changed to a non-positive amount.
  if (next < 1n || next > MAXIMUM) return value
  const remainder = next % 100n
  return `${next / 100n}${remainder ? `.${remainder.toString().padStart(2, '0')}` : ''}`
}
