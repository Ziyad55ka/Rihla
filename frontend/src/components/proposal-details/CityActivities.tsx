import type { CityStay } from '../../types/proposal'
import { useLanguage } from '../../lib/language'

/** Developer 2 (US-11/12): show this stay's activities here. Empty until then. */
export function CityActivities({ stay }: { stay: CityStay }) {
  const { t } = useLanguage()
  if (!stay.activities?.length) return null
  return <a className="details-text-link" href="#activities-options" onClick={event => {
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return
    event.preventDefault()
    const section = document.getElementById('activities-options')
    section?.focus({ preventScroll: true })
    section?.scrollIntoView({ block: 'start', behavior: 'instant' })
  }}>{t('Explore this city’s suggestions')} ({stay.activities.length})</a>
}
