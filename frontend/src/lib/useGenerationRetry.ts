import { useEffect, useState } from 'react'
import type { GenerationIssue } from '../types/proposal'

/** One deadline for every generation button, without a per-second rerender. */
export function useGenerationRetry(issue: GenerationIssue | null) {
  const retryAt = Math.max(0, ...(issue?.suggestions ?? []).map(item => Date.parse(item.params.retry_at ?? '') || 0))
  const [now, setNow] = useState(Date.now)
  useEffect(() => {
    if (!retryAt || now >= retryAt) return
    const timer = window.setTimeout(() => setNow(Date.now()), Math.min(2147483647, Math.max(1, retryAt - Date.now() + 25)))
    return () => window.clearTimeout(timer)
  }, [retryAt, now])
  return { retryAt, retryPending: now < retryAt }
}
