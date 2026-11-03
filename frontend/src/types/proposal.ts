/**
 * The proposal JSON returned by the API.
 *
 * Other copy: backend/app/schemas/proposals.py. Any change must be made in both files.
 * Team guide: docs/proposal-schema-handoff.md. Sample data: docs/examples/proposals.mock.json.
 */

/**
 * How far a value can be trusted.
 * - `Sourced`: a source states it. Has evidence.
 * - `Estimated`: approximate or converted. Has evidence.
 * - `Unconfirmed`: unclear or general knowledge. Evidence may be empty.
 * - `Not available`: unknown. The value is null and evidence is empty.
 */
export type InfoStatus = 'Sourced' | 'Estimated' | 'Unconfirmed' | 'Not available'
/** Same values as InfoStatus. Only a live flight fare can be `Sourced`. */
export type PriceStatus = InfoStatus
/** The preference a Flexible adjustment relates to. */
export type PreferenceCategory = 'destinations' | 'interests' | 'flights' | 'accommodation'

/**
 * Whether the group fits, never the budget behind that answer.
 * - `within_group_budget`: the total fits and every price has evidence.
 * - `includes_unconfirmed`: the known total fits, but a price is uncertain or missing.
 * - `over_group_budget`: the total does not fit. Such a proposal is rejected, not returned.
 */
export type BudgetStatus = 'within_group_budget' | 'includes_unconfirmed' | 'over_group_budget'

/**
 * How the flights are booked.
 * - `round_trip`: one booking for both directions.
 * - `split`: two separate bookings. The total is an estimate.
 * - `one_way`: outbound only. The return cost is not counted.
 */
export type TripType = 'round_trip' | 'split' | 'one_way'

/** The proof behind a value: which source said it, in its own words. */
export interface Evidence {
  /** The id of an entry in `Proposal.sources`. Example: `2`. */
  source_id: number
  /** A short quote from that source. Example: `"The flight takes about 5 hours."`. */
  quote: string
}

/** A text value with its trust level. */
export interface InfoField {
  /** The text to show, or null when `Not available`. Example: `"Saudia"`. */
  value: string | null
  /** See InfoStatus. Example: `"Sourced"`. */
  status: InfoStatus
  /** Present for `Sourced` and `Estimated`. May be empty for `Unconfirmed`. */
  evidence: Evidence[]
}

/** A price in Saudi riyals with its trust level. */
export interface SarPrice {
  /** Serialized from a decimal, so it arrives as a string or null. Example: `"1200.00"`. */
  amount_sar: string | null
  /** See PriceStatus. Example: `"Estimated"`. */
  status: PriceStatus
  /** Present for `Sourced` and `Estimated`. May be empty for `Unconfirmed`. */
  evidence: Evidence[]
}

/** A web page or booking link cited by Evidence. */
export interface ProposalSource {
  /** Unique within the proposal. Example: `1`. */
  id: number
  /** The page title. Example: `"Istanbul hotel guide"`. */
  title: string
  /** The page address. Example: `"https://example.com/istanbul"`. */
  url: string
  /** `booking`: an approved booking site. `ideas`: ideas only. `flight`: never listed. */
  kind?: 'booking' | 'ideas' | 'flight' | null
  /** When this source was read (US-14). Absent on older proposals: use `generated_at`. */
  retrieved_at?: string | null
}

/** One direction of a flight trip. */
export interface FlightLeg {
  /** `outbound` or `return`. */
  direction: 'outbound' | 'return'
  /** The travel date, YYYY-MM-DD. Example: `"2026-12-13"`. */
  date: string
  /** The airline for this direction. Example value: `"Saudia"`. */
  airline: InfoField
  /** The flight time for this direction. Example value: `"3h 20m"`. */
  duration: InfoField
  /** On a round_trip the price is on the whole trip, so this is `Not available`. */
  price: SarPrice
  /** A link saved at generation. It can expire, so the page asks for a fresh one. */
  booking_url: string | null
  /** Null on older proposals. Example: `"SV 1020"`. Connections: `"SV 1020, SV 45"`. */
  flight_number?: string | null
  /** Local airport time, or null on older proposals. Example: `"2026-12-13T08:30"`. */
  departure_time?: string | null
  /** Local airport time, or null on older proposals. */
  arrival_time?: string | null
  /** 0 is nonstop. Null on older proposals. */
  stops?: number | null
  /** Who sells this leg, or null. It can differ from the airline. */
  seller?: string | null
  /** Where the stops are, or empty on older proposals. Example: ["ATH"]. */
  stop_airports?: string[]
}

