import { useLanguage } from '../lib/language'
import { calendarDate } from '../lib/planning'
import { placeName } from '../lib/places'
import type { GenerationIssue, GenerationSuggestion, SuggestionAction, SuggestionKind } from '../types/proposal'
import { WarningIcon } from './proposal-details/icons'

// Nielsen 9: say what happened in plain words, then offer a way forward.
const titles: Record<string, string> = {
  no_flights: 'No bookable flights for these dates',
  no_proposals: 'No proposal passed the checks',
}

const suggestionText: Record<SuggestionKind, string> = {
  dates_too_soon: 'Trips need to start at least {days} days from today so seats can still be booked. Move the group’s dates to {earliest} or later.',
  widen_dates: 'Widen the group’s shared dates by a few days, so other departure days can be checked.',
  add_destination: 'Add more places to your preferences, or leave them empty, so Rihla can look at more places with flights from every departure city.',
  retry_later: 'Try again in about {hours} hours: airlines add and release seats during the day, and Rihla checks live each time.',
  generate_again: 'Generate again: the AI suggests different places each time.',
  review_essentials: 'Review Essential preferences: fewer Essential items give the AI more places to choose from.',
  wait_and_retry: 'Wait a few minutes, then generate again.',
}

const actionLabels: Record<SuggestionAction, string> = {
  edit_dates: 'Change dates',
  edit_preferences: 'Open preferences',
  retry: 'Try again',
}

export function GenerationIssueCard({ issue, isAdmin, onAction }: { issue: GenerationIssue; isAdmin: boolean; onAction: (action: SuggestionAction) => void }) {
  const { t, language, locale } = useLanguage()
  const places = issue.places.map((place) => placeName(place, language)).join(language === 'ar' ? '، ' : ', ')
  const text = (item: GenerationSuggestion) => {
    const template = suggestionText[item.kind]
    if (!template) return item.text
    const earliest = item.params.earliest ? calendarDate(item.params.earliest, locale) : ''
    const days = item.params.days ? Number(item.params.days).toLocaleString(locale) : ''
    const hours = Number(item.params.hours ?? 2).toLocaleString(locale)
    return t(template, { earliest, days, hours })
  }
  // Only the administrator can generate; every member can change their own inputs.
  const shown = issue.suggestions.filter((item) => isAdmin || item.action !== 'retry')
  return <section className="generation-issue" role="alert" aria-labelledby="generation-issue-title">
    <h3 id="generation-issue-title"><WarningIcon /> {t(titles[issue.code] ?? 'Proposals could not be generated')}</h3>
    {issue.code === 'no_flights' && places
      ? <p>{t('Rihla checked live flights to {places}, but none could be booked for the group’s dates.', { places })}</p>
      : issue.code !== 'no_flights' && <p>{t(issue.message)}</p>}
    {shown.length > 0 && <>
      <p className="generation-issue-lead">{t('What you can do:')}</p>
      <ul className="generation-suggestions">
        {shown.map((item) => <li key={item.kind}>
          <span>{text(item)}</span>
          <button type="button" className={item.action === 'retry' ? 'trip-primary' : 'trip-secondary'} onClick={() => onAction(item.action)}>{t(actionLabels[item.action])}</button>
        </li>)}
      </ul>
    </>}
  </section>
}
