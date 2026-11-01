import { useEffect, useState } from 'react'
import { CityStaysSection } from '../components/proposal-details/CityStaysSection'
import { CostsAndCompatibility } from '../components/proposal-details/CostsAndCompatibility'
import { FlightsSection } from '../components/proposal-details/FlightsSection'
import { ProposalHeader } from '../components/proposal-details/ProposalHeader'
import { SourcesSection } from '../components/proposal-details/SourcesSection'
import { TransfersSection } from '../components/proposal-details/TransfersSection'
import { useLanguage } from '../lib/language'
import { getProposals } from '../lib/proposals'
import { getTrip } from '../lib/trips'
import type { StoredProposals } from '../types/proposal'
import '../planning.css'
import '../proposals.css'
import '../proposal-details.css'

export function ProposalDetailView({ stored, proposalId, isAdmin, onBack, onChanged = () => undefined }: { stored: StoredProposals; proposalId: string; isAdmin: boolean; onBack: () => void; onChanged?: () => void }) {
  const { t } = useLanguage()
  const proposal = stored.proposals.find((item) => item.id === proposalId)
  const back = <button type="button" className="trip-back" onClick={onBack}>← {t('Back to the trip')}</button>
  if (!proposal) return <section className="proposal-details">{back}
    <div className="trip-state-panel"><h3 role="status">{t('This proposal has been replaced.')}</h3><button type="button" className="trip-secondary" onClick={onBack}>{t('Back to the trip')}</button></div>
  </section>
  const limits = { freshHours: stored.price_fresh_hours ?? 3, staleHours: stored.price_stale_hours ?? 24, fallback: stored.generated_at }
  return <article className="proposal-details">
    {back}
    <ProposalHeader proposal={proposal} total={stored.proposals.length} />
    {stored.needs_regeneration && <p className="proposals-review" role="status">{t(isAdmin ? 'The trip’s details changed after these proposals were generated. Generate them again to include the changes.' : 'The trip’s details changed after these proposals were generated. The administrator needs to generate them again.')}</p>}
    <CityStaysSection proposal={proposal} limits={limits} />
    <TransfersSection proposal={proposal} />
    <FlightsSection proposal={proposal} allSameCity={stored.all_same_city === true} isAdmin={isAdmin} limits={limits} cooldownMinutes={stored.refresh_cooldown_minutes ?? 2} onChanged={onChanged} />
    <CostsAndCompatibility proposal={proposal} />
    <SourcesSection sources={proposal.sources} />
  </article>
}

export function ProposalDetailPage({ tripId, proposalId, onBack }: { tripId: string; proposalId: string; onBack: () => void }) {
  const { t } = useLanguage()
  const [loaded, setLoaded] = useState<{ stored: StoredProposals; isAdmin: boolean } | null>(null)
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    setError('')
    Promise.all([getProposals(tripId, controller.signal), getTrip(tripId, controller.signal)])
      .then(([stored, trip]) => { if (!controller.signal.aborted) setLoaded({ stored, isAdmin: trip.role === 'administrator' }) })
      .catch((err: unknown) => { if (!controller.signal.aborted) setError(err instanceof Error ? err.message : 'Could not load proposals.') })
    return () => controller.abort()
  }, [tripId, attempt])
  if (error) return <section className="proposal-details">
    <button type="button" className="trip-back" onClick={onBack}>← {t('Back to the trip')}</button>
    <div className="trip-feedback trip-feedback--error" role="alert">{t(error)}<button type="button" className="trip-text-button" onClick={() => setAttempt((value) => value + 1)}>{t('Try again')}</button></div>
  </section>
  if (!loaded) return <p className="trip-loading" role="status">{t('Opening this proposal…')}</p>
  return <ProposalDetailView stored={loaded.stored} proposalId={proposalId} isAdmin={loaded.isAdmin} onBack={onBack} onChanged={() => setAttempt((value) => value + 1)} />
}
