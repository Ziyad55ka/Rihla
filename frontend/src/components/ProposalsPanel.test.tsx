import { describe, expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { LanguageProvider } from '../lib/language'
import { ProposalsView } from './ProposalsPanel'
import type { GroupConflicts, StoredProposals } from '../types/proposal'

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
