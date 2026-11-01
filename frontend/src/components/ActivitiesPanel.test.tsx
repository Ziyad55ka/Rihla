import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { LanguageProvider } from '../lib/language'
import { ActivitiesPanel } from './ActivitiesPanel'
import data from '../data/activities.mock.json'
import type { Proposal, ProposalSet } from '../types/proposal'

const proposal = (data as ProposalSet).proposals[0]
const render = (p: Proposal) => renderToStaticMarkup(<LanguageProvider><ActivitiesPanel proposal={p} /></LanguageProvider>)

describe('activity cards', () => {
  it('shows details, missing information, zero prices and trust labels', () => {
    const html = render(proposal)
    for (const text of ['Museum visit', 'City walk', 'Description', 'Location', 'Duration', 'Event date', 'Not available', 'Unconfirmed', '85.50', '0.00']) expect(html).toContain(text)
    expect(html.match(/type="checkbox"/g)).toHaveLength(3)
  })
  it('shows a clear empty state for old proposals', () => {
    expect(render({ ...proposal, cities: proposal.cities.map(city => ({ ...city, activities: undefined })) })).toContain('No activities available for this city.')
  })
  it('does not render unsafe booking links from untrusted data', () => {
    const unsafe = structuredClone(proposal)
    unsafe.cities[0].activities![0].booking_url = 'javascript:alert(1)'
    expect(render(unsafe)).not.toContain('href="javascript:')
  })
})
