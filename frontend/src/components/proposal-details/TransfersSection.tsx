import { useLanguage } from '../../lib/language'
import type { Proposal } from '../../types/proposal'
import { InfoValue, PriceValue } from './values'

export function TransfersSection({ proposal }: { proposal: Proposal }) {
  const { t, language } = useLanguage()
  if (proposal.intercity_transport.length === 0) return null
  const arrow = language === 'ar' ? '←' : '→'
  return <section aria-labelledby="details-transfers">
    <h2 id="details-transfers">{t('Travel between cities')}</h2>
    {proposal.intercity_transport.map((transfer) => <div className="details-card details-transfer" key={`${transfer.from_city}-${transfer.to_city}`}>
      <h3><bdi>{transfer.from_city}</bdi> {arrow} <bdi>{transfer.to_city}</bdi></h3>
      <InfoValue field={transfer.mode} sources={proposal.sources} />
      <InfoValue field={transfer.duration} sources={proposal.sources} />
      <PriceValue price={transfer.price_per_person} unit="per person" sources={proposal.sources} />
    </div>)}
  </section>
}
