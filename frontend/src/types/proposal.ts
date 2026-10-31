// Mirrors backend/app/schemas/proposals.py. Mock data: docs/examples/proposals.mock.json.
export type InfoStatus = 'Confirmed' | 'Estimated' | 'Unconfirmed' | 'Not available'
export type PriceStatus = Exclude<InfoStatus, 'Confirmed'>
export type PreferenceCategory = 'destinations' | 'interests' | 'flights' | 'accommodation'

export interface Evidence {
  source_id: number
  quote: string
}

export interface InfoField {
  value: string | null
  status: InfoStatus
  evidence: Evidence[]
}

export interface SarPrice {
  // Serialized from a decimal, so it arrives as a string.
  amount_sar: string | null
  status: PriceStatus
  evidence: Evidence[]
}

export interface ProposalSource {
  id: number
  title: string
  url: string
}

export interface Flights {
  origin: string
  airline: InfoField
  duration: InfoField
  price_per_person: SarPrice
}

export interface CityStay {
  order: number
  city: string
  nights: number
  hotel_name: InfoField
  hotel_price_per_night: SarPrice
}

export interface IntercityTransfer {
  from_city: string
  to_city: string
  mode: InfoField
  duration: InfoField
  price_per_person: SarPrice
}

export interface FlexibleAdjustment {
  category: PreferenceCategory
  explanation: string
}

export interface Proposal {
  id: string
  trip_id: string
  version: number
  option_number: 1 | 2 | 3
  title: string
  destination: string
  start_date: string
  end_date: string
  cities: CityStay[]
  // Holds only the signed-in member's departure city under the current privacy rule.
  flights: Flights[]
  intercity_transport: IntercityTransfer[]
  flexible_adjustments: FlexibleAdjustment[]
  sources: ProposalSource[]
}

export interface ProposalSet {
  proposals: Proposal[]
}
