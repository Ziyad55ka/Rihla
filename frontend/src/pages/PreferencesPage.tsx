import { PreferencesPanel } from '../components/PreferencesPanel'
import { useLanguage } from '../lib/language'
import '../preferences.css'

export function PreferencesPage({ tripId, onBack, onSaved }: { tripId: string; onBack: () => void; onSaved?: () => void }) {
  const { t } = useLanguage()
  return <section className="preferences-page">
    <button type="button" className="trip-back" onClick={onBack}>← {t('Back to your trip')}</button>
    <PreferencesPanel key={tripId} tripId={tripId} onSaved={() => onSaved?.()} />
  </section>
}
