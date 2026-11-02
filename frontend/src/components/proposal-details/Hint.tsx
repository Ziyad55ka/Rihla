import { useState } from 'react'
import { useLanguage } from '../../lib/language'
import { InfoIcon } from './icons'

/** A longer explanation, kept out of the way until someone asks for it. */
export function Hint({ text }: { text: string }) {
  const { t } = useLanguage()
  const [open, setOpen] = useState(false)
  return <span className="details-tip">
    <button type="button" aria-label={t('More information')} aria-expanded={open} onClick={() => setOpen((value) => !value)} onBlur={() => setOpen(false)}><InfoIcon /></button>
    <span className={`details-tip-text${open ? ' is-open' : ''}`} role="tooltip">{text}</span>
  </span>
}
