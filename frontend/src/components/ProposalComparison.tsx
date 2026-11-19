import { useEffect, useRef } from 'react'
import { useLanguage } from '../lib/language'
import { proposalTitle } from '../lib/proposals'
import type { Proposal, StoredProposals } from '../types/proposal'
import { ActivitiesSection } from './proposal-details/ActivitiesSection'
import { CityStaysSection } from './proposal-details/CityStaysSection'
import { CostsSection } from './proposal-details/CostsSection'
import { CompatibilitySection } from './proposal-details/CompatibilitySection'
import { FlightsSection } from './proposal-details/FlightsSection'
import { ProposalHeader } from './proposal-details/ProposalHeader'
import { ProposalFeedback } from './proposal-details/ProposalFeedback'
import { SmartSummary } from './proposal-details/SmartSummary'
import { TransfersSection } from './proposal-details/TransfersSection'
import { DetailScope } from './proposal-details/detailScope'
import { FlightPriceReview } from './FlightPriceReview'
import '../comparison.css'

export function ProposalComparison({ proposals, stored, isAdmin, onChanged, onBack }: {
  proposals: Proposal[]; stored: StoredProposals; isAdmin: boolean; onChanged: () => void; onBack: () => void
}) {
  const { t, language } = useLanguage()
  const dialog = useRef<HTMLDialogElement>(null)
  useEffect(() => { if (!dialog.current?.open) dialog.current?.showModal() }, [])
  const limits = { freshHours: stored.price_fresh_hours ?? 3, staleHours: stored.price_stale_hours ?? 24, fallback: stored.generated_at }
  return <dialog ref={dialog} className="comparison-screen" aria-label={t('Compare proposals')} onClose={onBack}>
    <div className="comparison-toolbar"><h2>{t('Compare proposals')}</h2><button type="button" className="trip-secondary" onClick={() => dialog.current?.close()}>{t('Change selection')}</button></div>
    <div className="comparison-scroll"><div className="comparison-panes" style={{ gridTemplateColumns: `repeat(${proposals.length}, minmax(0, 1fr))`, minWidth: `${proposals.length * 20}rem` }}>
      {proposals.map(proposal => <DetailScope.Provider key={proposal.id} value={proposal.id}><article className="proposal-details comparison-pane" aria-label={proposalTitle(proposal, language)}>
        <ProposalHeader proposal={proposal} total={stored.proposals.length} stale={stored.needs_regeneration} />
        <SmartSummary proposal={proposal} stale={stored.needs_regeneration} />
        <div><FlightPriceReview routes={proposal.flights} minutes={stored.price_review_minutes ?? 15} /></div>
        <FlightsSection proposal={proposal} isAdmin={isAdmin} limits={limits} cooldownMinutes={stored.refresh_cooldown_minutes ?? 2} onChanged={onChanged} />
        <CityStaysSection proposal={proposal} limits={limits} />
        <div>{proposal.intercity_transport.length ? <TransfersSection proposal={proposal} /> : <p className="details-hint">{t('Single-city trip')}</p>}</div>
        <div><ActivitiesSection proposal={proposal} onChanged={onChanged} /></div>
        <CostsSection costs={stored.costs?.find(item => item.proposal_id === proposal.id)} />
        <div>{stored.needs_regeneration ? <p className="proposals-review">{t('Regenerate to recheck budget and preferences')}</p> : <CompatibilitySection proposal={proposal} />}
          <ProposalFeedback proposal={proposal} isAdmin={isAdmin} stale={stored.needs_regeneration || stored.generating} onChanged={onChanged} />
        </div>
      </article></DetailScope.Provider>)}
    </div></div>
  </dialog>
}
