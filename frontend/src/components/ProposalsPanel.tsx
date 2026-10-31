import { useEffect, useState } from 'react'
import { useLanguage } from '../lib/language'
import { calendarDate } from '../lib/planning'
import { budgetStatusLabels, canPressGenerate, conflictMessages, generateProposals, getConflicts, getProposals, reviewMessages } from '../lib/proposals'
import type { GroupConflicts, StoredProposals } from '../types/proposal'
import '../proposals.css'

type ViewProps = {
  isAdmin: boolean
  conflicts: GroupConflicts | null
  stored: StoredProposals | null
  busy: boolean
  error: string
  notice: string
  onGenerate: (regenerate: boolean) => void
}

export function ProposalsView({ isAdmin, conflicts, stored, busy, error, notice, onGenerate }: ViewProps) {
  const { t, locale } = useLanguage()
  const generating = busy || stored?.generating === true
  const enabled = canPressGenerate(conflicts, generating)
  const proposals = stored?.proposals ?? []
  return <section className="proposals-panel" aria-labelledby="proposals-title">
    <div className="proposals-heading">
      <div><p className="trip-eyebrow">{t('TRIP PROPOSALS')}</p><h2 id="proposals-title">{t('Three ways to go.')}</h2></div>
      {isAdmin && <div className="proposals-actions">
        <button type="button" className="trip-primary" disabled={!enabled} onClick={() => onGenerate(proposals.length > 0)}>
          {generating ? t('Generating proposals…') : proposals.length > 0 ? t('Generate again') : t('Generate proposals')}
        </button>
      </div>}
    </div>
    {conflicts && conflicts.conflicts.length > 0 && <ul className="proposals-conflicts" role="status">
      {conflicts.conflicts.map((category) => <li key={category}>{t(conflictMessages[category])}</li>)}
    </ul>}
    {conflicts?.own_review.map((category) => reviewMessages[category] && <p className="proposals-review" key={category}>{t(reviewMessages[category])}</p>)}
    {generating && <p className="proposals-note" role="status">{t('This can take a few minutes. You can stay on this page.')}</p>}
    {error && <p className="trip-feedback trip-feedback--error" role="alert">{t(error)}</p>}
    {notice && <p className="trip-feedback trip-feedback--success" role="status">{t(notice)}</p>}
    {stored?.needs_regeneration && !generating && <p className="proposals-review" role="status">{t(isAdmin ? 'These proposals have no flights from your departure city. Generate them again to include it.' : 'These proposals have no flights from your departure city. The administrator needs to generate them again.')}</p>}
    {stored && stored.version !== null && !stored.complete && <p className="proposals-note">{t('Some proposals could not pass the checks, so fewer than three are shown.')}</p>}
    {proposals.length > 0 ? <ol className="proposals-list">
      {proposals.map((proposal) => <li className="proposals-card" key={proposal.id}>
        <p className="trip-eyebrow">{t('Option {number}', { number: proposal.option_number.toLocaleString(locale) })}</p>
        <h3>{proposal.title}</h3>
        <p className="proposals-destination">{proposal.destination}</p>
        <p className="proposals-dates">{calendarDate(proposal.start_date, locale)} {t('to')} {calendarDate(proposal.end_date, locale)}</p>
        <span className={`planning-badge${proposal.budget_status === 'within_group_budget' ? ' planning-badge--ready' : ''}`}>{t(budgetStatusLabels[proposal.budget_status])}</span>
      </li>)}
    </ol> : !generating && <p className="proposals-note">{t(isAdmin ? 'No proposals yet. Generate them when the group is ready.' : 'No proposals yet. The administrator generates them when the group is ready.')}</p>}
  </section>
}

export function ProposalsPanel({ tripId, isAdmin, revision }: { tripId: string; isAdmin: boolean; revision: number }) {
  const [conflicts, setConflicts] = useState<GroupConflicts | null>(null)
  const [stored, setStored] = useState<StoredProposals | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [generation, setGeneration] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    Promise.all([getConflicts(tripId, controller.signal), getProposals(tripId, controller.signal)])
      .then(([nextConflicts, nextStored]) => { if (!controller.signal.aborted) { setConflicts(nextConflicts); setStored(nextStored) } })
      .catch((err: unknown) => { if (!controller.signal.aborted) setError(err instanceof Error ? err.message : 'Could not load proposals.') })
    return () => controller.abort()
  }, [tripId, revision, generation])
  async function generate(regenerate: boolean) {
    setBusy(true); setError(''); setNotice('')
    try {
      const result = await generateProposals(tripId, regenerate)
      setStored(result)
      if (result.demo) setNotice('Demo mode: these are saved proposals, not newly generated ones.')
      else if (result.reused) setNotice('Nothing changed, so your recent proposals were kept.')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not generate proposals.')
    } finally {
      setBusy(false)
      setGeneration((value) => value + 1)
    }
  }
  return <ProposalsView isAdmin={isAdmin} conflicts={conflicts} stored={stored} busy={busy} error={error} notice={notice} onGenerate={(regenerate) => { void generate(regenerate) }} />
}
