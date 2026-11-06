import { useEffect, useState, type MouseEvent } from 'react'
import { ArrowUpRight, BedDouble, CalendarCheck2, CircleCheck, Coins, MapPinned, Plane, SlidersHorizontal } from 'lucide-react'
import { GENERATE_STEP_MS, generateMessages } from '../lib/aiStatus'
import { useLanguage } from '../lib/language'
import { navigate } from '../lib/navigation'
import { calendarDate } from '../lib/planning'
import { placeName } from '../lib/places'
import { ApiError } from '../lib/http'
import { useGenerationRetry } from '../lib/useGenerationRetry'
import { budgetStatusLabels, canPressGenerate, conflictMessages, generateProposals, generationIssue, getConflicts, getGenerationProgress, getProposals, PROGRESS_POLL_MS, proposalTitle, reviewMessages } from '../lib/proposals'
import type { GenerationIssue, GenerationProgress, GroupConflicts, Proposal, StoredProposals, SuggestionAction } from '../types/proposal'
import { AiStatus } from './AiStatus'
import { GenerationIssueCard } from './GenerationIssueCard'
import { GenerationProgressView } from './GenerationProgress'
import { FlightPriceReview } from './FlightPriceReview'
import { PlacePhoto } from './proposal-details/PlacePhoto'
import '../proposals.css'
import '../proposal-details.css'
import '../proposal-fonts'

const proposalPath = (proposal: Proposal) => `/trips/${proposal.trip_id}/proposals/${proposal.id}`

function openProposal(event: MouseEvent, proposal: Proposal) {
  // Keeps open-in-new-tab working for modified clicks.
  if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return
  event.preventDefault()
  navigate(proposalPath(proposal))
}

type ViewProps = {
  isAdmin: boolean
  conflicts: GroupConflicts | null
  stored: StoredProposals | null
  busy: boolean
  error: string
  notice: string
  onGenerate: (regenerate: boolean, tripDays?: number | null) => void
  /** Days every member is free together; the administrator picks a length inside it. */
  sharedDays?: number | null
  progress?: GenerationProgress | null
  elapsedSeconds?: number
  issue?: GenerationIssue | null
  onIssueAction?: (action: SuggestionAction) => void
  preferencesHref?: string
}

