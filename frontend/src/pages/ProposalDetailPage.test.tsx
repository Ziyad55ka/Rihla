import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
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

describe('ProposalDetailView', () => {
  it('reads the proposal route', () => {
    const id = '00000000-0000-4000-8000-0000000000aa'
    expect(readRoute(`/trips/${id}/proposals/${id}`)).toEqual({ page: 'proposal', tripId: id, proposalId: id })
    expect(readRoute(`/trips/${id}/proposals/nope`)).toEqual({ page: 'not-found' })
  })
  it('shows Sourced with its evidence and source link', () => {
    const html = page(proposal({ cities: [{ ...stay, hotel_price_per_night: price('450', 'Sourced') }] }))
    expect(html).toContain('From a source')
    expect(html).toContain('Show evidence')
    expect(html).toContain('A fictional quote.')
    expect(html).toContain('href="https://source.example/page"')
  })
  it('shows Estimated with About and evidence', () => {
    const html = page()
    expect(html).toContain('Estimated')
    expect(html).toContain('About 450 SAR')
    expect(html).toContain('per night')
  })
  it('shows Unconfirmed with its warning and no About', () => {
    const html = page(proposal({ cities: [{ ...stay, hotel_price_per_night: { amount_sar: '750', status: 'Unconfirmed', evidence: [] } }] }))
    expect(html).toContain('Unconfirmed · Check before booking')
    expect(html).toContain('750 SAR')
    expect(html).not.toContain('About 750')
  })
  it('shows Not available as a dash with no number or evidence', () => {
    const html = page(proposal({ flights: [], sources: [], cities: [{ ...stay, hotel_name: { value: null, status: 'Not available', evidence: [] }, hotel_price_per_night: none }] }))
    expect(html).toContain('Not available')
    expect(html).toContain('—')
    expect(html).not.toContain('Show evidence')
    expect(html).not.toContain('SAR')
    expect(html).toContain('Search for hotels in Cairo')
  })
  it('shows a round trip with one price and one button', () => {
    const html = page()
    expect(html).toContain('Round trip · One booking')
    expect(html).toContain('Outbound')
    expect(html).toContain('Return')
    expect(count(html, 'Book the trip')).toBe(1)
    expect(html).not.toContain('Book this flight')
  })
  it('shows split flights with a price and button for each direction', () => {
    const html = page(proposal({ flights: [flights({ trip_type: 'split', price_per_person: price('2150'), legs: [leg('outbound', 'https://air.example/out', price('1138')), leg('return', 'https://air.example/back', price('1012'))] })] }))
    expect(html).toContain('Two separate bookings')
    expect(count(html, 'Book this flight')).toBe(2)
    expect(html).toContain('About 1,138 SAR')
    expect(html).toContain('About 1,012 SAR')
    expect(html).toContain('The total is an estimate')
  })
  it('warns that a one way trip leaves out the return', () => {
    const html = page(proposal({ budget_status: 'includes_unconfirmed', flights: [flights({ trip_type: 'one_way', legs: [leg('outbound', 'https://air.example/out', price('500'))] })] }))
    expect(html).toContain('One way only')
    expect(html).toContain('The return price is not counted.')
    expect(html).not.toContain('>Return<')
  })
  it('hides the button and says so when a booking link is missing', () => {
    const html = page(proposal({ flights: [flights({ legs: [leg('outbound', null), leg('return', null)] })] }))
    expect(html).not.toContain('Book the trip')
    expect(html).toContain('No booking link')
  })
  it('never makes a link from an unsafe address', () => {
    const html = page(proposal({ flights: [flights({ legs: [leg('outbound', 'javascript:alert(1)'), leg('return', 'javascript:alert(1)')] })] }))
    expect(html).not.toContain('javascript:')
  })
  it('opens every booking link in a new tab, with the warning under it', () => {
    const html = page()
    expect(count(html, 'target="_blank" rel="noopener noreferrer"')).toBeGreaterThanOrEqual(3)
    expect(count(html, 'Check the flight and price before paying.')).toBe(2)
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
  it('picks the title by language and falls back to the main title', () => {
    expect(page(proposal({ title_en: 'English title', title_ar: 'عنوان عربي' }))).toContain('English title')
    expect(page()).toContain('Main title')
    localStorage.setItem('rihla-language', 'ar')
    const html = page(proposal({ title_en: 'English title', title_ar: 'عنوان عربي' }))
    expect(html).toContain('عنوان عربي')
    expect(html).toContain('من مصدر')
    expect(page()).toContain('Main title')
  })
})
