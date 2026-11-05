import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { LanguageProvider } from '../../lib/language'
import { ProposalDetailView } from '../../pages/ProposalDetailPage'
import type { CostAmount, CostScenario, Proposal, ProposalCosts, SarPrice, StoredProposals } from '../../types/proposal'

vi.mock('../../lib/supabase', () => ({ supabase: null, supabaseConfiguration: { state: 'not-configured', message: '' } }))

const evidence = [{ source_id: 1, quote: 'A fictional quote.' }]
const price = (amount: string, status: SarPrice['status'] = 'Estimated'): SarPrice => ({ amount_sar: amount, status, evidence })
const info = (value: string) => ({ value, status: 'Sourced' as const, evidence })
const amount = (value: string | null, status: CostAmount['status'] = 'Estimated', partial = false): CostAmount => ({ amount_sar: value, status, partial })

const proposal = (extra: Partial<Proposal> = {}): Proposal => ({
  id: 'p1', trip_id: 't1', version: 1, option_number: 1, title: 'Main title', destination: 'Egypt', start_date: '2026-12-13', end_date: '2026-12-17',
  cities: [{ order: 1, city: 'Cairo', nights: 4, hotel_name: info('Mock Hotel'), hotel_price_per_night: price('450'), booking_url: null }],
  flights: [], intercity_transport: [], flexible_adjustments: [], budget_status: 'includes_unconfirmed',
  sources: [
    { id: 1, title: 'Cairo hotel guide', url: 'https://www.guide.example/cairo', kind: 'ideas', retrieved_at: '2026-11-02T09:30:00Z' },
    { id: 2, title: 'Internal fare note', url: 'https://fares.example/x', kind: 'flight' },
  ],
  compatibility: [
    { topic: 'destinations', importance: 'Essential', status: 'met' },
    { topic: 'accommodation', importance: 'Essential', status: 'unverified' },
    { topic: 'interests', importance: 'Flexible', status: 'unmet' },
    { topic: 'dates', importance: 'Required', status: 'met' },
    { topic: 'budget', importance: 'Required', status: 'unverified' },
  ],
  ...extra,
})

const scenario = (extra: Partial<CostScenario> = {}): CostScenario => ({
  rooms: 'single',
  lines: [
    { category: 'flights', per_person: amount('1200.00'), counted: true },
    { category: 'accommodation', per_person: amount('1800.00'), counted: true },
    { category: 'activities', per_person: amount(null, 'Not available'), counted: false },
    { category: 'meals', per_person: amount('750.00', 'Unconfirmed'), counted: true },
  ],
  per_person_total: amount('3750.00', 'Unconfirmed'),
  group_total: amount('11250.00', 'Unconfirmed'),
  own_budget: 'within',
  over_by_sar: null,
  ...extra,
})

const costs = (extra: Partial<ProposalCosts> = {}): ProposalCosts => ({
  proposal_id: 'p1', days: 5, nights: 4,
  scenarios: [scenario(), scenario({ rooms: 'shared', per_person_total: amount('3150.00', 'Unconfirmed') })],
  assumptions: ['flights_own_city', 'rooms_single', 'rooms_shared', 'meals_allowance', 'activities_not_included', 'group_total_all_cities', 'prices_may_change'],
  ...extra,
})

function page(item = proposal(), stored: Partial<StoredProposals> = {}) {
  const data: StoredProposals = { version: 1, complete: true, generated_at: '2026-11-02T08:00:00Z', generating: false, needs_regeneration: false, proposals: [item], costs: [costs()], ...stored }
  return renderToStaticMarkup(<LanguageProvider><ProposalDetailView stored={data} proposalId="p1" isAdmin={false} onBack={() => undefined} /></LanguageProvider>)
}

const saved = new Map<string, string>()
beforeEach(() => {
  saved.clear()
  vi.stubGlobal('localStorage', { getItem: (key: string) => saved.get(key) ?? null, setItem: (key: string, value: string) => saved.set(key, value) })
})

