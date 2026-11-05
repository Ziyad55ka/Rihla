import { useLanguage } from '../../lib/language'
import type { CompatibilityCheck, CompatibilityStatus, CompatibilityTopic, Proposal, ProposalFit } from '../../types/proposal'
import { Hint } from './Hint'
import { MatchTitleIcon, MetIcon, UnmetIcon, UnverifiedIcon, WarningIcon } from './icons'
import { SectionTitle } from './SectionTitle'

const topicLabels: Record<CompatibilityTopic, string> = {
  destinations: 'Destinations',
  interests: 'Interests',
  flights: 'Flights',
  accommodation: 'Accommodation',
  budget: 'Group budget',
  dates: 'Shared travel dates',
}

const importanceLabels: Record<CompatibilityCheck['importance'], string> = {
  Essential: 'Essential',
  Flexible: 'Flexible',
  Required: 'Always required',
}

const resultLabels: Record<CompatibilityStatus, string> = {
  met: 'Met',
  unverified: 'Not verified',
  unmet: 'Not met',
}

const resultIcons = { met: MetIcon, unverified: UnverifiedIcon, unmet: UnmetIcon }
// Problems first, then the importance, so an Essential that is not met leads.
const statusOrder: CompatibilityStatus[] = ['unmet', 'unverified', 'met']
const importanceOrder: CompatibilityCheck['importance'][] = ['Essential', 'Required', 'Flexible']

function sorted(checks: CompatibilityCheck[]) {
  return [...checks].sort((a, b) => statusOrder.indexOf(a.status) - statusOrder.indexOf(b.status)
    || importanceOrder.indexOf(a.importance) - importanceOrder.indexOf(b.importance))
}

/** US-15: which requirements this proposal meets, which are not met or not verified, and its trade-offs. */
export function CompatibilitySection({ proposal }: { proposal: Proposal }) {
  const { t, locale, language } = useLanguage()
  const checks = sorted(proposal.compatibility ?? [])
  const essentialProblems = checks.filter((item) => item.importance === 'Essential' && item.status !== 'met')
  const metCount = checks.filter((item) => item.status === 'met').length
  return <section aria-labelledby="details-match">
    <SectionTitle id="details-match" icon={<MatchTitleIcon />} title={t('How it matches the group')} hint={<Hint text={t('Grouped by topic. It never shows anyone’s own preferences or who asked for what.')} />} />
    <div className="details-card details-match">
      {checks.length === 0
        ? <p className="details-hint">{t('This proposal was generated before match details were added. Generate the proposals again to see them.')}</p>
        : <>
          {essentialProblems.length > 0 && <p className="details-budget details-budget--over" role="status">
            <WarningIcon /> <span>{t('Check these Essential requirements yourself before deciding: {topics}', { topics: essentialProblems.map((item) => `${t(topicLabels[item.topic])} (${t(resultLabels[item.status])})`).join(language === 'ar' ? '، ' : ', ') })}</span>
          </p>}
          <p className="details-hint">{t('{met} of {total} checks met', { met: metCount.toLocaleString(locale), total: checks.length.toLocaleString(locale) })}</p>
          <ul className="details-match-list">
            {checks.map((item) => {
              const Icon = resultIcons[item.status]
              return <li key={`${item.topic}-${item.importance}`} className={`details-match-row details-match-row--${item.status}`}>
                <Icon />
                <span className="details-match-topic">{t(topicLabels[item.topic])}</span>
                <span className="details-chip details-chip--plain">{t(importanceLabels[item.importance])}</span>
                <span className={`planning-badge${item.status === 'met' ? ' planning-badge--ready' : item.status === 'unmet' ? ' planning-badge--conflict' : ' details-badge--neutral'}`}>{t(resultLabels[item.status])}</span>
              </li>
            })}
          </ul>
          <dl className="details-match-legend">
            <div><dt>{t('Met')}</dt><dd>{t('Rihla checked this against the proposal’s details.')}</dd></div>
            <div><dt>{t('Not verified')}</dt><dd>{t('The AI reported it as met, but Rihla could not check it. Review it yourself.')}</dd></div>
            <div><dt>{t('Not met')}</dt><dd>{t('The proposal does not meet it. See the trade-offs below.')}</dd></div>
          </dl>
        </>}
      <h3 className="details-match-subtitle">{t('Trade-offs')}</h3>
      {proposal.flexible_adjustments.length === 0
        ? <p className="details-hint">{t('No trade-offs: every Flexible preference was met.')}</p>
        : <ul className="details-tradeoffs">
          {proposal.flexible_adjustments.map((item, index) => <li key={index}>
            <strong>{t(topicLabels[item.category])}:</strong> <bdi>{item.explanation}</bdi>
          </li>)}
        </ul>}
      {proposal.fit ? <FitSummary fit={proposal.fit} /> : <p className="details-hint">{t('Rihla does not give proposals a score. Compare the checks and trade-offs above.')}</p>}
    </div>
  </section>
}

/** US-15-AC03: the score and the criteria behind it, with nobody's own result. */
function FitSummary({ fit }: { fit: ProposalFit }) {
  const { t, locale } = useLanguage()
  const percent = (value: number) => (value / 100).toLocaleString(locale, { style: 'percent' })
  return <div className="details-fit">
    <h3 className="details-match-subtitle">{t('Fit score')}</h3>
    <dl className="details-fit-scores">
      <div><dt>{t('Least-satisfied member')}</dt><dd>{percent(fit.least_satisfied_percent)}</dd></div>
      <div><dt>{t('Group average')}</dt><dd>{percent(fit.group_percent)}</dd></div>
    </dl>
    <p className="details-hint">{t('Each member is scored on their own requirements: Essential ones count three times, Flexible ones once, plus the shared dates and the group budget. Met counts fully and Not verified counts half. Proposals are ordered by the least-satisfied member, so no one is left behind. No one’s own score is shown.')}</p>
  </div>
}
