/// <reference types="node" />
import { readFileSync } from 'node:fs'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ReactNode } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { BookResultView, BookSteps, RefreshView, SplitBooking, TimerRing } from '../components/proposal-details/FlightActions'
import { PlacePhoto } from '../components/proposal-details/PlacePhoto'
import { airlineName } from '../lib/airlines'
import { ActivitiesSection } from '../components/proposal-details/ActivitiesSection'
import { bookingLink, checkAndReload, durationLabel, type FlightCheckResult, linkFractionLeft, linkMinutesLeft, modeKind, priceChange, transferLink } from '../lib/proposals'
import { AiStatus } from '../components/AiStatus'
import { checkMessages, generateMessages, nextStatusIndex } from '../lib/aiStatus'
import { countUpValue } from '../lib/motion'
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

const detailsCss = readFileSync('src/proposal-details.css', 'utf8')
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
    // The reliability legend in the sources section (US-14) names every label once more.
    expect(count(html.split('id="details-costs"')[0], 'Confirmed by the seller')).toBe(1)
  })
  it('shows Estimated with About', () => {
    const html = page()
    expect(html).toContain('Estimated')
    expect(html).toContain('About 450 SAR')
    expect(html).toContain('per night')
  })
  it('shows Unconfirmed with its warning and no About', () => {
    const html = page(proposal({ cities: [{ ...stay, hotel_price_per_night: { amount_sar: '750', status: 'Unconfirmed', evidence: [] } }] }))
    expect(html).toContain('Rough estimate · Check before booking')
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
    expect(html).toContain('Round trip, per person')
    expect(html).toContain('Outbound')
    expect(html).toContain('Return')
    expect(count(html, '>Book<')).toBe(1)
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
    expect(count(html, 'Two separate bookings')).toBe(1)
    expect(count(html, '>Book<')).toBe(1)
    expect(html).toContain('Outbound 1,138 SAR + return 1,012 SAR')
  })
  it('warns that a one way trip leaves out the return', () => {
    const html = page(proposal({ budget_status: 'includes_unconfirmed', flights: [flights({ trip_type: 'one_way', legs: [leg('outbound', 'https://air.example/out', price('500'))] })] }))
    expect(html).toContain('One way only')
    expect(html).toContain('The return price is not counted.')
    expect(html).not.toContain('>Return<')
    expect(count(html, '>Book<')).toBe(1)
  })
  it('never opens a saved flight link: pressing the button asks for a fresh one', () => {
    const html = page(proposal({ flights: [flights({ legs: [leg('outbound', 'https://old.example/expired'), leg('return', 'https://old.example/expired')] })] }))
    expect(html).not.toContain('old.example')
    expect(html).toContain('>Book<')
  })
  it('says the flight fits everyone from the city, or that none does, with no count', () => {
    const fits = page(proposal({ flights: [flights({ group_availability: 'available' })] }))
    expect(fits).toContain('Available for all travellers from your city')
    const none = page(proposal({ flights: [flights({ group_availability: 'not_found' })] }))
    expect(none).toContain('You may need different flights.')
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
    airline_fares: [], updated: true, fallback: null, alternative: null, now_over_budget: false, checked_at: new Date().toISOString(), link_valid_minutes: 15, next_refresh_seconds: 120, ...extra,
  })
  it('shows the old and new price with the difference, and opens in a new tab', () => {
    const html = pure(<BookResultView result={checked({ previous_price_sar: '900' })} />)
    expect(html).toContain('Was 900 SAR, now 998.5 SAR (+98.5 SAR)')
    expect(html).toContain('href="https://air.example/new"')
    expect(html).toContain('target="_blank" rel="noopener noreferrer"')
  })
  it('says a checked price is the same', () => {
    expect(pure(<BookResultView result={checked()} />)).toContain('Checked just now. The price is the same.')
    expect(pure(<BookResultView result={checked()} />)).not.toContain('Find another flight')
    expect(pure(<BookResultView result={checked()} onNotOffered={() => undefined} />)).toContain('Find another flight')
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
  const back = { direction: 'return' as const, airline: 'طيران الخليج', flight_number: 'GF 163', departure_time: '2026-11-30T09:35:00', arrival_time: '2026-11-30T11:00:00' }
  const note = { code: 'GF', name_en: 'Gulf Air', name_ar: 'طيران الخليج', fare_en: 'Economy Light', fare_ar: 'السياحية الخفيفة', checked_kg: 25 }
  it('says which flights and fare to choose, and the total to expect', () => {
    const both = checked({ exact_flight: false, price_sar: '1614', flights: [checked().flights[0], back], airline_fares: [note] })
    const html = pure(<BookResultView result={both} />)
    expect(html).toContain('This is a results page')
    expect(html).toContain('Choose the outbound GF 162 at 06:50, then the return GF 163 at 09:35, in the Economy Light fare, and check the total is close to 1,614 SAR.')
    expect(pure(<BookResultView result={{ ...both, airline_fares: [] }} />)).toContain('then the return GF 163 at 09:35, and check the total')
    localStorage.setItem('rihla-language', 'ar')
    const arabic = pure(<BookResultView result={both} />)
    expect(arabic).toContain('اختر الذهاب GF 162 الساعة ٠٦:٥٠')
    expect(arabic).toContain('بفئة السياحية الخفيفة')
    localStorage.clear?.()
  })
  it('guides one direction of separate bookings', () => {
    const both = checked({ price_sar: '615', flights: [checked().flights[0], back] })
    expect(pure(<BookResultView result={both} leg="inbound" />)).toContain('Choose flight GF 163 at 09:35, and check the price is close to 615 SAR.')
  })
  it('shows the fare and bag, or says the bag may not be included', () => {
    const unknown = page(proposal({ flights: [flights({ cabin_class: 'economy' })] }))
    expect(unknown).toContain('Economy')
    expect(unknown).toContain('may not include a bag')
    expect(page(proposal({ flights: [flights({ checked_bags: 0 })] }))).toContain('No checked bag')
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
    expect(html).toContain('The original flight is gone. Replacement: Saudia · 1,000 SAR')
    expect(html).toContain('SV 1')
    expect(html).toContain('09:00')
    expect(html).toContain('over the group budget')
  })
  it('offers a cheaper flight or one that opens directly, with its own link', () => {
    const found = { ...checked(), url: 'https://www.flynas.com/b', reason: 'cheaper' as const, within_budget: true, price_sar: '1000.00' }
    const html = pure(<BookResultView result={checked({ alternative: found })} />)
    expect(html).toContain('Cheaper option available')
    expect(html).toContain('https://www.flynas.com/b')
  })
  it('says plainly when the cheaper option is an agent', () => {
    const found = { ...checked(), url: 'https://agent.example/x', reason: 'agent' as const, within_budget: true, seller: 'Mock Agent', price_sar: '900.00' }
    const html = pure(<BookResultView result={checked({ alternative: found })} />)
    expect(html).toContain('Cheaper through a travel agent: Mock Agent')
    expect(html).toContain('This is an agent, not the airline')
    expect(html).toContain('Mock Agent')
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
    expect(html.replace(/<[^>]+>/g, ' ')).not.toMatch(/\d/)
  })
  it('reloads after a check that saved, so the page shows the new price', async () => {
    const reload = vi.fn()
    await checkAndReload(async () => checked({ updated: true }), reload)
    expect(reload).toHaveBeenCalledTimes(1)
    await checkAndReload(async () => checked({ updated: false }), reload)
    expect(reload).toHaveBeenCalledTimes(1)
    expect(page(proposal({ flights: [flights({ price_per_person: price('998.50', 'Sourced') })] }))).toContain('From 998.5 SAR')
  })
  it('breaks the price down only when each direction has its own price', () => {
    const parted = flights({ price_per_person: price('1614', 'Sourced'), legs: [leg('outbound', 'https://a.example/x', price('999')), leg('return', 'https://a.example/x', price('615'))] })
    const html = page(proposal({ flights: [parted] }))
    expect(html).toContain('Outbound 999 SAR + return 615 SAR = 1,614 SAR per person')
    expect(html).not.toContain('may show the outbound price first')
    expect(page()).not.toContain('Outbound 900')
    localStorage.setItem('rihla-language', 'ar')
    const arabic = page(proposal({ flights: [parted] }))
    expect(arabic).toContain('الذهاب')
    expect(arabic).toContain('الإجمالي')
  })
  it('shows the general fare and bag, or says to check, in the page language', () => {
    const note = { code: 'GF', name_en: 'Gulf Air', name_ar: 'طيران الخليج', fare_en: 'Economy Light', fare_ar: 'السياحية الخفيفة', checked_kg: 25 }
    const unknown = { ...note, code: 'SV', name_en: 'Saudia', fare_en: 'Guest Saver', checked_kg: null }
    const html = page(proposal({ flights: [flights({ airline_fares: [note, unknown] })] }))
    expect(html).toContain('Economy Light')
    expect(html).toContain('Checked bag 25 kg')
    expect(html).toContain('Check the bag on the airline’s site')
    expect(html).toContain('not a promise for your ticket')
    expect(page(proposal({ flights: [flights({ airline_fares: [{ ...note, checked_kg: 0 }] })] }))).toContain('No checked bag')
    expect(page(proposal({ flights: [flights({ airline_fares: [note], checked_bags: 2 })] }))).toContain('2 checked bags')
    localStorage.setItem('rihla-language', 'ar')
    expect(page(proposal({ flights: [flights({ airline_fares: [note] })] }))).toContain('السياحية الخفيفة')
  })
  const lined = () => flights({
    origin_airport: 'RUH', destination_airport: 'CDG',
    legs: [{ ...leg('outbound', null), flight_number: 'A3 953', departure_time: '2026-12-13T06:50:00', arrival_time: '2026-12-13T20:35:00', stops: 1, stop_airports: ['ATH'] }, { ...leg('return', null), flight_number: 'VF 10', departure_time: '2026-12-17T01:25:00', arrival_time: '2026-12-17T09:00:00', stops: 0 }],
  })
  it('draws each direction as a flight line with times, airports and stops', () => {
    const html = page(proposal({ flights: [lined()] }))
    expect(html).toContain('details-line-track')
    expect(html).toContain('06:50')
    expect(html).toContain('20:35')
    expect(html).toContain('RUH')
    expect(html).toContain('CDG')
    expect(html).toContain('A3 953')
    expect(html).toContain('Stop at ATH')
    expect(html).toContain('One stop')
    expect(html).toContain('Nonstop')
    expect(count(html, 'details-line-stop')).toBe(1)
  })
  it('says when Google Flights also sells the same flights', () => {
    expect(page(proposal({ flights: [{ ...lined(), schedule_confirmed: true }] }))).toContain('Also on sale on Google Flights')
    expect(page(proposal({ flights: [lined()] }))).not.toContain('Also on sale on Google Flights')
  })
  it('flies home from the last city when the trip ends somewhere else', () => {
    const base = proposal()
    const twoCities = proposal({ cities: [base.cities[0], { ...base.cities[0], city: 'Barcelona', city_ar: 'برشلونة' }], flights: [{ ...lined(), return_airport: 'BCN' }] })
    const html = page(twoCities)
    expect(html).toContain('BCN')
    expect(html).toContain('Barcelona')
    expect(page(proposal({ flights: [lined()] }))).not.toContain('BCN')
  })
  it('shows one price and one Book button, with each message only once', () => {
    const html = page(proposal({ flights: [lined()] }))
    expect(count(html, '>Book<')).toBe(1)
    expect(count(html, 'Refresh the price')).toBe(1)
    expect(count(html, 'From 900 SAR')).toBe(1)
    expect(count(html, 'Approximate price. This is the base fare')).toBe(1)
  })
  it('opens split flights as two steps from one button, with one label', () => {
    const route = flights({ trip_type: 'split', price_per_person: price('2150'), legs: [leg('outbound', 'https://a.example/o', price('1138')), leg('return', 'https://a.example/b', price('1012'))] })
    const closed = page(proposal({ flights: [route] }))
    expect(count(closed, '>Book<')).toBe(1)
    expect(count(closed, 'Two separate bookings')).toBe(1)
    expect(closed).not.toContain('Check this flight')
    expect(closed).toContain('Outbound 1,138 SAR + return 1,012 SAR = 2,150 SAR per person')
    const open = pure(<SplitBooking tripId="t" proposalId="p" cooldownMinutes={2} onChanged={() => undefined} initiallyOpen />)
    expect(count(open, 'role="tab"')).toBe(2)
    expect(count(open, 'Check this flight')).toBe(2)
    expect(open).toContain('Next: the return')
    expect(open).toContain('aria-selected="true"')
  })
  it('folds the alternative behind one line, and opens a replacement', () => {
    const found = { ...checked(), url: 'https://air.example/alt', reason: 'cheaper' as const, within_budget: true, seller: 'Mock Air', price_sar: '2000.00' }
    const html = pure(<BookResultView result={checked({ alternative: found })} />)
    expect(html).toContain('<details')
    expect(html).toContain('Cheaper option available: Mock Air · 2,000 SAR')
    expect(html).not.toContain('<details class="details-alternative details-reveal" open')
    expect(pure(<BookResultView result={checked({ alternative: { ...found, reason: 'gone' } })} />)).toContain('open=""')
  })
  it('states only facts in the summary, with no judgement of fit', () => {
    const html = page(proposal())
    expect(html).toContain('smart summary')
    expect(html).toContain('Suggested by AI')
    expect(html).toContain('Fits the group budget')
    expect(html).toContain('One city')
    const two = page(proposal({ budget_status: 'over_group_budget', cities: [{ ...stay, nights: 2 }, { ...stay, order: 2, city: 'Luxor', nights: 2 }], intercity_transport: [{ from_city: 'Cairo', to_city: 'Luxor', mode: info('Train'), duration: info('9h'), price_per_person: price('200') }] }))
    expect(two).toContain('Over the group budget')
    expect(two).toContain('Two cities')
  })
  it('says once that a price is approximate, above flights and above hotels', () => {
    const html = page()
    expect(count(html, 'Approximate price. This is the base fare')).toBe(1)
    expect(count(html, 'Approximate nightly price.')).toBe(1)
    expect(pure(<BookResultView result={checked()} />)).toContain('Skip optional extras')
    localStorage.setItem('rihla-language', 'ar')
    const arabic = page()
    expect(arabic).toContain('سعر تقريبي لليلة')
    expect(pure(<BookResultView result={checked()} />)).toContain('تخطّى الإضافات الاختيارية')
  })
  it('shows only the hotel basics, with one room for each person in the link', () => {
    const fourPeople = 'https://www.booking.com/searchresults.html?ss=Cairo&group_adults=4&no_rooms=2'
    const html = page(proposal({ cities: [{ ...stay, booking_url: fourPeople, priced_at: agoIso(30) }] }))
    expect(html).toContain('Mock Hotel')
    expect(html).toContain('About 450 SAR')
    expect(html).toContain('details-age--fresh')
    expect(html).toContain('no_rooms=4')
    expect(html).not.toContain('for the whole stay')
    expect(html).not.toContain('share rooms')
    expect(bookingLink(fourPeople)).toContain('no_rooms=4')
    expect(bookingLink(null)).toBeNull()
    expect(bookingLink('javascript:x')).toBeNull()
  })
  it('uses only SVG icons, with no symbol that could show as a box, in both languages', () => {
    const symbols = /[\u2190-\u21FF\u2460-\u24FF\u25A0-\u27BF\u2900-\u2BFF\u{1F000}-\u{1FAFF}]/u
    const found = { ...checked(), url: 'https://a.example/', reason: 'no_link' as const, within_budget: true, price_sar: '100.00' }
    const views = () => [page(twoCities()), page(proposal({ flights: [lined()] })), pure(<BookResultView result={checked({ previous_price_sar: '900', alternative: found })} />)]
    for (const html of views()) { expect(html).not.toMatch(symbols); expect(html).toContain('<svg') }
    localStorage.setItem('rihla-language', 'ar')
    for (const html of views()) expect(html).not.toMatch(symbols)
  })
  it('shows the notice beside flights and stays, and a from price on every flight', () => {
    const html = page()
    expect(count(html, 'Approximate price. This is the base fare')).toBe(1)
    expect(html).toContain('From 900 SAR')
    expect(html).toContain('may show the outbound price first')
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
    expect(page()).toContain('Search on Booking.com')
  })
  it('shows the parts of the page in the agreed order, with sources last (US-14)', () => {
    const second = { ...stay, order: 2, city: 'Luxor', nights: 2 }
    const html = page(proposal({ cities: [{ ...stay, nights: 2 }, second], intercity_transport: [{ from_city: 'Cairo', to_city: 'Luxor', mode: info('Train'), duration: info('9h'), price_per_person: price('200') }] }))
    const order = ['details-hero', 'id="details-flights"', 'id="details-cities"', 'id="details-transfers"', 'id="details-costs"', 'id="details-match"', 'id="details-sources"']
    const places = order.map((part) => html.indexOf(part))
    expect(places.every((place) => place >= 0)).toBe(true)
    expect([...places].sort((x, y) => x - y)).toEqual(places)
    // A source with no kind may name an internal service, so it is never listed.
    expect(html).not.toContain('Mock source')
  })
  const twoCities = (extra = {}) => proposal({
    cities: [{ ...stay, city: 'Paris', nights: 2 }, { ...stay, order: 2, city: 'Strasbourg', nights: 2 }],
    intercity_transport: [{ from_city: 'Paris', to_city: 'Strasbourg', mode: info('Train'), duration: info('1h 48m'), price_per_person: price('260'), ...extra }],
  })
  it('draws the route as a line, with stations only when the data has them', () => {
    const plain = page(twoCities())
    expect(plain).toContain('details-metro')
    expect(plain).toContain('Paris')
    expect(plain).toContain('1h 48m')
    expect(plain).toContain('Train')
    expect(plain).not.toContain('Gare')
    const stations = page(twoCities({ from_station: "Paris Gare de l'Est", to_station: 'Strasbourg' }))
    expect(stations).toContain('Gare de l')
    expect(modeKind('High-speed train (TGV)')).toBe('train')
    expect(modeKind('باص')).toBe('bus')
    expect(modeKind('Flight')).toBe('flight')
    expect(modeKind(null)).toBe('other')
    const train = { from_city: 'Paris', to_city: 'Strasbourg', mode: info('Train'), duration: info('2h'), price_per_person: { amount_sar: null, status: 'Not available' as const, evidence: [{ source_id: 7, quote: 'from 30 EUR' }] } }
    // The cited page first; without one, a route planner. Never a web search.
    expect(transferLink(train, [{ id: 7, title: 'Trainline', url: 'https://www.thetrainline.com/x' }])).toEqual({ url: 'https://www.thetrainline.com/x', kind: 'source' })
    const planner = transferLink({ ...train, price_per_person: { ...train.price_per_person, evidence: [] } }, [])
    expect(planner).toEqual({ url: 'https://www.rome2rio.com/map/Paris/Strasbourg', kind: 'planner' })
    expect(planner.url).not.toContain('google')
  })
  it('shows a whole Arabic page with no English beyond flight numbers and unknown names', () => {
    localStorage.setItem('rihla-language', 'ar')
    const gulf = flights({ legs: [{ ...leg('outbound', null), airline: info('Gulf Air'), flight_number: 'GF 162', departure_time: '2026-12-13T06:50:00', arrival_time: '2026-12-13T08:10:00', stops: 0, duration: info('1h 25m') }, { ...leg('return', null), airline: info('Gulf Air'), duration: info('1h 25m') }], duration: info('1h 25m') })
    const html = page({ ...twoCities({ from_station: "Paris Gare de l'Est", to_station: 'Strasbourg' }), title: 'رحلة', destination: 'France', flights: [gulf], sources: [] })
    const visible = html.replace(/<(style|script)[^>]*>.*?<\/\1>/gs, '').replace(/<[^>]+>/g, ' ').replace(/GF \d+/g, ' ').replace(/Booking(\.com)?/g, ' ').replace(/Mock Hotel/g, ' ').replace(/Rihla/g, ' ')
    expect(visible.match(/[A-Za-z]{2,}/g) ?? []).toEqual([])
    expect(html).toContain('الرياض')
    expect(html).toContain('٠٦:٥٠')
  })
  it('keeps unknown names isolated, and everything English on an English page', () => {
    const html = page(proposal({ cities: [{ ...stay, city: 'Nowhere', hotel_name: info('Hotel Mock') }] }))
    expect(html).toContain('<bdi>Hotel Mock</bdi>')
    expect(html).not.toMatch(/[\u0600-\u06FF]/)
    expect(durationLabel('2h 5m', 'ar', 'ar-SA-u-ca-gregory')).toContain('س')
    expect(durationLabel('about five hours', 'ar', 'ar-SA-u-ca-gregory')).toBe('about five hours')
  })
  it('honours reduced motion in the styles, and eases numbers', () => {
    expect(countUpValue(900, 1000, 0)).toBe(900)
    expect(countUpValue(900, 1000, 1)).toBe(1000)
    expect(countUpValue(900, 1000, 0.5)).toBeGreaterThan(950)
    expect(detailsCss).toContain('@media (prefers-reduced-motion: reduce)')
    expect(detailsCss).toMatch(/prefers-reduced-motion: reduce\) \{\s*:is\(\.proposal-details,\.proposals-panel\)/)
  })
  it('keeps every style and the font under its own pages', () => {
    const rules = detailsCss.split('\n').map((line) => line.trim()).filter((line) => /^[^@/}].*\{/.test(line) && !/^(from|to|\d+%)/.test(line) && !line.startsWith('@'))
    expect(rules.length).toBeGreaterThan(50)
    expect(rules.filter((line) => !/details-|proposal|ai-status/.test(line.split('{')[0]))).toEqual([])
    expect(detailsCss).toContain(".proposal-details, .proposals-panel { font-family:'IBM Plex Sans Arabic'")
  })
  it('makes cards rise and photos zoom on hover, inside a hover-only rule', () => {
    expect(detailsCss).toMatch(/@media \(hover:hover\) \{[\s\S]*translateY\(-4px\) scale\(1\.03\)/)
    expect(detailsCss).toMatch(/\.details-photo img \{ transform:scale\(1\.08\)/)
    expect(detailsCss).toMatch(/\.details-city:active/)
  })
  it('shows a working status with changing words in both languages', () => {
    const html = pure(<AiStatus messages={checkMessages} />)
    expect(html).toContain('role="status"')
    expect(html).toContain('ai-status-spark')
    expect(html).toContain('<svg')
    expect(html).toContain('Reviewing the trip…')
    expect(nextStatusIndex(0, 4)).toBe(1)
    expect(nextStatusIndex(3, 4)).toBe(3)
    expect(pure(<RefreshView busy result={null} error="" waitMinutes={0} onRefresh={() => undefined} />)).toContain('ai-status')
    expect(pure(<RefreshView busy result={null} error="" waitMinutes={0} onRefresh={() => undefined} />)).not.toContain('details-spinner')
    localStorage.setItem('rihla-language', 'ar')
    expect(pure(<AiStatus messages={checkMessages} />)).toContain('يحلل الرحلة…')
    expect(pure(<AiStatus messages={generateMessages} />)).toContain('يقرأ تفضيلات المجموعة…')
  })
  it('brings the heading in word by word, and reads it as one title', () => {
    const html = page(proposal({ title: 'Three word title' }))
    expect(count(html, 'details-word')).toBe(3)
    expect(html).toContain('aria-label="Three word title"')
    expect(detailsCss).toContain('details-zoom-out')
  })
  it('empties the timer ring as the link runs out', () => {
    const at = '2026-11-01T10:00:00Z'
    const base = new Date(at).getTime()
    expect(linkFractionLeft(at, 10, base)).toBe(1)
    expect(linkFractionLeft(at, 10, base + 5 * 60000)).toBe(0.5)
    expect(linkFractionLeft(at, 10, base + 11 * 60000)).toBe(0)
    expect(pure(<TimerRing fraction={0.5} />)).toContain('stroke-dashoffset="50"')
    expect(pure(<BookResultView result={checked({ checked_at: at })} now={base} />)).toContain('details-ring')
  })
  it('shows the progress of the booking steps', () => {
    const html = pure(<BookSteps busy result={null} />)
    expect(html).toContain('role="progressbar"')
    expect(html).toContain('aria-valuenow="1"')
    expect(pure(<BookSteps busy={false} result={checked()} />)).toContain('aria-valuenow="3"')
  })
  it('offers real activity research for a proposal without suggestions', () => {
    expect(pure(<ActivitiesSection proposal={proposal()} />)).toContain('Find activity suggestions')
  })
  it('makes the photo open nothing, with its credit in a tooltip on the corner icon', () => {
    const image = { url: 'https://upload.wikimedia.org/a.jpg', source_url: 'https://commons.wikimedia.org/a', artist: 'A. Person', license: 'CC BY-SA 4.0' }
    const html = pure(<PlacePhoto image={image} place="Cairo" />)
    expect(html).not.toContain('<a ')
    expect(html).not.toContain('commons.wikimedia.org')
    expect(html).toContain('aria-label="Photo source and licence"')
    expect(html).toContain('role="tooltip"')
    expect(html).toContain('A. Person')
    expect(detailsCss).toMatch(/\.details-photo-credit \{[^}]*visibility:hidden/)
    expect(html).toContain('is-loading')
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
    expect(arabic).toContain('سعر تقريبي. هذا سعر التذكرة الأساسي')
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
  it('shows the Flexible adjustment as a trade-off (US-15) and a general note after changes', () => {
    const html = page(proposal({ flexible_adjustments: [{ category: 'flights', explanation: 'A stop was added.' }] }), false, 'p1', { needs_regeneration: true })
    expect(html.indexOf('A stop was added.')).toBeGreaterThan(html.indexOf('Trade-offs'))
    expect(html).toContain('details changed after these proposals')
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