export function ProposalsView({ isAdmin, conflicts, stored, busy, error, notice, onGenerate, progress = null, elapsedSeconds = 0, issue = null, onIssueAction = () => undefined, preferencesHref, sharedDays = null }: ViewProps) {
  const { t, locale, language } = useLanguage()
  // 0 lets the AI choose the length inside the shared dates.
  const [tripDays, setTripDays] = useState(0)
  const lengths = sharedDays && sharedDays > 1 ? Array.from({ length: sharedDays - 1 }, (_, index) => index + 2) : []
  const generating = busy || stored?.generating === true
  const { retryPending } = useGenerationRetry(issue)
  const enabled = canPressGenerate(conflicts, generating) && !retryPending
  const proposals = stored?.proposals ?? []
  return <section className="proposals-panel" aria-labelledby="proposals-title">
    <div className="proposals-heading">
      <div className="proposals-heading-copy"><span className="proposals-kicker"><MapPinned size={16} aria-hidden="true" />{t('TRIP PROPOSALS')}</span><h2 id="proposals-title">{t(proposals.length ? 'Your trip options' : 'Find a trip that fits everyone')}</h2><p>{t('Your group’s dates. Your lowest budget. One plan together.')}</p></div>
      <div className="proposals-actions">
        {isAdmin && <button type="button" className="trip-primary" disabled={!enabled} aria-describedby={retryPending ? 'generation-issue-title' : undefined} onClick={() => { if (enabled) onGenerate(proposals.length > 0, tripDays || null) }}>
          {generating ? <AiStatus messages={progress ? ['Generating proposals…'] : generateMessages} stepMs={GENERATE_STEP_MS} /> : proposals.length > 0 ? t('Generate again') : t('Generate proposals')}
          {!generating && <ArrowUpRight size={17} aria-hidden="true" />}
        </button>}
        {preferencesHref && <a className="proposals-preferences" href={preferencesHref} onClick={event => { if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return; event.preventDefault(); navigate(preferencesHref) }}><SlidersHorizontal size={15} aria-hidden="true" />{t('Edit preferences')}</a>}
      </div>
    </div>
    {isAdmin && !generating && lengths.length > 0 && <div className="generation-length">
      <label htmlFor="generation-length">{t('Everyone is free for {count} days together. How long should the trip be?', { count: sharedDays!.toLocaleString(locale) })}</label>
      <select id="generation-length" value={tripDays} onChange={(event) => setTripDays(Number(event.target.value))}>
        <option value={0}>{t('Let the AI choose')}</option>
        {lengths.map((days) => <option key={days} value={days}>{t('{count} days', { count: days.toLocaleString(locale) })}</option>)}
      </select>
    </div>}
    {!generating && !proposals.length && !issue && <div className={`generation-readiness${conflicts?.can_generate ? ' generation-readiness--ready' : ''}`} role="status"><CircleCheck size={18} aria-hidden="true" /><span>{t(conflicts === null ? 'Checking group readiness…' : conflicts.can_generate ? 'Ready to compare trip options' : 'Complete the group’s details before generating.')}</span></div>}
    {conflicts && conflicts.conflicts.length > 0 && <ul className="proposals-conflicts" role="status">
      {conflicts.conflicts.map((category) => <li key={category}>{t(conflictMessages[category])}</li>)}
    </ul>}
    {conflicts?.own_review.map((category) => reviewMessages[category] && <p className="proposals-review" key={category}>{t(reviewMessages[category])}</p>)}
    {generating && <GenerationProgressView progress={progress} elapsedSeconds={elapsedSeconds} />}
    {!generating && issue && <GenerationIssueCard issue={issue} isAdmin={isAdmin} onAction={onIssueAction} />}
    {error && !issue && <p className="trip-feedback trip-feedback--error" role="alert">{t(error)}</p>}
    {notice && <p className="trip-feedback trip-feedback--success" role="status">{t(notice)}</p>}
    {stored?.needs_regeneration && !generating && <p className="proposals-review" role="status">{t(isAdmin ? 'The trip’s details changed after these proposals were generated. Generate them again to include the changes.' : 'The trip’s details changed after these proposals were generated. The administrator needs to generate them again.')}</p>}
    {stored && stored.version !== null && !stored.complete && <p className="proposals-note">{t('Some proposals could not pass the checks, so fewer than three are shown.')}</p>}
    {proposals.length > 0 ? <ol className="proposals-list">
      {proposals.map((proposal) => {
        const cost = stored?.costs?.find((item) => item.proposal_id === proposal.id)?.scenarios.find((scenario) => scenario.rooms === 'single')
        const total = cost?.per_person_total
        const activitiesPending = cost?.lines.some((line) => line.category === 'activities' && !line.counted)
        return <li className="proposals-card" key={proposal.id}>
        <PlacePhoto image={proposal.image} place={placeName(proposal.destination, language, proposal.destination_ar)} />
        <div className="proposals-card-body">
        <p className="trip-eyebrow">{t('Option {number}', { number: proposal.option_number.toLocaleString(locale) })}</p>
        <h3><a href={proposalPath(proposal)} onClick={(event) => openProposal(event, proposal)}><bdi>{proposalTitle(proposal, language)}</bdi></a></h3>
        <p className="proposals-destination"><bdi>{placeName(proposal.destination, language, proposal.destination_ar)}</bdi></p>
        <p className="proposals-dates">{calendarDate(proposal.start_date, locale)} {t('to')} {calendarDate(proposal.end_date, locale)}</p>
        <FlightPriceReview routes={proposal.flights} minutes={stored?.price_review_minutes ?? 15} compact />
        <span className={`planning-badge${!stored?.needs_regeneration && proposal.budget_status === 'within_group_budget' ? ' planning-badge--ready' : ''}`}>{t(stored?.needs_regeneration ? 'Regenerate to recheck budget and preferences' : budgetStatusLabels[proposal.budget_status])}</span>
        {total?.amount_sar !== null && total?.amount_sar !== undefined && <div className="proposal-cost-preview">
          <span>{t(stored?.needs_regeneration ? 'Previous estimate per person' : total.partial ? 'Known subtotal per person' : activitiesPending ? 'Base estimate per person' : 'Estimated per person')}</span>
          <strong><bdi>{Number(total.amount_sar).toLocaleString(locale, { style: 'currency', currency: 'SAR', maximumFractionDigits: 2 })}</bdi></strong>
          <small>{t(total.partial ? 'Some prices are missing. This is not the full trip cost.' : 'One person per room. See the breakdown before deciding.')}</small>
          {activitiesPending && <small>{t('Activities are added after selection. Their prices may change the total.')}</small>}
        </div>}
        {!stored?.needs_regeneration && proposal.fit && <p className="proposals-fit">{t('Fits everyone: at least {percent}', { percent: (proposal.fit.least_satisfied_percent / 100).toLocaleString(locale, { style: 'percent' }) })}</p>}
        <a className="trip-secondary proposals-open" href={proposalPath(proposal)} onClick={(event) => openProposal(event, proposal)}>{t('View details')}</a>
        </div>
      </li>})}
    </ol> : !generating && !issue && <div className="proposals-empty">
      <ul className="generation-includes" aria-label={t('What your trip estimate includes')}>
        <li><Plane size={22} aria-hidden="true" /><span>{t('Round-trip flights on one booking')}</span><small>{t('From each departure city')}</small></li>
        <li><BedDouble size={22} aria-hidden="true" /><span>{t('Hotels and stays')}</span><small>{t('For the trip’s dates')}</small></li>
        <li><Coins size={22} aria-hidden="true" /><span>{t('Per-person costs')}</span><small>{t('With missing prices clearly marked')}</small></li>
      </ul>
      <p className="proposals-note">{t(isAdmin ? 'Generate up to three options, then compare the details.' : 'The administrator generates the options when everyone is ready.')}</p>
    </div>}
    {!generating && <details className="generation-explainer"><summary><CalendarCheck2 size={16} aria-hidden="true" />{t('How your plan is checked')}</summary><p>{t('Dates and every member’s budget stay as limits. Essential preferences must be respected; Flexible preferences may be adjusted with an explanation. Activity choices are added to the estimate later. Prices and availability must be checked before booking.')}</p></details>}
    {proposals.length > 0 && <p className="proposals-note proposals-ai-note">{t('AI can make mistakes. Check the details before you book.')}</p>}
  </section>
}

