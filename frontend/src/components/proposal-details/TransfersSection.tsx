import { useLanguage } from '../../lib/language'
import { placeName } from '../../lib/places'
import type { Proposal } from '../../types/proposal'
import { InfoValue, PriceValue } from './values'

export function TransfersSection({ proposal }: { proposal: Proposal }) {
  const { t, language } = useLanguage()
  if (proposal.intercity_transport.length === 0) return null
  const arrow = language === 'ar' ? '←' : '→'
  const name = (city: string) => placeName(city, language, proposal.cities.find((stay) => stay.city === city)?.city_ar)
  return <section aria-labelledby="details-transfers">
    <h2 id="details-transfers">{t('Travel between cities')}</h2>
    {proposal.intercity_transport.map((transfer) => <div className="details-card details-transfer" key={`${transfer.from_city}-${transfer.to_city}`}>
      <h3><bdi>{name(transfer.from_city)}</bdi> {arrow} <bdi>{name(transfer.to_city)}</bdi></h3>
      <InfoValue field={transfer.mode} />
      <InfoValue field={transfer.duration} />
      <PriceValue price={transfer.price_per_person} unit="per person" />
    </div>)}
  </section>
}
