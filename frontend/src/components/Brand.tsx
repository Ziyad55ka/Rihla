import { useId } from 'react'
import { useLanguage } from '../lib/language'

/** The brand mark: a teal-to-slate circle, a plane on a dotted route and a sand sun. */
export function BrandMark({ size = 32 }: { size?: number }) {
  const id = useId()
  return <svg width={size} height={size} viewBox="0 0 64 64" aria-hidden="true">
    <defs>
      <linearGradient id={`${id}-sky`} x1="54" y1="8" x2="10" y2="58" gradientUnits="userSpaceOnUse">
        <stop offset="0" stopColor="#3a978c" />
        <stop offset="1" stopColor="#2f4a5c" />
      </linearGradient>
    </defs>
    <circle cx="32" cy="32" r="31" fill={`url(#${id}-sky)`} />
    <circle cx="47.5" cy="15" r="4" fill="#d29a5f" />
    <g fill="#e8ecec">
      {[[13, 30], [13.6, 35], [15.4, 39.6], [18.4, 43.4], [22.4, 46], [27, 47]].map(([cx, cy]) => <circle key={`${cx}`} cx={cx} cy={cy} r="1.5" />)}
      <path transform="translate(33 33) scale(.82) translate(-33 -31)" d="M45.6 20.2c1.3-1.3 3.2-1.2 3.6-.8.4.4.5 2.3-.8 3.6l-5.6 5.6 2.4 13.6-2.6 2.6-6.4-11-5.4 5.4.8 4.6-2 2-2.6-5.4-5.4-2.6 2-2 4.6.8 5.4-5.4-11-6.4 2.6-2.6 13.6 2.4Z" />
    </g>
  </svg>
}

export function Brand() {
  const { t } = useLanguage()
  return <a href="/" className="auth-brand" aria-label={t('Rihla home')} lang="en" dir="ltr">
    <span className="auth-brand-icon" aria-hidden="true"><BrandMark /></span>
    <span>rihla<span className="auth-brand-dot">.</span></span>
  </a>
}