/** The flights from one departure city. */
export interface Flights {
  /** The departure city. A member receives only their own. Example: `"Riyadh"`. */
  origin: string
  /** See TripType. Example: `"round_trip"`. */
  trip_type: TripType
  /** One leg for one_way. Otherwise outbound then return. */
  legs: FlightLeg[]
  /** The outbound airline, as a summary. Example value: `"Saudia"`. */
  airline: InfoField
  /** The outbound flight time, as a summary. Example value: `"3h 20m"`. */
  duration: InfoField
  /** The whole trip's cost. On one_way, the return is not counted. */
  price_per_person: SarPrice
  /** When this price was checked, or null on older proposals. */
  priced_at?: string | null
  /** Three-letter code, or null on older proposals. Example: `"RUH"`. */
  origin_airport?: string | null
  /** Three-letter code, or null on older proposals. */
  destination_airport?: string | null
  /** Whether the search for everyone from this city found the flight. Never a count. */
  group_availability?: 'available' | 'not_found' | 'unknown'
  /** solo: each person booking alone was cheaper, and the price shown is that one. */
  fare_basis?: 'group' | 'solo' | null
  /** With solo: how much less per person than one booking together. */
  solo_saving_sar?: string | null
  /** Added when reading. */
  airline_fares?: AirlineFareNote[]
  /** Which source gave this price. Example: "ignav". */
  provider?: string | null
  /** airline, third_party, or null when unknown. */
  seller_type?: string | null
  /** seller: the seller's own price. search: the search result's. */
  price_source?: 'seller' | 'search' | null
  /** Null when the source does not say. */
  cabin_class?: string | null
  fare_name?: string | null
  /** Allowance per person, or null when the source does not say. */
  checked_bags?: number | null
  carry_on_bags?: number | null
}

/** General facts about an airline's cheapest fare, never a promise for a ticket. */
export interface AirlineFareNote {
  code: string
  name_en: string
  name_ar: string
  fare_en: string
  fare_ar: string
  /** The usual checked bag: 0 is none, and null is not confirmed. */
  checked_kg?: number | null
}

/** A free photo with its credit. Added when reading, and never saved. */
export interface PlaceImage {
  url: string
  /** The picture's page, with its full licence. */
  source_url: string
  artist?: string | null
  /** Example: "CC BY-SA 4.0". */
  license: string
}

/** A stay in one city. */
export type ActivityCategory = 'activity' | 'attraction' | 'restaurant'

export interface Activity {
  id: string
  /** Legacy records without a category are ordinary activities. */
  category?: ActivityCategory
  name: InfoField
  description: InfoField
  location: InfoField
  duration: InfoField
  scheduled_date: InfoField
  /** Same status rules as hotel prices, with zero allowed for free activities. */
  price_per_person: SarPrice
  booking_url: string | null
  image_url: string | null
}

export interface EstimateComponent {
  known_amount_sar: string
  missing_items: number
  unconfirmed_items: number
  estimated_items: number
}

/** Per-person estimate for the current caller's flight route and selections. */
export interface ActivityProposalEstimate {
  proposal_id: string
  version: number
  currency: 'SAR'
  flights: EstimateComponent
  accommodation: EstimateComponent
  transport: EstimateComponent
  activities: EstimateComponent
  total: EstimateComponent
}

export interface ActivitySelections {
  proposal_id: string
  version: number
  activity_ids: string[]
  estimate?: ActivityProposalEstimate
}

/** A stay in one city. */
export interface CityStay {
  activities?: Activity[]
  /** The position in the route, counting up from 1. Example: `1`. */
  order: number
  /** The city name. Example: `"Cairo"`. */
  city: string
  /** The city in Arabic, or null on older proposals. */
  city_ar?: string | null
  /** Nights here. All stays add up to the trip dates. Example: `4`. */
  nights: number
  /** A suggested hotel. Example value: `"Mock Hotel"`. */
  hotel_name: InfoField
  /** The price per night. It is never `Sourced`. Example amount: `"450.00"`. */
  hotel_price_per_night: SarPrice
  /** A Booking.com search, or null. It does not confirm availability or price. */
  booking_url: string | null
  /** A suggested area from idea sources, or null. Example: `"Le Marais"`. */
  area?: string | null
  /** When this price was checked, or null on older proposals. */
  priced_at?: string | null
  /** A page for this hotel itself, as its source gave it. */
  hotel_url?: string | null
  /** Who gave the hotel and price when it was a live source. Example: "Trip.com". */
  hotel_source?: string | null
  /** A photo of this city, or null. */
  image?: PlaceImage | null
}

