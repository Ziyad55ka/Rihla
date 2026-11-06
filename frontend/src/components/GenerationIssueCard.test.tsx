import { renderToStaticMarkup } from 'react-dom/server'
import { expect, it, vi } from 'vitest'
import { LanguageProvider } from '../lib/language'
import type { GenerationIssue } from '../types/proposal'
import { GenerationIssueCard } from './GenerationIssueCard'

vi.mock('../lib/supabase', () => ({ supabase: null, supabaseConfiguration: { state: 'not-configured', message: '' } }))

it('offers other dates and a Google Flights link when no flights were found', () => {
  const url = 'https://www.google.com/travel/flights?q=Flights+to+Doha+on+2026-12-01+through+2026-12-08'
  const issue: GenerationIssue = {
    code: 'no_flights', message: 'No bookable flights were found to Doha.', places: ['Doha'],
    suggestions: [
      { action: 'edit_dates', kind: 'try_other_dates', text: '', params: {} },
      { action: 'open_link', kind: 'search_google_flights', text: '', params: { place: 'Doha', url } },
      // A link that is not https must never be offered.
      { action: 'open_link', kind: 'search_google_flights', text: '', params: { place: 'Doha', url: 'javascript:alert(1)' } },
    ],
  }
  const html = renderToStaticMarkup(<LanguageProvider><GenerationIssueCard issue={issue} isAdmin={false} onAction={() => undefined} /></LanguageProvider>)
  expect(html).toContain('Try other travel dates')
  expect(html).toContain('Search Google Flights for Doha yourself')
  expect(html).toContain(`href="${url.replaceAll('&', '&amp;')}"`)
  expect(html).toContain('target="_blank"')
  expect(html).not.toContain('javascript:')
  expect(html.match(/Open Google Flights/g)).toHaveLength(1)
})
