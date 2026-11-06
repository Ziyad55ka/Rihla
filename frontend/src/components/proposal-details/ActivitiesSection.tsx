import type { Proposal } from '../../types/proposal'
import { ActivitiesPanel } from '../ActivitiesPanel'
import { useState } from 'react'
import { useLanguage } from '../../lib/language'
import { longRequest } from '../../lib/proposalsHttp'
import { RouteTitleIcon } from './icons'
import { SectionTitle } from './SectionTitle'

/**
 * Developer 2 (US-11/12): the page's activities section, after travel between cities.
 * ActivitiesPanel on the Ziyad branch can be called from here, reading
 * CityStay.activities. Show nothing until there is data. See docs/developer-2-handoff.md.
 */
export function ActivitiesSection({ proposal, onChanged = () => undefined }: { proposal: Proposal; onChanged?: () => void }) {
  const { t } = useLanguage()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const hasActivities = proposal.cities.some(city => city.activities?.length)
  async function find() {
    setBusy(true); setError('')
    try {
      await longRequest(`/api/trips/${encodeURIComponent(proposal.trip_id)}/proposals/${encodeURIComponent(proposal.id)}/activities/suggestions`, { body: { version: proposal.version }, timeoutMs: 180000 })
      onChanged()
    } catch (err) { setError(err instanceof Error ? err.message : 'Activity search is unavailable. Try again later.') }
    finally { setBusy(false) }
  }
  const notes = proposal.cities.flatMap(city => city.activities?.flatMap(activity => activity.research_notes ?? []) ?? [])
  if (hasActivities) return <>
    {notes.includes('guide_search_unavailable') && <p className="trip-feedback" role="status">{t('Showing checked event listings only. Attraction and restaurant research is temporarily unavailable.')}</p>}
    {notes.includes('event_source_unavailable') && <p className="trip-feedback" role="status">{t('The event source could not be reached. These suggestions may not include dated events.')}</p>}
    <ActivitiesPanel key={`${proposal.id}:${proposal.version}`} proposal={proposal} showEstimate={false} onSaved={onChanged} />
  </>
  return <section aria-labelledby="details-activities">
    <SectionTitle icon={<RouteTitleIcon />} id="details-activities" title={t('Activities and places')} />
    <div className="details-card">
      {proposal.activity_research_status === 'ready' ? <p>{t('No checkable suggestions were found for these cities and dates.')}</p> : <>
        <h4 className="details-activity-question">{t('Want us to suggest activities for your trip?')}</h4>
        <p>{t('We will suggest sights, activities and places to eat in your cities, then build a plan for each day from what you choose. Days with nothing chosen stay as free time.')}</p>
      </>}
      {proposal.activity_research_status !== 'ready' && <button className="trip-primary" type="button" disabled={busy} onClick={() => void find()}>{t(busy ? 'Finding real activity suggestions…' : 'Yes, suggest activities')}</button>}
      {error && <p className="trip-feedback trip-feedback--error" role="alert">{t(error)}</p>}
    </div>
  </section>
}
