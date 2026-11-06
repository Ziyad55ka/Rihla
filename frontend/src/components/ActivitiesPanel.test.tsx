import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'
import { LanguageProvider } from '../lib/language'
import { ActivitiesPanel, ActivityCard, DailyActivityPlan } from './ActivitiesPanel'
import { modeFor } from '../lib/activities'
import data from '../test-fixtures/activities.json'
import type { Proposal, ProposalSet } from '../types/proposal'

const proposal = (data as ProposalSet).proposals[0]
const render = (p: Proposal) => renderToStaticMarkup(<LanguageProvider><ActivitiesPanel proposal={p} /></LanguageProvider>)
const renderCards = (p: Proposal) => renderToStaticMarkup(<LanguageProvider>{p.cities.flatMap(city => city.activities!.map((activity,index) => <ActivityCard key={activity.id} activity={activity} index={index} city={city} proposal={p} selected={false} disabled={false} onToggle={() => {}} />))}</LanguageProvider>)

describe('activity cards', () => {
  it('uses the chosen language for the landmark name and description', () => {
    const fixture = structuredClone(proposal)
    Object.assign(fixture.cities[0].activities![0], { name_ar: 'متحف برادو', name_en: 'Prado Museum', description_ar: 'متحف فني في مدريد.', description_en: 'An art museum in Madrid.' })
    expect(render(fixture)).toContain('An art museum in Madrid.')
    vi.stubGlobal('localStorage', { getItem: () => 'ar' })
    try {
      const html = render(fixture)
      expect(html).toContain('متحف فني في مدريد.')
      expect(html).not.toContain('An art museum in Madrid.')
      expect(html).not.toContain('>Sourced<')
    } finally { vi.unstubAllGlobals() }
  })
  it('shows details, missing information, zero prices and trust labels', () => {
    const html = renderCards(proposal)
    for (const text of ['Museum visit', 'City walk', 'Description', 'Location', 'Duration', 'Event date', 'Not available', 'Rough estimate · may change with the season', 'Usually free']) expect(html).toContain(text)
    expect(html).not.toContain('>Sourced<')
    // A price with no source reads as a rough guide, rounded.
    expect(html).toMatch(/About (SAR|ر\.س\.)\s?86/)
    expect(html.match(/type="checkbox"/g)).toHaveLength(4)
  })
  it('hides a suggestion with no photo, but keeps a saved choice', () => {
    const fixture = structuredClone(proposal)
    fixture.cities[0].activities![0].image_url = null
    expect(renderCards(fixture)).not.toContain('Museum visit')
    const city = fixture.cities[0], activity = city.activities![0]
    const html = renderToStaticMarkup(<LanguageProvider><ActivityCard activity={activity} index={0} city={city} proposal={fixture} selected disabled={false} onToggle={() => undefined} /></LanguageProvider>)
    expect(html).toContain('Museum visit')
    expect(html).toContain('Image not available')
  })
  it('shows a free photo with its credit when one was found', () => {
    const fixture = structuredClone(proposal)
    fixture.cities[0].activities![0].image = { url: 'https://upload.wikimedia.org/a.jpg', source_url: 'https://commons.wikimedia.org/wiki/File:A.jpg', artist: 'A. Photographer', license: 'CC BY-SA 4.0' }
    const html = render(fixture)
    expect(html).toContain('https://upload.wikimedia.org/a.jpg')
    expect(html).toContain('CC BY-SA 4.0')
  })
  it('shows a clear empty state for old proposals', () => {
    expect(render({ ...proposal, cities: proposal.cities.map(city => ({ ...city, activities: undefined })) })).toContain('No suggestions in this category for this city.')
  })
  it('does not render unsafe booking links from untrusted data', () => {
    const unsafe = structuredClone(proposal)
    unsafe.cities[0].activities![0].booking_url = 'javascript:alert(1)'
    expect(render(unsafe)).not.toContain('href="javascript:')
  })
  it('renders a supplied image and labels an unsuitable dated event', () => {
    const fixture = structuredClone(proposal)
    fixture.cities[0].activities![0].image_url = 'https://example.test/museum.jpg'
    fixture.cities[0].activities![2].scheduled_date.value = '2027-01-01'
    const html = renderCards(fixture)
    expect(html).toContain('src="https://example.test/museum.jpg"')
    expect(html).toContain('Outside this city stay')
  })
  it('shows which group interests a suggestion matches, and nothing on older ones', () => {
    const fixture = structuredClone(proposal)
    fixture.cities[0].activities![0].fits = ['museums_history', 'culture_arts']
    const html = render(fixture)
    expect(html).toContain('Matches the group’s interests:')
    expect(html).toContain('Museums and history')
    expect(html.match(/class="activity-fit"/g)).toHaveLength(2)
    expect(render(proposal)).not.toContain('Matches the group’s interests:')
  })
})

describe('activity choice steps', () => {
  it('starts with sights and provides separate next steps without rendering the whole catalogue', () => {
    const html = render(proposal)
    expect(html).toContain('Activity selection steps')
    expect(html).toContain('aria-current="step"')
    expect(html).toContain('Next: Activities and events')
    expect(html).toContain('Museum visit')
    expect(html).not.toContain('Local restaurant')
    expect(html).not.toContain('Evening event')
    expect(html.match(/type="checkbox"/g)).toHaveLength(1)
  })
  it('reviews each selected visit once under a day and shows room for free time', () => {
    const ids = proposal.cities[0].activities!.map(a => a.id)
    const html = renderToStaticMarkup(<LanguageProvider><DailyActivityPlan proposal={proposal} ids={ids} /></LanguageProvider>)
    expect(html.match(/MOCK: Museum visit/g)).toHaveLength(1)
    expect(html).toContain('Dated event')
    expect(html).toContain('Free time')
  })
  it('opens on the choice, then the saved list, then the locked list', () => {
    expect(modeFor(0, false)).toBe('choose')
    expect(modeFor(3, false)).toBe('review')
    expect(modeFor(3, true)).toBe('confirmed')
    expect(modeFor(3, true, true)).toBe('review')
    expect(modeFor(0, true)).toBe('confirmed')
    expect(modeFor(0, false, true)).toBe('review')
  })
})
