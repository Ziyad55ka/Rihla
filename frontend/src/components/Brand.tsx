import { useLanguage } from '../lib/language'

export function Brand() {
  const { t } = useLanguage()
  return <a href="/" className="auth-brand" aria-label={t('Rihla home')} lang="en" dir="ltr">
    <span className="auth-brand-icon" aria-hidden="true"><svg width="29" height="29" viewBox="0 0 32 32" fill="none"><path d="m5 27 7-18 15-4-5 15-17 7Z" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" /><path d="m13 19 14-14M13 19l-1-10m1 10 9 1" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" /></svg></span>
    <span>rihla<span className="auth-brand-dot">.</span></span>
  </a>
}
