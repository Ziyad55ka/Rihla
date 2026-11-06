import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { LanguageProvider } from '../../lib/language'
import { ActivitiesSection } from './ActivitiesSection'
import data from '../../test-fixtures/activities.json'
import type { ProposalSet } from '../../types/proposal'

describe('partial activity source results', () => {
  it('preserves a source outage notice after saved activity data is reloaded', () => {
    const proposal = structuredClone((data as ProposalSet).proposals[0])
    proposal.cities[0].activities![0].research_notes = ['guide_search_unavailable', 'events_only']
    const html = renderToStaticMarkup(<LanguageProvider><ActivitiesSection proposal={proposal} /></LanguageProvider>)
    expect(html).toContain('Showing checked event listings only.')
    expect(html).toContain('Attraction and restaurant research is temporarily unavailable.')
    expect(html).toContain('Museum visit')
  })
  it('keeps guide suggestions when the structured event provider is unavailable', () => {
    const proposal = structuredClone((data as ProposalSet).proposals[0])
    proposal.cities[0].activities![0].research_notes = ['event_source_unavailable']
    const html = renderToStaticMarkup(<LanguageProvider><ActivitiesSection proposal={proposal} /></LanguageProvider>)
    expect(html).toContain('The event source could not be reached.')
    expect(html).toContain('Museum visit')
  })
})