export function ProposalsPanel({ tripId, isAdmin, revision, sharedDays = null }: { tripId: string; isAdmin: boolean; revision: number; sharedDays?: number | null }) {
  const [conflicts, setConflicts] = useState<GroupConflicts | null>(null)
  const [stored, setStored] = useState<StoredProposals | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [issue, setIssue] = useState<GenerationIssue | null>(null)
  const [notice, setNotice] = useState('')
  const [generation, setGeneration] = useState(0)
  const [progress, setProgress] = useState<GenerationProgress | null>(null)
  const [startedAt, setStartedAt] = useState<number | null>(null)
  const [now, setNow] = useState(() => Date.now())
  const generating = busy || stored?.generating === true
  useEffect(() => {
    const controller = new AbortController()
    Promise.all([getConflicts(tripId, controller.signal), getProposals(tripId, controller.signal)])
      .then(([nextConflicts, nextStored]) => { if (!controller.signal.aborted) { setConflicts(nextConflicts); setStored(nextStored) } })
      .catch((err: unknown) => { if (!controller.signal.aborted) setError(err instanceof Error ? err.message : 'Could not load proposals.') })
    return () => controller.abort()
  }, [tripId, revision, generation])
  // While anyone generates, ask for the live steps and tick the clock.
  useEffect(() => {
    if (!generating) return
    const controller = new AbortController()
    const poll = () => {
      getGenerationProgress(tripId, controller.signal)
        .then((next) => {
          if (controller.signal.aborted) return
          setProgress(next)
          if (next) setStartedAt((value) => value ?? Date.parse(next.started_at))
        })
        .catch(() => undefined) // A missed poll is retried; the steps are a convenience.
    }
    poll()
    const polling = window.setInterval(poll, PROGRESS_POLL_MS)
    const ticking = window.setInterval(() => setNow(Date.now()), 1000)
    return () => { controller.abort(); window.clearInterval(polling); window.clearInterval(ticking) }
  }, [generating, tripId])
  async function generate(regenerate: boolean, tripDays: number | null = null) {
    setBusy(true); setError(''); setIssue(null); setNotice(''); setProgress(null); setStartedAt(Date.now()); setNow(Date.now())
    try {
      const result = await generateProposals(tripId, regenerate, tripDays)
      setStored(result)
      if (result.demo) setNotice('Demo mode: these are saved proposals, not newly generated ones.')
      else if (result.reused) setNotice('Nothing changed, so your recent proposals were kept.')
    } catch (err) {
      setIssue(err instanceof ApiError ? generationIssue(err.detail) : null)
      setError(err instanceof Error ? err.message : 'Could not generate proposals.')
    } finally {
      setBusy(false)
      setStartedAt(null)
      setGeneration((value) => value + 1)
    }
  }
  function act(action: SuggestionAction) {
    if (action === 'retry') { void generate((stored?.proposals.length ?? 0) > 0); return }
    // Dates and destinations are both set on the member's preferences page.
    navigate(`/trips/${tripId}/preferences`)
  }
  const elapsedSeconds = startedAt ? Math.max(0, (now - startedAt) / 1000) : 0
  return <ProposalsView isAdmin={isAdmin} conflicts={conflicts} stored={stored} busy={busy} error={error} notice={notice}
    onGenerate={(regenerate, tripDays) => { void generate(regenerate, tripDays) }} sharedDays={sharedDays} progress={progress} elapsedSeconds={elapsedSeconds} issue={issue} onIssueAction={act} preferencesHref={`/trips/${tripId}/preferences`} />
}
