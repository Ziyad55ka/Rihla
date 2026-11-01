import { useEffect, useRef, useState } from 'react'
import { ActivitiesSection } from '../components/proposal-details/ActivitiesSection'
import { CityStaysSection } from '../components/proposal-details/CityStaysSection'
import { CostsAndCompatibility } from '../components/proposal-details/CostsAndCompatibility'
import { FlightsSection } from '../components/proposal-details/FlightsSection'
import { ProposalHeader } from '../components/proposal-details/ProposalHeader'
import { TransfersSection } from '../components/proposal-details/TransfersSection'
import { useLanguage } from '../lib/language'
import { useSectionReveal } from '../lib/motion'
import { getPreferences } from '../lib/preferences'
import { getProposals } from '../lib/proposals'
import { defaultRoomChoice, type RoomChoice } from '../lib/rooms'
import { getTrip } from '../lib/trips'
import type { StoredProposals } from '../types/proposal'
import '../planning.css'
import '../proposals.css'
import '../proposal-details.css'

export function ProposalDetailView({ stored, proposalId, isAdmin, onBack, onChanged = () => undefined, defaultRooms = 'shared' }: { stored: StoredProposals; proposalId: string; isAdmin: boolean; onBack: () => void; onChanged?: () => void; defaultRooms?: RoomChoice }) {
  const { t } = useLanguage()
  const root = useRef<HTMLElement>(null)
  useSectionReveal(root)
  const proposal = stored.proposals.find((item) => item.id === proposalId)
  const back = <button type="button" className="trip-back" onClick={onBack}>← {t('Back to the trip')}</button>
  if (!proposal) return <section className="proposal-details">{back}
    <div className="trip-state-panel"><h3 role="status">{t('This proposal has been replaced.')}</h3><button type="button" className="trip-secondary" onClick={onBack}>{t('Back to the trip')}</button></div>
  </section>
  const limits = { freshHours: stored.price_fresh_hours ?? 3, staleHours: stored.price_stale_hours ?? 24, fallback: stored.generated_at }
  return <article className="proposal-details" ref={root}>
    {back}
    <ProposalHeader proposal={proposal} total={stored.proposals.length} />
    {stored.needs_regeneration && <p className="proposals-review" role="status">{t(isAdmin ? 'The trip’s details changed after these proposals were generated. Generate them again to include the changes.' : 'The trip’s details changed after these proposals were generated. The administrator needs to generate them again.')}</p>}
    <FlightsSection proposal={proposal} allSameCity={stored.all_same_city === true} isAdmin={isAdmin} limits={limits} cooldownMinutes={stored.refresh_cooldown_minutes ?? 2} onChanged={onChanged} />
    <CityStaysSection proposal={proposal} limits={limits} defaultRooms={defaultRooms} />
    <TransfersSection proposal={proposal} />
    <ActivitiesSection proposal={proposal} />
    <CostsAndCompatibility proposal={proposal} />
  </article>
}

export function ProposalDetailPage({ tripId, proposalId, onBack }: { tripId: string; proposalId: string; onBack: () => void }) {
  const { t } = useLanguage()
  const [loaded, setLoaded] = useState<{ stored: StoredProposals; isAdmin: boolean; defaultRooms: RoomChoice } | null>(null)
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    setError('')
    // Only the member's own preference. Without it, the page assumes shared rooms.
    const preference = getPreferences(tripId, controller.signal).then((saved) => saved.accommodation.value).catch(() => null)
    Promise.all([getProposals(tripId, controller.signal), getTrip(tripId, controller.signal), preference])
      .then(([stored, trip, wanted]) => { if (!controller.signal.aborted) setLoaded({ stored, isAdmin: trip.role === 'administrator', defaultRooms: defaultRoomChoice(wanted) }) })
      .catch((err: unknown) => { if (!controller.signal.aborted) setError(err instanceof Error ? err.message : 'Could not load proposals.') })
    return () => controller.abort()
  }, [tripId, attempt])
  if (error) return <section className="proposal-details">
    <button type="button" className="trip-back" onClick={onBack}>← {t('Back to the trip')}</button>
    <div className="trip-feedback trip-feedback--error" role="alert">{t(error)}<button type="button" className="trip-text-button" onClick={() => setAttempt((value) => value + 1)}>{t('Try again')}</button></div>
  </section>
  if (!loaded) return <p className="trip-loading" role="status">{t('Opening this proposal…')}</p>
  return <ProposalDetailView stored={loaded.stored} proposalId={proposalId} isAdmin={loaded.isAdmin} onBack={onBack} defaultRooms={loaded.defaultRooms} onChanged={() => setAttempt((value) => value + 1)} />
}