/** Travel between two consecutive cities. */
export interface IntercityTransfer {
  /** The city left. Example: `"Cairo"`. */
  from_city: string
  /** The city reached. Example: `"Alexandria"`. */
  to_city: string
  /** How to travel. Example value: `"Train"`. */
  mode: InfoField
  /** The travel time. Example value: `"1.5 hours"`. */
  duration: InfoField
  /** The price for one person. It is never `Sourced`. Example amount: `"53.00"`. */
  price_per_person: SarPrice
  /** Station names, or null. Nothing fills these yet. */
  from_station?: string | null
  to_station?: string | null
}

/** Explains a Flexible preference that this proposal could not meet. */
export interface FlexibleAdjustment {
  /** See PreferenceCategory. Example: `"accommodation"`. */
  category: PreferenceCategory
  /** General text with no digits or member details. Example: `"A standard option is suggested."`. */
  explanation: string
}

/** One complete trip option. */
export interface Proposal {
  activity_research_status?: 'not_requested' | 'ready' | 'unavailable'
  /** This proposal's own id, a UUID. */
  id: string
  /** The trip it belongs to, a UUID. */
  trip_id: string
  /** The generation round. It goes up each time proposals are regenerated. Example: `1`. */
  version: number
  /** 1, 2 or 3. */
  option_number: 1 | 2 | 3
  /** A general title with no private details. Example: `"Nile Heritage Experience"`. */
  title: string
  /** The title in Arabic, or absent on older proposals. Show `title` then. */
  title_ar?: string | null
  /** The title in English, or absent on older proposals. Show `title` then. */
  title_en?: string | null
  /** The place shown to users. Example: `"Cairo"`. */
  destination: string
  /** The place in Arabic, or null on older proposals. */
  destination_ar?: string | null
  /** The first day, YYYY-MM-DD. Example: `"2026-12-13"`. */
  start_date: string
  /** The last day, YYYY-MM-DD. Example: `"2026-12-17"`. */
  end_date: string
  /** At least one stay, in route order. */
  cities: CityStay[]
  /** Holds only the signed-in member's departure city, so this list can be empty. */
  flights: Flights[]
  /** One entry between each pair of consecutive cities. Empty for a single city. */
  intercity_transport: IntercityTransfer[]
  /** Empty when every Flexible preference was met. */
  flexible_adjustments: FlexibleAdjustment[]
  /** See BudgetStatus. Example: `"includes_unconfirmed"`. */
  budget_status: BudgetStatus
  /** Every source cited by Evidence in this proposal. */
  sources: ProposalSource[]
  /** A photo of the destination, or null. */
  image?: PlaceImage | null
  /** US-15: how this proposal matches the group's requirements. Empty on older proposals. */
  compatibility?: CompatibilityCheck[]
}

/**
 * US-15. `met`: checked by the backend. `unverified`: only the AI reported it met.
 * `unmet`: not met; a Flexible one is explained in `flexible_adjustments`.
 */
export type CompatibilityStatus = 'met' | 'unverified' | 'unmet'
/** The preference categories, plus the group budget and the shared dates. */
export type CompatibilityTopic = PreferenceCategory | 'budget' | 'dates'

/** One result per topic and importance. Never holds requirement text or a member. */
export interface CompatibilityCheck {
  topic: CompatibilityTopic
  /** Essential or Flexible for a preference. Required for budget and dates. */
  importance: 'Essential' | 'Flexible' | 'Required'
  status: CompatibilityStatus
}

/** US-13 cost categories. */
export type CostCategory = 'flights' | 'accommodation' | 'transport' | 'activities' | 'meals'
/** `single`: one person per room. `shared`: two per room, split evenly. */
export type RoomPlan = 'single' | 'shared'
/** The caller's own budget, as a label only. */
export type OwnBudget = 'within' | 'over' | 'unconfirmed' | 'unknown'
export type CostAssumption =
  | 'rooms_single' | 'rooms_shared' | 'flights_own_city' | 'flights_one_way' | 'flights_missing'
  | 'meals_allowance' | 'activities_not_included' | 'activities_selected' | 'group_total_all_cities'
  | 'group_total_unavailable' | 'prices_may_change'

