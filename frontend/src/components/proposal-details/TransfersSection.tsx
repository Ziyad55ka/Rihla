import { useState } from 'react'
import { durationLabel, modeKind, type ModeKind, transferSearchUrl } from '../../lib/proposals'
import { useLanguage } from '../../lib/language'
import { calendarDate } from '../../lib/planning'
import { placeName, stationName } from '../../lib/places'
import { stayDates } from '../../lib/proposals'
import type { IntercityTransfer, Proposal } from '../../types/proposal'
import { BusIcon, CarIcon, FerryIcon, PlaneIcon, RouteIcon, TrainIcon } from './icons'
import { nightsLabel } from './nights'
import { PriceValue } from './values'

const modeIcons: Record<ModeKind, () => React.JSX.Element> = { train: TrainIcon, bus: BusIcon, flight: PlaneIcon, car: CarIcon, ferry: FerryIcon, other: RouteIcon }
const modeLabels: Record<Exclude<ModeKind, 'other'>, string> = { train: 'Train', bus: 'Bus', flight: 'Flight', car: 'Car', ferry: 'Ferry' }

function Link({ transfer, from, to }: { transfer: IntercityTransfer; from: string; to: string }) {
  const { t, language, locale } = useLanguage()
  const kind = modeKind(transfer.mode.value)
  const Icon = modeIcons[kind]
  const mode = kind === 'other' ? transfer.mode.value : t(modeLabels[kind])
  const duration = durationLabel(transfer.duration.value, language, locale)
  return <li className="details-metro-link">
    <span className="details-metro-icon"><Icon /></span>
    <div className="details-metro-facts">
      {mode && <strong><bdi>{mode}</bdi></strong>}
      {duration && <span><bdi>{duration}</bdi></span>}
      <PriceValue price={transfer.price_per_person} unit="per person" />
      <a className="details-text-link" href={transferSearchUrl(transfer.mode.value, transfer.from_city, transfer.to_city)} target="_blank" rel="noopener noreferrer">{t('Search for this trip: {from} to {to}', { from, to })} <span aria-hidden="true">↗</span></a>
    </div>
  </li>
}

/** The route as a line of stops. Stations show only when the data has them. */
export function TransfersSection({ proposal }: { proposal: Proposal }) {
  const { t, language, locale } = useLanguage()
  const [open, setOpen] = useState<number | null>(null)
  if (proposal.intercity_transport.length === 0) return null
  const dates = stayDates(proposal)
  const name = (index: number) => placeName(proposal.cities[index].city, language, proposal.cities[index].city_ar)
  const station = (index: number) => {
    const arriving = proposal.intercity_transport[index - 1]?.to_station
    const leaving = proposal.intercity_transport[index]?.from_station
    return arriving ?? leaving ?? null
  }
  return <section aria-labelledby="details-transfers">
    <h2 id="details-transfers">{t('Travel between cities')}</h2>
    <ol className="details-metro details-card">
      {proposal.cities.flatMap((stay, index) => {
        const here = station(index)
        const stop = <li className="details-metro-stop" key={`stop-${stay.order}`}>
          <button type="button" className={open === index ? 'is-open' : undefined} aria-expanded={open === index} onClick={() => setOpen(open === index ? null : index)} onMouseEnter={() => setOpen(index)}>
            <span className="details-metro-dot" aria-hidden="true" />
            <bdi>{name(index)}</bdi>
          </button>
          {here && <span className="details-hint"><bdi>{stationName(here, language)}</bdi></span>}
          {open === index && <p className="details-hint details-reveal">{nightsLabel(stay.nights, language, t, locale)} · {calendarDate(dates[index].start, locale)} – {calendarDate(dates[index].end, locale)}</p>}
        </li>
        const transfer = proposal.intercity_transport[index]
        return transfer ? [stop, <Link key={`link-${stay.order}`} transfer={transfer} from={name(index)} to={name(index + 1)} />] : [stop]
      })}
    </ol>
  </section>
}
