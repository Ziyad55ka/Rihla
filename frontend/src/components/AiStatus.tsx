import { useEffect, useState } from 'react'
import { CHECK_STEP_MS, nextStatusIndex } from '../lib/aiStatus'
import { useLanguage } from '../lib/language'

/** A glowing dot and changing words while the system works. */
export function AiStatus({ messages, stepMs = CHECK_STEP_MS }: { messages: readonly string[]; stepMs?: number }) {
  const { t } = useLanguage()
  const [index, setIndex] = useState(0)
  useEffect(() => {
    const timer = window.setInterval(() => setIndex((value) => nextStatusIndex(value, messages.length)), stepMs)
    return () => window.clearInterval(timer)
  }, [messages.length, stepMs])
  return <span className="ai-status" role="status">
    <span className="ai-status-dot" aria-hidden="true" />
    <span className="ai-status-text" key={index}>{t(messages[index])}</span>
  </span>
}
