import { describe, expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { LanguageProvider } from '../lib/language'
import { elapsedLabel } from '../lib/aiStatus'
import { generationIssue } from '../lib/proposals'
import { GenerationIssueCard } from './GenerationIssueCard'
import { GenerationProgressView } from './GenerationProgress'
import { ProposalsView } from './ProposalsPanel'
import type { GenerationIssue, GenerationProgress, StoredProposals } from '../types/proposal'

vi.mock('../lib/supabase', () => ({ supabase: null, supabaseConfiguration: { state: 'not-configured', message: '' } }))

const option = { title: 'Trip', title_ar: null, destination_ar: null, start_date: '2026-11-21', end_date: '2026-11-25', hotel_name: null, hotel_price_per_night_sar: null, hotel_source: null, date_shift_days: 0 }
const progress: GenerationProgress = {
  stage: 'researching', started_at: '2026-11-03T10:00:00Z', updated_at: '2026-11-03T10:00:30Z', target: 3, ready: 1,
  options: [
    { ...option, key: 'doha', destination: 'Doha', status: 'ready', date_shift_days: 1, hotel_name: 'Souq Hotel', hotel_price_per_night_sar: '420.00', hotel_source: 'Booking.com via Google' },
    { ...option, key: 'nowhere', destination: 'Nowhere', status: 'no_flights' },
  ],
}
const issue: GenerationIssue = {
  code: 'no_flights', message: 'x', places: ['Doha', 'Paris'],
  suggestions: [
    { action: 'edit_dates', kind: 'dates_too_soon', text: 'x', params: { earliest: '2026-11-06', days: '3' } },
    { action: 'edit_preferences', kind: 'add_destination', text: 'x', params: {} },
    { action: 'retry', kind: 'retry_later', text: 'x', params: {} },
  ],
}

const wrap = (node: React.ReactNode) => renderToStaticMarkup(<LanguageProvider>{node}</LanguageProvider>)

describe('GenerationProgressView', () => {
  it('marks finished steps, the current step and the elapsed time', () => {
    const html = wrap(<GenerationProgressView progress={progress} elapsedSeconds={65} />)
    expect(html).toContain('aria-current="step"')
    expect(html).toContain('Finding hotels and trip details')
    expect(html.match(/generation-step--done/g)).toHaveLength(2)
    expect(html).toContain('Elapsed 1:05')
    expect(html).toContain('1 of 3 proposals ready')
  })
  it('shows each destination, moved dates, the hotel price and places without flights', () => {
    const html = wrap(<GenerationProgressView progress={progress} elapsedSeconds={0} />)
    expect(html).toContain('Departure moved 1 day later to find flights')
    expect(html).toContain('Souq Hotel: 420 SAR a night')
    expect(html).toContain('No bookable flights. Trying another place.')
  })
  it('starts at the first step before any progress arrives', () => {
    expect(wrap(<GenerationProgressView progress={null} elapsedSeconds={0} />)).toContain('aria-current="step"')
  })
})

describe('GenerationIssueCard', () => {
  it('names the places tried and offers a button for each fix', () => {
    const html = wrap(<GenerationIssueCard issue={issue} isAdmin onAction={() => undefined} />)
    expect(html).toContain('role="alert"')
    expect(html).toContain('Doha, Paris')
    expect(html).toContain('at least 3 days from today')
    expect(html).toContain('Change dates')
    expect(html).toContain('Open preferences')
    expect(html).toContain('Try again')
  })
  it('does not offer members a generate button', () => {
    expect(wrap(<GenerationIssueCard issue={issue} isAdmin={false} onAction={() => undefined} />)).not.toContain('Try again')
  })
})

describe('ProposalsView with progress and issues', () => {
  const empty: StoredProposals = { version: null, complete: false, generated_at: null, generating: false, needs_regeneration: false, proposals: [] }
  const clear = { conflicts: [], own_review: [], can_generate: true }
  it('shows live steps while generating and the issue card instead of a bare error', () => {
    const busy = wrap(<ProposalsView isAdmin conflicts={clear} stored={empty} busy error="" notice="" onGenerate={() => undefined} progress={progress} />)
    expect(busy).toContain('Building your proposals')
    const failed = wrap(<ProposalsView isAdmin conflicts={clear} stored={empty} busy={false} error="raw" notice="" onGenerate={() => undefined} issue={issue} />)
    expect(failed).toContain('No bookable flights for these dates')
    expect(failed).not.toContain('>raw<')
  })
})

describe('helpers', () => {
  it('formats elapsed time', () => {
    expect(elapsedLabel(5, 'en-US')).toBe('0:05')
    expect(elapsedLabel(125, 'en-US')).toBe('2:05')
  })
  it('reads only well-formed issue details', () => {
    expect(generationIssue('text')).toBeNull()
    expect(generationIssue({ message: 'x' })).toBeNull()
    const parsed = generationIssue({ code: 'no_flights', message: 'm', suggestions: [{ action: 'retry', kind: 'retry_later', text: 't' }, 'bad'] })
    expect(parsed?.suggestions).toEqual([{ action: 'retry', kind: 'retry_later', text: 't', params: {} }])
    expect(parsed?.places).toEqual([])
  })
})
