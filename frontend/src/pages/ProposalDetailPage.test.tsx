import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ReactNode } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { BookResultView, BookSteps, RefreshView } from '../components/proposal-details/FlightActions'
import { PlacePhoto } from '../components/proposal-details/PlacePhoto'
import { airlineName } from '../lib/airlines'
import { checkAndReload, type FlightCheckResult, linkMinutesLeft, priceChange, staySource } from '../lib/proposals'
import { placeName } from '../lib/places'
import { LanguageProvider } from '../lib/language'
import { readRoute } from '../lib/navigation'
import { ProposalDetailView } from './ProposalDetailPage'
import type { FlightLeg, Flights, InfoField, Proposal, SarPrice, StoredProposals } from '../types/proposal'

vi.mock('../lib/supabase', () => ({ supabase: null, supabaseConfiguration: { state: 'not-configured', message: '' } }))

const evidence = [{ source_id: 1, quote: 'A fictional quote.' }]
const info = (value: string): InfoField => ({ value, status: 'Sourced', evidence })
const price = (amount: string, status: SarPrice['status'] = 'Estimated'): SarPrice => ({ amount_sar: amount, status, evidence })
const none: SarPrice = { amount_sar: null, status: 'Not available', evidence: [] }
const leg = (direction: FlightLeg['direction'], booking_url: string | null, legPrice = none): FlightLeg => ({
  direction, date: direction === 'outbound' ? '2026-12-13' : '2026-12-17', airline: info('Mock Air'), duration: info('3h'), price: legPrice, booking_url,
})
const flights = (extra: Partial<Flights>): Flights => ({
  origin: 'Riyadh', trip_type: 'round_trip', legs: [leg('outbound', 'https://air.example/a'), leg('return', 'https://air.example/a')],
  airline: info('Mock Air'), duration: info('3h'), price_per_person: price('900', 'Sourced'), ...extra,
})
const stay = { order: 1, city: 'Cairo', nights: 4, hotel_name: info('Mock Hotel'), hotel_price_per_night: price('450'), booking_url: 'https://www.booking.com/searchresults.html?ss=Cairo' }
const proposal = (extra: Partial<Proposal> = {}): Proposal => ({
  id: 'p1', trip_id: 't1', version: 1, option_number: 1, title: 'Main title', destination: 'Egypt', start_date: '2026-12-13', end_date: '2026-12-17',
  cities: [stay], flights: [flights({})], intercity_transport: [], flexible_adjustments: [], budget_status: 'within_group_budget',
  sources: [{ id: 1, title: 'Mock source', url: 'https://source.example/page' }], ...extra,
})
const stored = (item: Proposal, extra: Partial<StoredProposals> = {}): StoredProposals => ({
  version: 1, complete: true, generated_at: null, generating: false, needs_regeneration: false, proposals: [item], ...extra,
})
function page(item: Proposal = proposal(), isAdmin = true, proposalId = 'p1', extra: Partial<StoredProposals> = {}) {
  return renderToStaticMarkup(<LanguageProvider><ProposalDetailView stored={stored(item, extra)} proposalId={proposalId} isAdmin={isAdmin} onBack={() => undefined} /></LanguageProvider>)
}
const count = (html: string, text: string) => html.split(text).length - 1

const saved = new Map<string, string>()
beforeEach(() => {
  saved.clear()
  vi.stubGlobal('localStorage', { getItem: (key: string) => saved.get(key) ?? null, setItem: (key: string, value: string) => saved.set(key, value) })
})

const limits = { price_fresh_hours: 3, price_stale_hours: 24, refresh_cooldown_minutes: 5 }
const agoIso = (minutes: number) => new Date(Date.now() - minutes * 60000).toISOString()
const pure = (node: ReactNode) => renderToStaticMarkup(<LanguageProvider>{node}</LanguageProvider>)

