import { renderToStaticMarkup } from 'react-dom/server'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { FlightPriceReview } from './FlightPriceReview'
import { LanguageProvider } from '../lib/language'
import data from '../test-fixtures/activities.json'
import type { ProposalSet } from '../types/proposal'

afterEach(() => vi.useRealTimers())
describe('flight review message', () => {
  it('shows a review countdown without promising held inventory or automatic refresh', () => {
    vi.useFakeTimers(); vi.setSystemTime(new Date('2026-11-06T09:00:00Z'))
    const route = { ...structuredClone((data as ProposalSet).proposals[0].flights[0]), schedule_confirmed: true, group_availability: 'available' as const, priced_at: '2026-11-06T09:00:00Z' }
    route.price_per_person.status = 'Sourced'
    const html = renderToStaticMarkup(<LanguageProvider><FlightPriceReview routes={[route]} /></LanguageProvider>)
    expect(html).toContain('15:00')
    expect(html).toContain('role="timer"')
    expect(html).toContain('aria-live="off"')
    expect(html).toContain('not a reservation')
    expect(html).not.toContain('Finish booking now')
  })
  it('does not show a numeric timer when no fare can be checked', () => {
    const html = renderToStaticMarkup(<LanguageProvider><FlightPriceReview routes={[]} compact /></LanguageProvider>)
    expect(html).toContain('Check flight prices before choosing')
    expect(html).not.toContain('role="timer"')
  })
})
