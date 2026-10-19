import { PreferencesPanel } from '../components/PreferencesPanel'
import { useLanguage } from '../lib/language'
import '../preferences.css'

export function PreferencesPage({ tripId, onBack, onSaved }: { tripId: string; onBack: () => void; onSaved?: () => void }) {
  const { t } = useLanguage()
  return <section className="preferences-page">
    <button type="button" className="trip-back" onClick={onBack}>← {t('Back to your trip')}</button>
    <header className="preferences-page-heading"><div><p className="trip-eyebrow">{t('A GOOD TRIP STARTS WITH YOU')}</p><h1>{t('Your kind')}<br />{t('of adventure.')}</h1><p className="trip-intro-copy">{t('Big plans work better when everyone has a say. Share your essentials and the little things that make a trip yours.')}</p></div><div className="preferences-page-marker" aria-hidden="true"><span>01 — {t('YOUR PREFERENCES')}</span><svg viewBox="0 0 100 100" fill="none"><path d="m50 6 10 34 34 10-34 10-10 34-10-34L6 50l34-10Z"/><circle cx="50" cy="50" r="14"/></svg><span>{t('MAKE ROOM FOR YOU.')}</span></div></header>
    <PreferencesPanel key={tripId} tripId={tripId} onSaved={() => onSaved?.()} />
  </section>
}
