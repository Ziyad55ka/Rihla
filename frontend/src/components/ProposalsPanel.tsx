import { useEffect, useState, type MouseEvent } from 'react'
import { GENERATE_STEP_MS, generateMessages } from '../lib/aiStatus'
import { useLanguage } from '../lib/language'
import { navigate } from '../lib/navigation'
import { calendarDate } from '../lib/planning'
import { placeName } from '../lib/places'
import { ApiError } from '../lib/http'
import { budgetStatusLabels, canPressGenerate, conflictMessages, generateProposals, generationIssue, getConflicts, getGenerationProgress, getProposals, PROGRESS_POLL_MS, proposalTitle, reviewMessages } from '../lib/proposals'
import type { GenerationIssue, GenerationProgress, GroupConflicts, Proposal, StoredProposals, SuggestionAction } from '../types/proposal'
import { AiStatus } from './AiStatus'
import { GenerationIssueCard } from './GenerationIssueCard'
import { GenerationProgressView } from './GenerationProgress'
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
  onGenerate: (regenerate: boolean) => void
  progress?: GenerationProgress | null
  elapsedSeconds?: number
  issue?: GenerationIssue | null
  onIssueAction?: (action: SuggestionAction) => void
}

export function ProposalsView({ isAdmin, conflicts, stored, busy, error, notice, onGenerate, progress = null, elapsedSeconds = 0, issue = null, onIssueAction = () => undefined }: ViewProps) {
  const { t, locale, language } = useLanguage()
  const generating = busy || stored?.generating === true
  const enabled = canPressGenerate(conflicts, generating)
  const proposals = stored?.proposals ?? []
  return <section className="proposals-panel" aria-labelledby="proposals-title">
    <div className="proposals-heading">
      <div><p className="trip-eyebrow">{t('TRIP PROPOSALS')}</p><h2 id="proposals-title">{t('Three ways to go.')}</h2></div>
      {isAdmin && <div className="proposals-actions">
        <button type="button" className="trip-primary" disabled={!enabled} onClick={() => onGenerate(proposals.length > 0)}>
          {generating ? <AiStatus messages={progress ? ['Generating proposals…'] : generateMessages} stepMs={GENERATE_STEP_MS} /> : proposals.length > 0 ? t('Generate again') : t('Generate proposals')}
        </button>
      </div>}
    </div>
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
      {proposals.map((proposal) => <li className="proposals-card" key={proposal.id}>
        <PlacePhoto image={proposal.image} place={placeName(proposal.destination, language, proposal.destination_ar)} />
        <p className="trip-eyebrow">{t('Option {number}', { number: proposal.option_number.toLocaleString(locale) })}</p>
        <h3><a href={proposalPath(proposal)} onClick={(event) => openProposal(event, proposal)}><bdi>{proposalTitle(proposal, language)}</bdi></a></h3>
        <p className="proposals-destination"><bdi>{placeName(proposal.destination, language, proposal.destination_ar)}</bdi></p>
        <p className="proposals-dates">{calendarDate(proposal.start_date, locale)} {t('to')} {calendarDate(proposal.end_date, locale)}</p>
        <span className={`planning-badge${proposal.budget_status === 'within_group_budget' ? ' planning-badge--ready' : ''}`}>{t(budgetStatusLabels[proposal.budget_status])}</span>
        <a className="trip-secondary proposals-open" href={proposalPath(proposal)} onClick={(event) => openProposal(event, proposal)}>{t('View details')}</a>
      </li>)}
    </ol> : !generating && !issue && <p className="proposals-note">{t(isAdmin ? 'No proposals yet. Generate them when the group is ready.' : 'No proposals yet. The administrator generates them when the group is ready.')}</p>}
  </section>
}

export function ProposalsPanel({ tripId, isAdmin, revision }: { tripId: string; isAdmin: boolean; revision: number }) {
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
  async function generate(regenerate: boolean) {
    setBusy(true); setError(''); setIssue(null); setNotice(''); setProgress(null); setStartedAt(Date.now()); setNow(Date.now())
    try {
      const result = await generateProposals(tripId, regenerate)
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
    onGenerate={(regenerate) => { void generate(regenerate) }} progress={progress} elapsedSeconds={elapsedSeconds} issue={issue} onIssueAction={act} />
}
