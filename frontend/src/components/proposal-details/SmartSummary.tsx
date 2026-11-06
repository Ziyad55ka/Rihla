import { useLanguage } from '../../lib/language'
import type { Proposal } from '../../types/proposal'
import { Hint } from './Hint'
import { SparkleIcon } from './icons'
import { nightsLabel } from './nights'

const budgetPoints = {
  within_group_budget: 'Fits the group budget',
  includes_unconfirmed: 'Fits the group budget so far, with some prices to confirm',
  over_group_budget: 'Over the group budget',
}

/** Facts from the proposal's own data: its length, cities and budget status. */
export function SmartSummary({ proposal, stale = false }: { proposal: Proposal; stale?: boolean }) {
  const { t, language, locale } = useLanguage()
  const nights = proposal.cities.reduce((sum, stay) => sum + stay.nights, 0)
  const length = nightsLabel(nights, language, t, locale)
  const points = [
    length,
    proposal.cities.length === 1 ? t('One city') : proposal.cities.length === 2 ? t('Two cities') : t('{count} cities', { count: proposal.cities.length.toLocaleString(locale) }),
    t(stale ? 'Regenerate to recheck budget and preferences' : budgetPoints[proposal.budget_status]),
  ]
  return <section className="details-smart" aria-labelledby="details-smart">
    <h2 id="details-smart" className="details-smart-title"><span className="details-smart-spark"><SparkleIcon /></span>{t('Rihla’s smart summary')}<Hint text={t('Written from this proposal’s details. It never uses any member’s private information.')} /></h2>
    <ul>{points.map((point) => <li key={point}><bdi>{point}</bdi></li>)}</ul>
  </section>
}