export interface CostAmount {
  /** The sum of the known parts, as a string such as `"3750.00"`, or null. */
  amount_sar: string | null
  /** The weakest status among the known parts. */
  status: PriceStatus
  /** True when a part is Not available, so the amount is too low. */
  partial: boolean
}

export interface CostLine {
  category: CostCategory
  per_person: CostAmount
  /** False for information only, such as activities not added yet. */
  counted: boolean
}

export interface CostScenario {
  rooms: RoomPlan
  lines: CostLine[]
  per_person_total: CostAmount
  /** Null when the backend could not read the group. */
  group_total: CostAmount | null
  own_budget: OwnBudget
  /** Only when `own_budget` is `over`, for this member alone. */
  over_by_sar: string | null
}

/** The signed-in member's cost breakdown for one proposal. Worked out on reading. */
export interface ProposalCosts {
  proposal_id: string
  days: number
  nights: number
  scenarios: CostScenario[]
  assumptions: CostAssumption[]
}

/** A general conflict category. It never names a member or a value. */
export type ConflictCategory = 'readiness' | 'dates' | 'destinations' | 'flights' | 'accommodation' | 'budget'

/** The response of `GET /api/trips/{trip_id}/conflicts`. */
export interface GroupConflicts {
  /** Every current conflict, shown to all members. Example: `["dates"]`. */
  conflicts: ConflictCategory[]
  /** Conflicts where this member has an Essential to review. Example: `["destinations"]`. */
  own_review: ConflictCategory[]
  /** True only when there are no conflicts. */
  can_generate: boolean
}

/** The response of `GET /api/trips/{trip_id}/proposals`. */
export interface StoredProposals {
  /** The latest round, or null if nothing has been generated. Example: `1`. */
  version: number | null
  /** False when fewer than three proposals passed the checks. */
  complete: boolean
  /** When the latest round was saved, or null. */
  generated_at: string | null
  /** True while a generation is running for this trip. */
  generating: boolean
  /** True when members or preferences changed after generation, or none has this member's city. */
  needs_regeneration: boolean
  /** Up to three proposals, by option number. Can be empty. */
  proposals: Proposal[]
  /** A price is fresh below this many hours. Set by the backend. */
  price_fresh_hours?: number
  /** A price is old above this many hours. Set by the backend. */
  price_stale_hours?: number
  /** Minutes before the flight price can be refreshed again. */
  refresh_cooldown_minutes?: number
  /** US-13: the caller's own costs for each proposal. Absent from older backends. */
  costs?: ProposalCosts[]
}

/** The response of `POST /api/trips/{trip_id}/proposals`, administrator only. */
export interface GeneratedProposals extends StoredProposals {
  /** A general note when not all proposals passed, or null. */
  message: string | null
  /** True when the inputs had not changed, so saved proposals were kept. */
  reused: boolean
  /** True when these are the saved demo proposals. */
  demo: boolean
}


export interface ProposalSet {
  /** Options 1, 2 and 3. */
  proposals: Proposal[]
}


/** What a running generation is doing. Holds no private data. */
export type GenerationStage = 'planning' | 'checking_flights' | 'researching' | 'saving' | 'done' | 'failed'
export type OptionStage = 'checking_flights' | 'flights_found' | 'dates_moved' | 'no_flights' | 'researching' | 'ready' | 'failed'

export interface OptionProgress {
  key: string
  title: string | null
  title_ar: string | null
  destination: string | null
  destination_ar: string | null
  status: OptionStage
  start_date: string | null
  end_date: string | null
  /** Days the departure moved to find flights: + later, - earlier. */
  date_shift_days: number
  hotel_name: string | null
  /** A decimal string in SAR, or null. */
  hotel_price_per_night_sar: string | null
  hotel_source: string | null
}

export interface GenerationProgress {
  stage: GenerationStage
  started_at: string
  updated_at: string
  options: OptionProgress[]
  target: number
  ready: number
}

export type SuggestionAction = 'edit_dates' | 'edit_preferences' | 'retry'
export type SuggestionKind = 'dates_too_soon' | 'widen_dates' | 'add_destination' | 'retry_later' | 'generate_again' | 'review_essentials' | 'wait_and_retry'

export interface GenerationSuggestion {
  action: SuggestionAction
  kind: SuggestionKind
  /** English copy; the page shows its own translation for the kind. */
  text: string
  params: Record<string, string>
}

/** Why generation produced nothing, and what the group can change. */
export interface GenerationIssue {
  code: string
  message: string
  places: string[]
  suggestions: GenerationSuggestion[]
}
