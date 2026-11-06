import { describe, expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { LanguageProvider } from '../lib/language'
import { ProposalsView } from './ProposalsPanel'
import type { GroupConflicts, ProposalSet, StoredProposals } from '../types/proposal'
import data from '../test-fixtures/activities.json'

vi.mock('../lib/supabase', () => ({ supabase: null, supabaseConfiguration: { state: 'not-configured', message: '' } }))

const clear: GroupConflicts = { conflicts: [], own_review: [], can_generate: true }
const conflicted: GroupConflicts = { conflicts: ['destinations'], own_review: ['destinations'], can_generate: false }
const empty: StoredProposals = { version: null, complete: false, generated_at: null, generating: false, needs_regeneration: false, proposals: [] }

function view(props: Partial<Parameters<typeof ProposalsView>[0]> = {}) {
  return renderToStaticMarkup(<LanguageProvider>
    <ProposalsView isAdmin conflicts={clear} stored={empty} busy={false} error="" notice="" onGenerate={() => undefined} {...props} />
  </LanguageProvider>)
}
const button = (html: string) => /<button[^>]*>/.exec(html)?.[0] ?? ''

describe('ProposalsView', () => {
  it('applies the provider retry deadline to the main button as well as Try again', () => {
    const future = new Date(Date.now() + 3600000).toISOString()
    const issue = { code: 'model_quota', message: 'Limit reached', places: [], min_departure_lead_days: 3, retry_after_hours: null, suggestions: [{ action: 'retry' as const, kind: 'retry_after' as const, text: '', params: { retry_at: future } }] }
    const html = view({ issue })
    expect(button(html)).toContain('disabled')
    expect(html.match(/disabled=""/g)).toHaveLength(2)
    const expired = { ...issue, suggestions: [{ ...issue.suggestions[0], params: { retry_at: '2020-01-01T00:00:00Z' } }] }
    expect(button(view({ issue: expired }))).not.toContain('disabled')
  })
  it('explains the estimate and exposes editing without bypassing readiness', () => {
    const html = view({ conflicts: conflicted, preferencesHref: '/trips/test/preferences' })
    expect(button(html)).toContain('disabled')
    expect(html).toContain('/trips/test/preferences')
    expect(html).toContain('Round-trip flights')
    expect(html).toContain('With missing prices clearly marked')
    expect(html).toContain('Activity choices are added to the estimate later')
  })
  it('shows partial per-person totals as incomplete rather than full trip prices', () => {
    const proposals = (data as ProposalSet).proposals
    const stored: StoredProposals = { ...empty, version: 1, proposals, costs: [{ proposal_id: proposals[0].id, days: 5, nights: 4, assumptions: [], scenarios: [{ rooms: 'single', lines: [], per_person_total: { amount_sar: '1234.50', status: 'Estimated', partial: true }, group_total: null, own_budget: 'unconfirmed', over_by_sar: null }] }] }
    const html = view({ stored })
    expect(html).toContain('Known subtotal per person')
    expect(html).toContain('1,234.50')
    expect(html).toContain('This is not the full trip cost.')
  })
  it('reminds that AI can make mistakes under the proposals only', () => {
    const proposals = (data as ProposalSet).proposals
    const shown: StoredProposals = { ...empty, version: 1, complete: true, proposals }
    expect(view({ stored: shown })).toContain('AI can make mistakes')
    expect(view()).not.toContain('AI can make mistakes')
  })
  it('enables the button for an administrator with no conflicts', () => {
    expect(button(view())).not.toContain('disabled')
  })
  it('keeps the button disabled while conflicts remain, or before they load', () => {
    expect(button(view({ conflicts: conflicted }))).toContain('disabled')
    expect(button(view({ conflicts: null }))).toContain('disabled')
  })
  it('disables the button while this or another request is generating', () => {
    expect(button(view({ busy: true }))).toContain('disabled')
    expect(button(view({ stored: { ...empty, generating: true } }))).toContain('disabled')
  })
  it('tells a member and the administrator when proposals need regenerating', () => {
    const stored = { ...empty, needs_regeneration: true }
    expect(view({ isAdmin: false, stored })).toContain('The administrator needs to generate them again')
    expect(view({ stored })).toContain('Generate them again to include the changes')
    expect(view({ isAdmin: false })).not.toContain('details changed')
  })
  it('does not repeat an old budget success or fit score after preferences change', () => {
    const proposals = structuredClone((data as ProposalSet).proposals)
    proposals[0].budget_status = 'within_group_budget'
    const html = view({ stored: { ...empty, version: 1, complete: true, proposals, needs_regeneration: true } })
    expect(html).toContain('Regenerate to recheck budget and preferences')
    expect(html).not.toContain('Within the group budget')
    expect(html).not.toContain('Fits everyone: at least')
  })
  it('shows members no button', () => {
    expect(view({ isAdmin: false })).not.toContain('<button')
  })
  it('shows every member the general conflict, and the review notice only when returned', () => {
    const withNotice = view({ isAdmin: false, conflicts: conflicted })
    expect(withNotice).toContain('required destinations conflict')
    expect(withNotice).toContain('review it in your preferences')
    const withoutNotice = view({ isAdmin: false, conflicts: { ...conflicted, own_review: [] } })
    expect(withoutNotice).toContain('required destinations conflict')
    expect(withoutNotice).not.toContain('review it in your preferences')
  })
})
