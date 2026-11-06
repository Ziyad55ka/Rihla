import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'
import { LanguageProvider } from '../lib/language'
import type { SavedPreferences } from '../types/preferences'
import { PreferencesForm } from './PreferencesPanel'

vi.mock('../lib/supabase', () => ({ supabase: null, supabaseConfiguration: { state: 'not-configured', message: '' } }))

const initial: SavedPreferences = {
  departure_city: 'Riyadh', max_budget_sar: '4500.50', available_start: '2027-01-10', available_end: '2027-01-16',
  destinations: { value: 'Paris or Japan', importance: 'Flexible' },
  interests: { value: 'focus:landmarks; notes:accessible museums', importance: 'Essential' },
  flights: { value: 'Legacy flight wish', importance: 'Flexible' },
  accommodation: { value: 'Step-free hotel', importance: 'Essential' },
  currency: 'SAR', updated_at: '2026-11-05T12:00:00Z',
}
const form = () => renderToStaticMarkup(<LanguageProvider><PreferencesForm tripId="test-trip" initial={initial} onSaved={() => undefined} /></LanguageProvider>)

describe('preference entry flow', () => {
  it('puts the editable destination before discovery, limits and interests', () => {
    const html = form()
    const destination = html.indexOf('id="preference-destinations"')
    expect(destination).toBeGreaterThan(0)
    expect(destination).toBeLessThan(html.indexOf('Not sure where to go?'))
    expect(destination).toBeLessThan(html.indexOf('id="departure-city"'))
    expect(html.indexOf('id="departure-city"')).toBeLessThan(html.indexOf('id="interest-focus-label"'))
    expect(html).toContain('Paris or Japan')
  })
  it('retains required limits, saved notes and both importance choices', () => {
    const html = form()
    expect(html.match(/ required=""/g)).toHaveLength(4)
    for (const value of ['4500.50', '2027-01-10', '2027-01-16', 'accessible museums', 'Step-free hotel']) expect(html).toContain(value)
    expect(html.match(/aria-pressed="true">/g)?.length).toBeGreaterThan(1)
    expect(html).toContain('Must be respected.')
    expect(html).toContain('Flexible')
    expect(html).toContain('Essential')
    expect(html).not.toContain('Legacy flight wish')
  })
  it('does not invite saving an untouched form or imply automatic generation', () => {
    const html = form()
    expect(html).toMatch(/type="submit"[^>]*disabled/)
    expect(html).toContain('Save preferences')
    expect(html).not.toContain('Generate proposals')
  })
  it('shows exactly one choice per hotel class and clear 1,000-SAR adjustments', () => {
    const html = form()
    expect(html.match(/>3 stars</g)).toHaveLength(1)
    expect(html.match(/>4 stars</g)).toHaveLength(1)
    expect(html.match(/>5 stars</g)).toHaveLength(1)
    expect(html).toContain('Increase budget by 1,000 SAR')
    expect(html).not.toContain('step="0.01"')
    expect(html).not.toContain('To save more for activities, I also accept:')
  })
})
