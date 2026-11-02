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
    for (const text of ['Museum visit', 'City walk', 'Description', 'Location', 'Duration', 'Event date', 'Not available', 'Unconfirmed', '85.50', '0.00']) expect(html).toContain(text)
    expect(html.match(/type="checkbox"/g)).toHaveLength(4)
    expect(html).toContain('Restaurants')
    expect(html).toContain('Attractions')
    expect(html).toContain('Image not available')
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
})
