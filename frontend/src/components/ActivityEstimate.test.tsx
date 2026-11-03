import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { LanguageProvider } from '../lib/language'
import { activityProposalEstimate } from '../lib/activities'
import { ActivityEstimate } from './ActivityEstimate'
import data from '../test-fixtures/activities.json'
import type { ProposalSet } from '../types/proposal'

const proposal = (data as ProposalSet).proposals[0]
describe('saved proposal cost presentation', () => {
  it('shows activity costs as part of the proposal total, with explicit assumptions', () => {
    const ids = [proposal.cities[0].activities![3].id]
    const html = renderToStaticMarkup(<LanguageProvider><ActivityEstimate estimate={activityProposalEstimate(proposal, ids)} dirty={false} /></LanguageProvider>)
    expect(html).toContain('3,065.00')
    expect(html).toContain('Saved activities and places')
    expect(html).toContain('One room per person')
  })
  it('labels partial estimates and unsaved changes clearly', () => {
    const ids = [proposal.cities[0].activities![2].id]
    const html = renderToStaticMarkup(<LanguageProvider><ActivityEstimate estimate={activityProposalEstimate(proposal, ids)} dirty /></LanguageProvider>)
    expect(html).toContain('At least')
    expect(html).toContain('Unavailable costs are not counted as zero')
    expect(html).toContain('Save your activity changes')
  })
})
