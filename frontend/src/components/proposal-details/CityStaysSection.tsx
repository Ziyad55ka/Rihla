import { useState } from 'react'
import { useLanguage } from '../../lib/language'
import { useCountUp } from '../../lib/motion'
import { calendarDate } from '../../lib/planning'
import { placeName } from '../../lib/places'
import { type PriceAgeLimits, safeLink, stayDates, staySource } from '../../lib/proposals'
import { adultsInLink, linkWithRooms, type RoomChoice, roomsFor, sharePerPerson } from '../../lib/rooms'
import type { CityStay, Proposal } from '../../types/proposal'
import { CityActivities } from './CityActivities'
import { Hint } from './Hint'
import { ExternalIcon, StaysTitleIcon } from './icons'
import { nightsLabel } from './nights'
import { PlacePhoto } from './PlacePhoto'
import { SectionTitle } from './SectionTitle'
import { useSar } from './useSar'
import { PriceAgeBadge, PriceValue, StatusBadge } from './values'

function RoomPicker({ choice, onChange }: { choice: RoomChoice; onChange: (choice: RoomChoice) => void }) {
  const { t } = useLanguage()
  const options: { value: RoomChoice; label: string }[] = [{ value: 'shared', label: 'Shared rooms (two to a room)' }, { value: 'own', label: 'A room for each person' }]
  return <fieldset className="details-rooms">
    <legend>{t('How will you share rooms?')}<Hint text={t('This only changes what you see. It is not saved, and nobody else sees it.')} /></legend>
    <div className="details-segment">{options.map((option) => <label key={option.value} className={choice === option.value ? 'is-chosen' : undefined}>
      <input type="radio" name="details-rooms" value={option.value} checked={choice === option.value} onChange={() => onChange(option.value)} />
      <span>{t(option.label)}</span>
    </label>)}</div>
  </fieldset>
}

/** One person's share, gliding when the room choice changes. */
function PersonShare({ perRoom, rooms, adults, nights }: { perRoom: number; rooms: number; adults: number; nights: number }) {
  const { t } = useLanguage()
  const sar = useSar()
  const { value: perNight, ref } = useCountUp<HTMLDivElement>(sharePerPerson(perRoom, rooms, adults))
  const shown = Math.round(perNight)
  return <div className="details-share" ref={ref}>
    <strong>{t('About {amount} per person a night', { amount: sar(shown) })}</strong>
    {nights > 0 && <span className="details-hint">{t('About {amount} per person for the whole stay', { amount: sar(shown * nights) })}</span>}
  </div>
}

function Hotel({ stay, city, proposal, limits, choice }: { stay: CityStay; city: string; proposal: Proposal; limits: PriceAgeLimits; choice: RoomChoice }) {
  const { t, language } = useLanguage()
  const sar = useSar()
  const name = stay.hotel_name.value
  const price = stay.hotel_price_per_night
  const perNight = price.amount_sar
  const direct = safeLink(stay.hotel_url ?? null)
  const adults = adultsInLink(stay.booking_url)
  const rooms = adults ? roomsFor(choice, adults) : null
  const search = safeLink(stay.booking_url && rooms ? linkWithRooms(stay.booking_url, rooms) : stay.booking_url)
  const labels = (language === 'ar' ? stay.labels_ar : stay.labels_en) ?? []
  const roomsHint = t('Check for enough rooms for the group.')
  if (!name && !perNight) return <div className="details-hotel details-hotel--empty">
    {stay.area && <p className="details-hint">{t('Suggested area:')} <bdi>{stay.area}</bdi></p>}
    {search
      ? <a className="trip-primary" href={search} target="_blank" rel="noopener noreferrer">{t('Search for hotels in {city}', { city })} <ExternalIcon /></a>
      : <p className="details-hint">{t('No booking link')}</p>}
    <p className="details-hint details-inline">{t('We did not find a confirmed hotel in {city}', { city })}<Hint text={roomsHint} /></p>
  </div>
  const source = staySource(stay, proposal.sources)
  return <div className="details-hotel">
    {name ? <h4 className="details-hotel-name"><bdi>{name}</bdi>{stay.hotel_name.status === 'Unconfirmed' && <StatusBadge status="Unconfirmed" />}</h4> : <p className="details-no-hotel">{t('The hotel is not confirmed yet')}</p>}
    {stay.area && <p className="details-hint">{t('Suggested area:')} <bdi>{stay.area}</bdi></p>}
    {labels.length > 0 && <ul className="details-labels">{labels.map((label) => <li key={label}><bdi>{label}</bdi></li>)}</ul>}
    {perNight && rooms && adults
      ? <>
        <PersonShare perRoom={Number(perNight)} rooms={rooms} adults={adults} nights={stay.nights} />
        <div className="details-value"><StatusBadge status={price.status} /><PriceAgeBadge pricedAt={stay.priced_at} limits={limits} />{source && <Hint text={`${t('Source:')} ${source} · ${t('Room price: {amount}', { amount: sar(perNight) })}`} />}</div>
      </>
      : perNight
        ? <>
          <div className="details-value details-share"><PriceValue price={price} unit="per night" /><PriceAgeBadge pricedAt={stay.priced_at} limits={limits} />{source && <Hint text={`${t('Source:')} ${source}`} />}</div>
          {stay.nights > 0 && <p className="details-hint">{t('About {amount} for the whole stay', { amount: sar(Number(perNight) * stay.nights) })}</p>}
        </>
        : <p className="details-hint">{t('The price appears on the booking page')}</p>}
    <div className="details-hotel-actions">
      {direct
        ? <>
          <a className="trip-primary" href={direct} target="_blank" rel="noopener noreferrer">{t('Book this hotel')} <ExternalIcon /></a>
          {search && <a className="details-text-link" href={search} target="_blank" rel="noopener noreferrer">{t('Compare on Booking')} <ExternalIcon /></a>}
        </>
        : search
          ? <a className="trip-primary" href={search} target="_blank" rel="noopener noreferrer">{name ? t('Search on Booking.com') : t('Search for hotels in {city}', { city })} <ExternalIcon /></a>
          : <p className="details-hint">{t('No booking link')}</p>}
      <Hint text={roomsHint} />
    </div>
  </div>
}

export function CityStaysSection({ proposal, limits, defaultRooms = 'shared' }: { proposal: Proposal; limits: PriceAgeLimits; defaultRooms?: RoomChoice }) {
  const { t, locale, language } = useLanguage()
  const [choice, setChoice] = useState<RoomChoice>(defaultRooms)
  const dates = stayDates(proposal)
  const canChoose = proposal.cities.some((stay) => (adultsInLink(stay.booking_url) ?? 0) > 1)
  return <section aria-labelledby="details-cities">
    <SectionTitle id="details-cities" icon={<StaysTitleIcon />} title={t('Hotels and stays')} />
    {canChoose && <RoomPicker choice={choice} onChange={setChoice} />}
    <ol className="details-cities">
      {proposal.cities.map((stay, index) => {
        const city = placeName(stay.city, language, stay.city_ar)
        return <li className="details-card details-city" key={stay.order}>
          <PlacePhoto image={stay.image} place={city} />
          <h3><span className="details-order">{stay.order.toLocaleString(locale)}</span> <bdi>{city}</bdi></h3>
          <p className="details-hint">{nightsLabel(stay.nights, language, t, locale)} · {calendarDate(dates[index].start, locale)} – {calendarDate(dates[index].end, locale)}</p>
          <Hotel stay={stay} city={city} proposal={proposal} limits={limits} choice={choice} />
          <CityActivities stay={stay} />
        </li>
      })}
    </ol>
  </section>
}
