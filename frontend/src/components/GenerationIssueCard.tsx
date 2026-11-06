import { useLanguage } from '../lib/language'
import { useGenerationRetry } from '../lib/useGenerationRetry'
import { calendarDate } from '../lib/planning'
import { placeName } from '../lib/places'
import { safeLink } from '../lib/proposals'
import type { GenerationIssue, GenerationSuggestion, SuggestionAction, SuggestionKind } from '../types/proposal'
import { WarningIcon } from './proposal-details/icons'

// Nielsen 9: say what happened in plain words, then offer a way forward.
const titles: Record<string, string> = {
  no_flights: 'No bookable flights for these dates',
  no_proposals: 'No proposal passed the checks',
  dates_unavailable: 'Choose later travel dates',
  budget_limit: 'The price is above the budget, not the dates',
}

// The searches' own reasons, in words a member can act on.
const causeText: Record<string, string> = {
  dates_not_searchable: 'The flight source does not search these dates yet, usually because they are far ahead. Try earlier dates.',
  no_seats: 'No flight that day has enough seats left for everyone flying from the same city together.',
  lands_after_trip: 'There are flights, but the only ones home land after the group’s last day.',
  no_single_booking: 'Flights exist, but outbound and return can only be bought as two separate bookings, which Rihla does not offer.',
  not_on_sale: 'The flights listed are no longer on sale on the airline’s or Google’s site.',
}

const suggestionText: Record<SuggestionKind, string> = {
  check_departure_city: 'A departure city could not be matched to an airport. Each member should check their departure city in preferences.',
  dates_too_soon: 'Trips need to start at least {days} days from today so seats can still be booked. Move the group’s dates to {earliest} or later.',
  widen_dates: 'Widen the group’s shared dates by a few days, so other departure days can be checked.',
  add_destination: 'Add more places to your preferences, or leave them empty, so Rihla can look at more places with flights from every departure city.',
  retry_later: 'Try again in about {hours} hours: airlines add and release seats during the day, and Rihla checks live each time.',
  generate_again: 'Generate again: the AI suggests different places each time.',
  review_essentials: 'Review Essential preferences: fewer Essential items give the AI more places to choose from.',
  wait_and_retry: 'Wait a few minutes, then generate again.',
  retry_after: 'Try again after {time}.',
  review_budget: 'Try fewer nights or more affordable destinations. Every member’s budget remains a firm limit.',
  search_google_flights: 'Search Google Flights for {place} yourself. Rihla does not make a trip until it finds tickets the whole group can book.',
  try_other_dates: 'Try other travel dates: flights on other days may have seats for everyone, or better fares.',
}

const actionLabels: Record<SuggestionAction, string> = {
  edit_dates: 'Change dates',
  edit_preferences: 'Open preferences',
  retry: 'Try again',
  open_link: 'Open Google Flights',
}

export function GenerationIssueCard({ issue, isAdmin, onAction }: { issue: GenerationIssue; isAdmin: boolean; onAction: (action: SuggestionAction) => void }) {
  const { t, language, locale } = useLanguage()
  const { retryPending } = useGenerationRetry(issue)
  const places = issue.places.map((place) => placeName(place, language)).join(language === 'ar' ? '، ' : ', ')
  const text = (item: GenerationSuggestion) => {
    const template = suggestionText[item.kind]
    if (!template) return item.text
    const earliest = item.params.earliest ? calendarDate(item.params.earliest, locale) : ''
    const days = item.params.days ? Number(item.params.days).toLocaleString(locale) : ''
    const hours = Number(item.params.hours ?? 2).toLocaleString(locale)
    const retryTime = Date.parse(item.params.retry_at ?? '')
    const time = Number.isFinite(retryTime) ? new Date(retryTime).toLocaleString(locale, { dateStyle: 'medium', timeStyle: 'short' }) : ''
    const place = item.params.place ? placeName(item.params.place, language) : ''
    return t(template, { earliest, days, hours, time, place })
  }
  // Only the administrator can generate; every member can change their own inputs.
  const shown = issue.suggestions.filter((item) => isAdmin || item.action !== 'retry')
  return <section className="generation-issue" role="alert" aria-labelledby="generation-issue-title">
    <h3 id="generation-issue-title"><WarningIcon /> {t(titles[issue.code] ?? 'Proposals could not be generated')}</h3>
    {issue.code === 'budget_limit'
      ? <p>{t('Rihla found trips for these dates, but each one costs more than the group’s budget allows. The problem is the price, not the dates.')}</p>
      : issue.code === 'no_flights' && places
      ? <p>{t('Rihla checked live flights to {places}, but none could be booked for the group’s dates.', { places })}</p>
      : <p>{t(issue.message)}</p>}
    {(issue.causes ?? []).length > 0 && <>
      <p className="generation-issue-lead">{t('Why:')}</p>
      <ul className="generation-causes">
        {(issue.causes ?? []).map((cause) => <li key={cause.kind}>{causeText[cause.kind] ? t(causeText[cause.kind]) : cause.text}</li>)}
      </ul>
    </>}
    {shown.length > 0 && <>
      <p className="generation-issue-lead">{t('What you can do:')}</p>
      <ul className="generation-suggestions">
        {shown.map((item) => <li key={item.kind}>
          <span>{text(item)}</span>
          {item.action === 'open_link'
            ? safeLink(item.params.url ?? null) && <a className="trip-secondary" href={safeLink(item.params.url ?? null)!} target="_blank" rel="noreferrer">{t(actionLabels[item.action])}</a>
            : <button type="button" disabled={item.action === 'retry' && retryPending} className={item.action === 'retry' ? 'trip-primary' : 'trip-secondary'} onClick={() => onAction(item.action)}>{t(actionLabels[item.action])}</button>}
        </li>)}
      </ul>
    </>}
  </section>
}
