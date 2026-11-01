import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ReactNode } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { BookResultView, RefreshView } from '../components/proposal-details/FlightActions'
import { refreshWaitMinutes } from '../lib/proposals'
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
  it('shows a hotel with no approved source as a dash and a city search', () => {
    const html = page(proposal({ flights: [], sources: [], cities: [{ ...stay, hotel_name: { value: null, status: 'Not available', evidence: [] }, hotel_price_per_night: none }] }))
    expect(html).toContain('Not available')
    expect(html).toContain('—')
    expect(html).not.toContain('SAR')
    expect(html).toContain('Search for hotels in Cairo')
    expect(html).not.toContain('Search on Booking.com')
    expect(html).toContain('Check for enough rooms for the group.')
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
    expect(html).toContain('Finish booking quickly')
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
    expect(html).toContain('Two separate bookings on two airlines. Book both.')
    expect(count(html, 'Book this flight')).toBe(2)
    expect(html).toContain('About 1,138 SAR')
    expect(html).toContain('About 1,012 SAR')
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
  it('asks before continuing at a changed price, and opens in a new tab', () => {
    const html = pure(<BookResultView result={{ url: 'https://air.example/new', fallback: null, seller: 'Saudia', exact_flight: true, price_sar: '950', previous_price_sar: '900' }} />)
    expect(html).toContain('The price is now 950 SAR instead of 900 SAR. Continue?')
    expect(html).toContain('href="https://air.example/new"')
    expect(html).toContain('target="_blank" rel="noopener noreferrer"')
  })
  it('explains the search link when the flight is gone or a limit was reached', () => {
    const base = { url: 'https://www.google.com/travel/flights', seller: null, exact_flight: false, price_sar: null, previous_price_sar: null }
    expect(pure(<BookResultView result={{ ...base, fallback: 'not_available' }} />)).toContain('The original flight is no longer available')
    expect(pure(<BookResultView result={{ ...base, fallback: 'limit' }} />)).toContain('today’s update limit')
  })
  it('never makes a link from an unsafe address', () => {
    expect(pure(<BookResultView result={{ url: 'javascript:alert(1)', fallback: 'limit', seller: null, exact_flight: false, price_sar: null, previous_price_sar: null }} />)).not.toContain('javascript:')
  })
  it('disables the refresh button for a while, and says how long', () => {
    expect(refreshWaitMinutes(agoIso(2), 5, Date.now())).toBe(3)
    expect(refreshWaitMinutes(agoIso(10), 5, Date.now())).toBe(0)
    expect(refreshWaitMinutes(null, 5, Date.now())).toBe(0)
    const props = { busy: false, result: null, error: '', onRefresh: () => undefined }
    const waiting = pure(<RefreshView {...props} waitMinutes={3} />)
    expect(waiting).toContain('disabled')
    expect(waiting).toContain('You can refresh again in 3 minutes.')
    expect(pure(<RefreshView {...props} waitMinutes={0} />)).not.toContain('disabled')
  })
  it('says a new price passed the budget without any figure', () => {
    const html = pure(<RefreshView busy={false} error="" waitMinutes={0} onRefresh={() => undefined} result={{ updated: true, fallback: null, url: null, now_over_budget: true, next_refresh_seconds: 300 }} />)
    expect(html).toContain('over the group budget')
    expect(html).not.toMatch(/\d/)
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
    expect(html).toContain('Booking sources')
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
