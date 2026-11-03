import type { CityStay } from '../../types/proposal'
import { useLanguage } from '../../lib/language'

/** Developer 2 (US-11/12): show this stay's activities here. Empty until then. */
export function CityActivities({ stay }: { stay: CityStay }) {
  const { t } = useLanguage()
  if (!stay.activities?.length) return null
  return <a className="details-text-link" href="#activities-options">{t('Explore this city’s suggestions')} ({stay.activities.length})</a>
}
