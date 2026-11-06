import { useEffect, useRef, useState } from 'react'
import { elapsedLabel } from '../lib/aiStatus'
import { useLanguage } from '../lib/language'
import { calendarDate } from '../lib/planning'
import { placeName } from '../lib/places'
import type { GenerationProgress, GenerationStage, OptionProgress, OptionStage } from '../types/proposal'
import { useSar } from './proposal-details/useSar'
import { CheckIcon, ClockIcon, PlaneIcon, SparkleIcon, StaysTitleIcon, WarningIcon } from './proposal-details/icons'

// The steps the backend reports, in order. Words name what the person cares about,
// not the system's internals (Nielsen 2: match between system and the real world).
const STEPS: { stage: GenerationStage; label: string }[] = [
  { stage: 'planning', label: 'Choosing destinations that suit everyone' },
  { stage: 'checking_flights', label: 'Checking real flights from every departure city' },
  { stage: 'researching', label: 'Finding hotels and trip details' },
  { stage: 'saving', label: 'Saving the proposals' },
]

// How long a place without flights stays on screen before it leaves the list.
export const DROPPED_VISIBLE_MS = 2500

const optionLabels: Record<OptionStage, string> = {
  checking_flights: 'Checking flights…',
  flights_found: 'Round-trip flights found',
  dates_moved: 'Round-trip flights found',
  no_flights: 'No bookable flights. Trying another place.',
  researching: 'Finding a hotel…',
  ready: 'Ready',
  failed: 'Did not pass the checks',
}

function stepIndex(stage: GenerationStage): number {
  if (stage === 'done') return STEPS.length
  const found = STEPS.findIndex((step) => step.stage === stage)
  return found < 0 ? 0 : found
}

function OptionRow({ option }: { option: OptionProgress }) {
  const { t, language, locale } = useLanguage()
  const sar = useSar()
  const name = option.destination ? placeName(option.destination, language, option.destination_ar ?? undefined) : t('A destination')
  const tone = option.status === 'ready' ? 'done' : option.status === 'no_flights' || option.status === 'failed' ? 'warn' : 'busy'
  const shift = option.date_shift_days
  return <li className={`generation-option generation-option--${tone}`}>
    <span className="generation-option-icon" aria-hidden="true">
      {tone === 'done' ? <CheckIcon /> : tone === 'warn' ? <WarningIcon /> : <PlaneIcon />}
    </span>
    <div className="generation-option-body">
      <p className="generation-option-name"><bdi>{name}</bdi>
        {option.start_date && option.end_date && <span className="generation-option-dates"> · {calendarDate(option.start_date, locale)} {t('to')} {calendarDate(option.end_date, locale)}</span>}
      </p>
      <p className="generation-option-status">{t(optionLabels[option.status])}
        {shift !== 0 && option.status !== 'no_flights' && <> · {Math.abs(shift) === 1
          ? t(shift > 0 ? 'Departure moved 1 day later to find flights' : 'Departure moved 1 day earlier to find flights')
          : t(shift > 0 ? 'Departure moved {days} days later to find flights' : 'Departure moved {days} days earlier to find flights', { days: Math.abs(shift).toLocaleString(locale) })}</>}
      </p>
      {option.hotel_price_per_night_sar && <p className="generation-option-hotel"><StaysTitleIcon />
        <span>{t('{hotel}: {price} a night', { hotel: option.hotel_name ?? t('Hotel'), price: sar(option.hotel_price_per_night_sar) })}{option.hotel_source && <> · <bdi>{option.hotel_source}</bdi></>}</span>
      </p>}
    </div>
  </li>
}

/** Live steps while proposals are generated (Nielsen 1: visibility of system status). */
export function GenerationProgressView({ progress, elapsedSeconds }: { progress: GenerationProgress | null; elapsedSeconds: number }) {
  const { t, locale } = useLanguage()
  const current = stepIndex(progress?.stage ?? 'planning')
  const options = progress?.options ?? []
  const ready = progress?.ready ?? 0
  // A place without bookable flights shows briefly, then leaves, so the list
  // keeps only places still in play. A count keeps what was checked visible.
  const [gone, setGone] = useState<ReadonlySet<string>>(() => new Set())
  const timers = useRef(new Map<string, number>())
  const dropped = options.filter((option) => option.status === 'no_flights' || option.status === 'failed')
  useEffect(() => {
    for (const option of dropped) {
      if (timers.current.has(option.key)) continue
      timers.current.set(option.key, window.setTimeout(() => setGone((current) => new Set(current).add(option.key)), DROPPED_VISIBLE_MS))
    }
  }, [dropped])
  useEffect(() => () => { for (const timer of timers.current.values()) window.clearTimeout(timer) }, [])
  const shown = options.filter((option) => !gone.has(option.key))
  const skipped = options.length - shown.length
  return <section className="generation-progress" aria-labelledby="generation-progress-title">
    <div className="generation-progress-head">
      <h3 id="generation-progress-title"><span className="ai-status-spark" aria-hidden="true"><SparkleIcon /></span> {t('Building your proposals')}</h3>
      <p className="generation-elapsed"><ClockIcon /> <span>{t('Elapsed {time}', { time: elapsedLabel(elapsedSeconds, locale) })}</span></p>
    </div>
    <ol className="generation-steps">
      {STEPS.map((step, index) => {
        const state = index < current ? 'done' : index === current ? 'current' : 'todo'
        return <li key={step.stage} className={`generation-step generation-step--${state}`} aria-current={state === 'current' ? 'step' : undefined}>
          <span className="generation-step-mark" aria-hidden="true">{state === 'done' ? <CheckIcon /> : (index + 1).toLocaleString(locale)}</span>
          <span>{t(step.label)}</span>
          {state === 'done' && <span className="visually-hidden">{t('Done')}</span>}
        </li>
      })}
    </ol>
    {/* One short polite announcement, not every row, so screen readers are not flooded. */}
    <p className="generation-summary" role="status" aria-live="polite">
      {t('{ready} of {target} proposals ready', { ready: ready.toLocaleString(locale), target: (progress?.target ?? 3).toLocaleString(locale) })}
    </p>
    {shown.length > 0 && <ul className="generation-options">{shown.map((option) => <OptionRow key={option.key} option={option} />)}</ul>}
    {skipped > 0 && <p className="generation-skipped">{t('Skipped {count} places that did not pass the checks', { count: skipped.toLocaleString(locale) })}</p>}
    <p className="proposals-note">{t('Checking flights, stays and your group’s limits. Prices remain subject to availability.')}</p>
  </section>
}
