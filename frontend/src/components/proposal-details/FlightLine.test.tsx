import { renderToStaticMarkup } from 'react-dom/server'
import { expect, it, vi } from 'vitest'
import { LanguageProvider } from '../../lib/language'
import type { FlightLeg } from '../../types/proposal'
import { FlightLine } from './FlightLine'

vi.mock('../../lib/supabase', () => ({ supabase: null, supabaseConfiguration: { state: 'not-configured', message: '' } }))

it('shows the local arrival date when an overnight flight arrives next day', () => {
  const field = { value: null, status: 'Not available' as const, evidence: [] }
  const leg: FlightLeg = { direction: 'return', date: '2027-01-16', airline: field, duration: field,
    price: { amount_sar: null, status: 'Not available', evidence: [] }, booking_url: null,
    departure_time: '2027-01-16T22:35:00', arrival_time: '2027-01-17T04:10:00' }
  const html = renderToStaticMarkup(<LanguageProvider><FlightLine leg={leg} from="Doha" to="Jeddah" /></LanguageProvider>)
  expect(html).toContain('Arrival date:')
  expect(html).toContain('Jan 17, 2027')
})
