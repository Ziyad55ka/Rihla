// The backend reports no stages, so these follow a timer and stop on the last one.
export const checkMessages = ['Reviewing the trip…', 'Checking the prices…', 'Comparing the sellers…', 'Preparing the booking link…']
export const generateMessages = ['Reading the group’s preferences…', 'Looking for destinations…', 'Checking the flights…', 'Preparing the proposals…']

export const openingMessages = ['Opening this proposal…']

export const CHECK_STEP_MS = 1500
export const GENERATE_STEP_MS = 8000

export function nextStatusIndex(index: number, length: number): number {
  return Math.min(index + 1, length - 1)
}

/** Minutes and seconds since generation began, such as 1:05. */
export function elapsedLabel(seconds: number, locale: string): string {
  const minutes = Math.floor(seconds / 60)
  const rest = Math.floor(seconds % 60)
  const two = (value: number) => value.toLocaleString(locale, { minimumIntegerDigits: 2 })
  return `${minutes.toLocaleString(locale)}:${two(rest)}`
}

