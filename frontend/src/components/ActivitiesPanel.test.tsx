import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { LanguageProvider } from '../lib/language'
import { ActivitiesPanel } from './ActivitiesPanel'
import data from '../test-fixtures/activities.json'
import type { Proposal, ProposalSet } from '../types/proposal'

const proposal = (data as ProposalSet).proposals[0]
const render = (p: Proposal) => renderToStaticMarkup(<LanguageProvider><ActivitiesPanel proposal={p} /></LanguageProvider>)

describe('activity cards', () => {
  it('shows details, missing information, zero prices and trust labels', () => {
    const html = render(proposal)
    for (const text of ['Museum visit', 'City walk', 'Description', 'Location', 'Duration', 'Event date', 'Not available', 'Unconfirmed', 'Rough estimate · may change with the season', '0.00']) expect(html).toContain(text)
    // A price with no source reads as a rough guide, rounded.
    expect(html).toMatch(/About (SAR|ر\.س\.)\s?86/)
    expect(html.match(/type="checkbox"/g)).toHaveLength(4)
    expect(html).toContain('Restaurants')
    expect(html).toContain('Attractions')
    // Grouped the way a visitor scans: sights, things to do, then where to eat.
    expect(html.indexOf('Top sights')).toBeLessThan(html.indexOf('Where to eat'))
    expect(html).toContain('Picked for your group')
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
    expect(render({ ...proposal, cities: proposal.cities.map(city => ({ ...city, activities: undefined })) })).toContain('No activities available for this city.')
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
    const html = render(fixture)
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