describe('US-13 costs and budget', () => {
  it('lists every cost category, per person and for the group', () => {
    const html = page()
    for (const text of ['Costs and budget', 'Flights', 'Accommodation', 'Selected activities', 'Meals and other expenses', 'Total per person', 'Total for the group']) expect(html).toContain(text)
    expect(html).toContain('3,750')
    expect(html).toContain('11,250')
    expect(html).toContain('Not added to the total yet')
  })

  it('explains the assumptions and offers both room plans', () => {
    const html = page()
    expect(html).toContain('How this is calculated')
    expect(html).toContain('Meals and small expenses use a general daily allowance per person.')
    expect(html).toContain('One person per room')
    expect(html).toContain('Two people per room')
  })

  it('warns a member who is over their own budget, without showing the budget', () => {
    const html = page(proposal(), { costs: [costs({ scenarios: [scenario({ own_budget: 'over', over_by_sar: '750.00' })] })] })
    expect(html).toContain('Over your budget by 750 SAR')
    expect(html).toContain('role="alert"')
    expect(html).not.toContain('One person per room</label>')
  })

  it('says when prices are uncertain or missing', () => {
    const uncertain = scenario({ own_budget: 'unconfirmed', per_person_total: amount('2950.00', 'Unconfirmed', true) })
    const html = page(proposal(), { costs: [costs({ scenarios: [uncertain] })] })
    expect(html).toContain('some prices are unconfirmed or missing')
    expect(html).toContain('Some prices are missing, so the real cost is higher.')
  })

  it('still renders when the backend sent no costs', () => {
    expect(page(proposal(), { costs: undefined })).toContain('The cost breakdown is not available right now.')
  })
})

describe('US-15 match and trade-offs', () => {
  it('names Essential requirements that are not verified', () => {
    const html = page()
    expect(html).toContain('How it matches the group')
    expect(html).toContain('Check these Essential requirements yourself before deciding: Accommodation (Not verified)')
    expect(html).toContain('See each check (2 of 5 met)')
  })

  it('describes trade-offs and says no score is used', () => {
    const html = page(proposal({ flexible_adjustments: [{ category: 'interests', explanation: 'A calmer city is suggested.' }] }))
    expect(html).toContain('Trade-offs')
    expect(html).toContain('A calmer city is suggested.')
    expect(html).toContain('does not give proposals a score')
  })

  it('explains older proposals without match details', () => {
    expect(page(proposal({ compatibility: undefined }))).toContain('generated before match details were added')
  })

  it('shows the fit score with its criteria: least-satisfied member and group average (US-15-AC03)', () => {
    const html = page(proposal({ fit: { group_percent: 88, least_satisfied_percent: 71, member_count: 4 } }))
    expect(html).toContain('Fit score')
    expect(html).toContain('AI can make mistakes')
    expect(html).toContain('Least-satisfied member')
    expect(html).toContain('71%')
    expect(html).toContain('Group average')
    expect(html).toContain('88%')
    expect(html).toContain('Essential ones count three times')
    expect(html).not.toContain('does not give proposals a score')
  })
})

describe('US-14 sources and reliability', () => {
  it('lists sources with their check time and hides internal fare notes', () => {
    const html = page()
    expect(html).toContain('Cairo hotel guide')
    expect(html).toContain('guide.example')
    expect(html).toContain('Checked ')
    expect(html).not.toContain('Internal fare note')
    expect(html).toContain('rel="noopener noreferrer"')
  })

  it('explains every reliability label', () => {
    const html = page()
    for (const text of ['Not a guaranteed price', 'Check it before booking.', 'It is not counted as free']) expect(html).toContain(text)
  })

  it('never turns an unsafe address into a link', () => {
    const html = page(proposal({ sources: [{ id: 1, title: 'Bad', url: 'javascript:alert(1)', kind: 'ideas' }] }))
    expect(html).not.toContain('href="javascript:')
  })
})

describe('Arabic', () => {
  it('translates every label in the three sections, including single words', () => {
    localStorage.setItem('rihla-language', 'ar')
    const html = page(proposal({ flexible_adjustments: [] }))
    const start = html.lastIndexOf('<section', html.indexOf('id="details-costs"'))
    const own = html.slice(start).replace(/<[^>]+>/g, ' ')
    // Only the sample data (hotel name, source title and site) may stay in English.
    const english = own.match(/[A-Za-z]{3,}/g)?.filter((word) => !['Cairo', 'hotel', 'guide', 'example'].includes(word)) ?? []
    expect(english).toEqual([])
  })
})