describe('ProposalDetailView', () => {
  it('reads the proposal route', () => {
    const id = '00000000-0000-4000-8000-0000000000aa'
    expect(readRoute(`/trips/${id}/proposals/${id}`)).toEqual({ page: 'proposal', tripId: id, proposalId: id })
    expect(readRoute(`/trips/${id}/proposals/nope`)).toEqual({ page: 'not-found' })
  })
  it('shows no evidence, quote or internal source name anywhere', () => {
    const html = page(proposal({ sources: [{ id: 1, title: 'Ignav booking link: Saudia', url: 'https://x.example/' }, { id: 2, title: 'Fare note', url: 'https://y.example/', kind: 'flight' }] }))
    expect(html).not.toContain('Show evidence')
    expect(html).not.toContain('A fictional quote.')
    expect(html).not.toContain('Ignav')
    expect(html).not.toContain('Fare note')
  })
  it('shows one price badge, not one for each flight field', () => {
    const html = page()
    expect(html).toContain('Confirmed by the seller')
    expect(count(html, 'Confirmed by the seller')).toBe(2)
  })
  it('shows Estimated with About', () => {
    const html = page()
    expect(html).toContain('Estimated')
    expect(html).toContain('About 450 SAR')
    expect(html).toContain('per night')
    expect(html).toContain('About 1,800 SAR for the whole stay')
  })
  it('shows Unconfirmed with its warning and no About', () => {
    const html = page(proposal({ cities: [{ ...stay, hotel_price_per_night: { amount_sar: '750', status: 'Unconfirmed', evidence: [] } }] }))
    expect(html).toContain('Unconfirmed · Check before booking')
    expect(html).toContain('750 SAR')
    expect(html).not.toContain('About 750')
  })
  it('shows the area and a named hotel with its search button', () => {
    const html = page(proposal({ cities: [{ ...stay, area: 'Zamalek' }] }))
    expect(html).toContain('Zamalek')
    expect(html).toContain('Search on Booking.com')
    expect(html).toContain('target="_blank" rel="noopener noreferrer"')
  })
  it('shows the three price ages', () => {
    const fresh = page(proposal({ flights: [flights({ priced_at: agoIso(30) })] }), true, 'p1', limits)
    expect(fresh).toContain('Updated 30 minutes ago')
    expect(fresh).toContain('details-age--fresh')
    const recent = page(proposal({ flights: [flights({ priced_at: agoIso(5 * 60) })] }), true, 'p1', limits)
    expect(recent).toContain('5 hours ago. It may have changed.')
    expect(recent).toContain('details-age--recent')
    const old = page(proposal({ flights: [flights({ priced_at: agoIso(30 * 60) })] }), true, 'p1', limits)
    expect(old).toContain('Old price. Refresh it before booking.')
    expect(old).toContain('details-age--old')
  })
  it('uses the generation time for a price with no time of its own', () => {
    expect(page(proposal(), true, 'p1', { generated_at: agoIso(10) })).toContain('Updated 10 minutes ago')
  })
  it('shows a round trip with one total and one button', () => {
    const html = page()
    expect(html).toContain('Round trip · One booking')
    expect(html).toContain('Round trip, per person')
    expect(html).toContain('Outbound')
    expect(html).toContain('Return')
    expect(count(html, 'Book the trip')).toBe(1)
    expect(html).not.toContain('Book this flight')
    expect(html).toContain('We check the flight when you press')
  })
  it('shows each leg in full when the details are known', () => {
    const html = page(proposal({ flights: [flights({ legs: [{ ...leg('outbound', null), flight_number: 'SV 1020', departure_time: '2026-12-13T08:30', arrival_time: '2026-12-13T11:50', stops: 0 }, { ...leg('return', null), stops: 1 }] })] }))
    expect(html).toContain('SV 1020')
    expect(html).toContain('08:30')
    expect(html).toContain('11:50')
    expect(html).toContain('Nonstop')
    expect(html).toContain('One stop')
  })
  it('shows split flights with a price and button for each direction', () => {
    const html = page(proposal({ flights: [flights({ trip_type: 'split', price_per_person: price('2150'), legs: [leg('outbound', 'https://air.example/out', price('1138')), leg('return', 'https://air.example/back', price('1012'))] })] }))
    expect(html).toContain('Two separate bookings. Book both.')
    expect(count(html, 'Book this flight')).toBe(2)
    expect(html).toContain('From 1,138 SAR')
    expect(html).toContain('From 1,012 SAR')
  })
  it('warns that a one way trip leaves out the return', () => {
    const html = page(proposal({ budget_status: 'includes_unconfirmed', flights: [flights({ trip_type: 'one_way', legs: [leg('outbound', 'https://air.example/out', price('500'))] })] }))
    expect(html).toContain('One way only')
    expect(html).toContain('The return price is not counted.')
    expect(html).not.toContain('>Return<')
    expect(count(html, 'Book this flight')).toBe(1)
  })
  it('never opens a saved flight link: pressing the button asks for a fresh one', () => {
    const html = page(proposal({ flights: [flights({ legs: [leg('outbound', 'https://old.example/expired'), leg('return', 'https://old.example/expired')] })] }))
    expect(html).not.toContain('old.example')
    expect(html).toContain('Book the trip')
  })
  it('says the flight fits everyone from the city, or that none does, with no count', () => {
    const fits = page(proposal({ flights: [flights({ group_availability: 'available' })] }))
    expect(fits).toContain('Available for all travellers from your city')
    const none = page(proposal({ flights: [flights({ group_availability: 'not_found' })] }))
    expect(none).toContain('You may need different flights.')
  })
  it('shows a group total only when the whole trip departs from one city', () => {
    const route = flights({ group_total_sar: '1800.00' })
    expect(page(proposal({ flights: [route] }), true, 'p1', { all_same_city: true })).toContain('for the whole group')
    expect(page(proposal({ flights: [route] }), true, 'p1', { all_same_city: false })).not.toContain('for the whole group')
    expect(page(proposal({ flights: [flights({})] }))).not.toContain('for the whole group')
  })
  it('warns when the price shown is for booking alone', () => {
    const html = page(proposal({ flights: [flights({ fare_basis: 'solo', solo_saving_sar: '50.00' })] }))
    expect(html).toContain('you may not be on the same flight')
    expect(page(proposal({ flights: [flights({ fare_basis: 'group' })] }))).not.toContain('you may not be on the same flight')
  })
  const checked = (extra: Partial<FlightCheckResult> = {}): FlightCheckResult => ({
    url: 'https://air.example/new', seller: 'طيران الخليج', seller_type: 'airline', provider: 'ignav', exact_flight: true, price_sar: '998.50', previous_price_sar: null,
    cabin_class: 'economy', fare_name: null, checked_bags: null, carry_on_bags: null,
    flights: [{ direction: 'outbound', airline: 'طيران الخليج', flight_number: 'GF 162', departure_time: '2026-11-20T06:50:00', arrival_time: '2026-11-20T08:10:00' }],
    updated: true, fallback: null, alternative: null, now_over_budget: false, checked_at: new Date().toISOString(), link_valid_minutes: 15, next_refresh_seconds: 120, ...extra,
  })
  it('shows the old and new price with the difference, and opens in a new tab', () => {
    const html = pure(<BookResultView result={checked({ previous_price_sar: '900' })} />)
    expect(html).toContain('Was 900 SAR → now 998.5 SAR (+98.5 SAR)')
    expect(html).toContain('href="https://air.example/new"')
    expect(html).toContain('target="_blank" rel="noopener noreferrer"')
  })
  it('says a checked price is the same', () => {
    expect(pure(<BookResultView result={checked()} />)).toContain('Checked just now. The price is the same.')
    const down = priceChange('800', '900')
    expect(down?.difference).toBe(-100)
    expect(priceChange('900', '900')).toBeNull()
  })
  it('counts down the link, then asks for a new check', () => {
    const at = '2026-11-01T10:00:00Z'
    const base = new Date(at).getTime()
    expect(linkMinutesLeft(at, 15, base + 60000)).toBe(14)
    expect(linkMinutesLeft(at, 15, base + 15 * 60000)).toBe(0)
    expect(linkMinutesLeft(null, 15, base)).toBeNull()
    const open = pure(<BookResultView result={checked({ checked_at: at })} now={base + 5 * 60000} />)
    expect(open).toContain('about 10 more minutes')
    expect(open).toContain('role="timer"')
    expect(open).toContain('href="https://air.example/new"')
    const late = pure(<BookResultView result={checked({ checked_at: at })} now={base + 16 * 60000} onRecheck={() => undefined} />)
    expect(late).toContain('This link may have expired.')
    expect(late).toContain('Check again')
    expect(late).not.toContain('href="https://air.example/new"')
  })
  it('names the flight and time when the link is a results page', () => {
    expect(pure(<BookResultView result={checked({ exact_flight: false })} />)).toContain('Choose flight GF 162 at 06:50.')
  })
  it('shows the fare and bag, or says the bag may not be included', () => {
    const unknown = pure(<BookResultView result={checked()} />)
    expect(unknown).toContain('Economy')
    expect(unknown).toContain('may not include a bag')
    expect(pure(<BookResultView result={checked({ checked_bags: 0 })} />)).toContain('No checked bag')
  })
  it('names the source plainly and never the internal one', () => {
    const html = pure(<BookResultView result={checked()} />)
    expect(html).toContain('Price directly from the seller')
    expect(html).not.toContain('ignav')
    expect(pure(<BookResultView result={checked({ provider: 'tripcom', seller: 'Trip.com', seller_type: 'third_party' })} />)).toContain('Price from Trip.com')
  })
  it('shows a replacement with its flight, time and price', () => {
    const found = { ...checked(), reason: 'gone' as const, within_budget: false, seller: 'Saudia', price_sar: '1000.00', flights: [{ direction: 'outbound' as const, airline: 'Saudia', flight_number: 'SV 1', departure_time: '2026-11-20T09:00:00', arrival_time: '2026-11-20T10:30:00' }] }
    const html = pure(<BookResultView result={checked({ alternative: found })} />)
    expect(html).toContain('The original flight is gone. We found a replacement.')
    expect(html).toContain('SV 1')
    expect(html).toContain('09:00')
    expect(html).toContain('From 1,000 SAR')
    expect(html).toContain('over the group budget')
  })
  it('offers a cheaper flight or one that opens directly, with its own link', () => {
    const found = { ...checked(), url: 'https://www.flynas.com/b', reason: 'cheaper' as const, within_budget: true, price_sar: '1000.00' }
    const html = pure(<BookResultView result={checked({ alternative: found })} />)
    expect(html).toContain('A cheaper option you can book directly')
    expect(html).toContain('https://www.flynas.com/b')
  })
  it('explains every search link, and never says a failed check means gone', () => {
    const base = { url: 'https://www.google.com/travel/flights', exact_flight: false, price_sar: null, checked_at: null }
    expect(pure(<BookResultView result={checked({ ...base, fallback: 'not_available' })} />)).toContain('we found no replacement')
    expect(pure(<BookResultView result={checked({ ...base, fallback: 'limit' })} />)).toContain('update limit')
    const failed = pure(<BookResultView result={checked({ ...base, fallback: 'check_failed' })} />)
    expect(failed).toContain('nothing was checked')
    expect(failed).not.toContain('gone')
    expect(pure(<BookResultView result={checked({ ...base, fallback: 'no_link' })} />)).toContain('gives no page that opens it directly')
  })
  it('never makes a link from an unsafe address', () => {
    expect(pure(<BookResultView result={checked({ url: 'javascript:alert(1)', fallback: 'limit', checked_at: null, price_sar: null })} />)).not.toContain('javascript:')
  })
  it('shows the booking steps', () => {
    expect(pure(<BookSteps busy={false} result={null} />)).toBe('')
    const busy = pure(<BookSteps busy result={null} />)
    expect(busy).toContain('Checking the price and seats now…')
    expect(busy).toContain('aria-current="step"')
    expect(pure(<BookSteps busy={false} result={checked()} />)).toContain('Open the booking page')
  })
  it('turns off the refresh button for a while, and says how long', () => {
    const props = { busy: false, result: null, error: '', onRefresh: () => undefined }
    const waiting = pure(<RefreshView {...props} waitMinutes={2} />)
    expect(waiting).toContain('disabled')
    expect(waiting).toContain('You can check again in 2 minutes.')
    expect(pure(<RefreshView {...props} waitMinutes={0} />)).not.toContain('disabled')
  })
  it('says a new price passed the budget without any figure', () => {
    const html = pure(<RefreshView busy={false} error="" waitMinutes={0} onRefresh={() => undefined} result={checked({ now_over_budget: true, price_sar: null, checked_at: null })} />)
    expect(html).toContain('over the group budget')
    expect(html).not.toMatch(/\d/)
  })
  it('reloads after a check that saved, so the page shows the new price', async () => {
    const reload = vi.fn()
    await checkAndReload(async () => checked({ updated: true }), reload)
    expect(reload).toHaveBeenCalledTimes(1)
    await checkAndReload(async () => checked({ updated: false }), reload)
    expect(reload).toHaveBeenCalledTimes(1)
    expect(page(proposal({ flights: [flights({ price_per_person: price('998.50', 'Sourced') })] }))).toContain('From 998.5 SAR')
  })
  it('shows the notice beside flights and stays, and a from price on every flight', () => {
    const html = page()
    expect(count(html, 'Prices and seats change from time to time.')).toBe(2)
    expect(html).toContain('From 900 SAR')
    expect(html).toContain('This price covers both directions.')
  })
  it('shows one line for a city with no hotel, not a repeated label', () => {
    const html = page(proposal({ flights: [], sources: [], cities: [{ ...stay, hotel_name: { value: null, status: 'Not available', evidence: [] }, hotel_price_per_night: none }] }))
    expect(html).toContain('We did not find a confirmed hotel in Cairo')
    expect(html).toContain('Search for hotels in Cairo')
    expect(html).not.toContain('—')
    expect(html).not.toContain('The hotel is not confirmed yet')
  })
  it('offers a direct hotel page first and Booking as the comparison', () => {
    const html = page(proposal({ cities: [{ ...stay, hotel_url: 'https://www.trip.com/hotels/x', hotel_source: 'Trip.com' }] }))
    expect(html).toContain('Book this hotel')
    expect(html).toContain('Compare on Booking')
    expect(html).toContain('Trip.com')
    expect(page()).not.toContain('Book this hotel')
    expect(page()).toContain('See photos of this hotel')
  })
  it('names the site behind a hotel price', () => {
    expect(staySource(stay, [{ id: 1, title: 'T', url: 'https://www.kayak.com/h' }])).toBe('kayak.com')
    expect(staySource({ ...stay, hotel_source: 'Trip.com' }, [])).toBe('Trip.com')
  })
  it('shows photos with their credit, and a designed panel without one', () => {
    const image = { url: 'https://upload.wikimedia.org/a.jpg', source_url: 'https://commons.wikimedia.org/a', artist: 'A. Person', license: 'CC BY-SA 4.0' }
    const html = page(proposal({ image, cities: [{ ...stay, image }] }))
    expect(html).toContain('upload.wikimedia.org/a.jpg')
    expect(html).toContain('A. Person')
    expect(html).toContain('CC BY-SA 4.0')
    expect(html).toContain('alt="Photo of Cairo"')
    expect(html).toContain('loading="lazy"')
    const plain = page()
    expect(plain).not.toContain('<img')
    expect(plain).toContain('details-photo-empty')
    expect(pure(<PlacePhoto image={{ ...image, url: 'javascript:x' }} place="Cairo" />)).not.toContain('javascript:')
  })
  it('shows airlines in the page language, and leaves unknown ones', () => {
    expect(airlineName('طيران الخليج', 'en')).toBe('Gulf Air')
    expect(airlineName('Gulf Air', 'ar')).toBe('طيران الخليج')
    expect(airlineName('Mock Air', 'ar')).toBe('Mock Air')
    const gulf = flights({ legs: [{ ...leg('outbound', null), airline: info('طيران الخليج') }, leg('return', null)] })
    expect(page(proposal({ flights: [gulf] }))).toContain('Gulf Air')
    localStorage.setItem('rihla-language', 'ar')
    const arabic = page(proposal({ flights: [flights({ legs: [{ ...leg('outbound', null), airline: info('Gulf Air') }, leg('return', null)] })] }))
    expect(arabic).toContain('طيران الخليج')
    expect(arabic).toContain('الأسعار والمقاعد تتغير')
    expect(arabic).toContain('يبدأ من')
  })
  it('hides travel between cities for one city and shows it for two', () => {
    expect(page()).not.toContain('Travel between cities')
    const second = { ...stay, order: 2, city: 'Luxor', nights: 2 }
    const html = page(proposal({
      cities: [{ ...stay, nights: 2 }, second],
      intercity_transport: [{ from_city: 'Cairo', to_city: 'Luxor', mode: info('Train'), duration: info('9h'), price_per_person: price('200') }],
    }))
    expect(html).toContain('Travel between cities')
    expect(html).toContain('Train')
    expect(html).toContain('Two cities')
  })
  it('tells the administrator and a member different things when their city has no flights', () => {
    expect(page(proposal({ flights: [] }))).toContain('Generate the proposals again')
    expect(page(proposal({ flights: [] }), false)).toContain('Wait for the administrator')
  })
  it('says a removed proposal was replaced', () => {
    const html = page(proposal(), true, 'gone')
    expect(html).toContain('This proposal has been replaced.')
    expect(html).not.toContain('Main title')
  })
  it('shows the Flexible adjustment and a general note after changes', () => {
    const html = page(proposal({ flexible_adjustments: [{ category: 'flights', explanation: 'A stop was added.' }] }), false, 'p1', { needs_regeneration: true })
    expect(html).toContain('A stop was added.')
    expect(html).toContain('details changed after these proposals')
  })
  it('splits booking sources from sources for ideas', () => {
    const html = page(proposal({ sources: [{ id: 1, title: 'On Booking', url: 'https://a.example/', kind: 'booking' }, { id: 2, title: 'A blog', url: 'https://b.example/', kind: 'ideas' }] }))
    expect(html).toContain('Booking and price sources')
    expect(html).toContain('Sources for ideas')
    expect(html.indexOf('On Booking')).toBeLessThan(html.indexOf('A blog'))
  })
  it('picks the title by language and falls back to the main title', () => {
    expect(page(proposal({ title_en: 'English title', title_ar: 'عنوان عربي' }))).toContain('English title')
    expect(page()).toContain('Main title')
    localStorage.setItem('rihla-language', 'ar')
    const html = page(proposal({ title_en: 'English title', title_ar: 'عنوان عربي' }))
    expect(html).toContain('عنوان عربي')
    expect(html).toContain('مؤكد من البائع')
    expect(page()).toContain('Main title')
  })
  it('shows places in Arabic, preferring the stored name, and leaves unknown ones', () => {
    localStorage.setItem('rihla-language', 'ar')
    const html = page(proposal({ destination: 'Bahrain', cities: [{ ...stay, city: 'Manama' }], flights: [flights({ origin: 'Riyadh' })] }))
    expect(html).toContain('البحرين')
    expect(html).toContain('المنامة')
    expect(html).toContain('الرياض')
    expect(placeName('Paris', 'ar', 'باريس المخزنة')).toBe('باريس المخزنة')
    expect(placeName('Nowhere', 'ar')).toBe('Nowhere')
    expect(placeName('الرياض', 'en')).toBe('Riyadh')
  })
})
