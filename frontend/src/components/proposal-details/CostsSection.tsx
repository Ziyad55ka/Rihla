import { useState } from 'react'
import { useLanguage } from '../../lib/language'
import type { CostAmount, CostAssumption, CostCategory, OwnBudget, ProposalCosts, RoomPlan } from '../../types/proposal'
import { Hint } from './Hint'
import { CostsTitleIcon, MetIcon, UnverifiedIcon, WarningIcon } from './icons'
import { SectionTitle } from './SectionTitle'
import { useSar } from './useSar'
import { StatusBadge } from './values'

const categoryLabels: Record<CostCategory, string> = {
  flights: 'Flights',
  accommodation: 'Accommodation',
  transport: 'Travel between cities',
  activities: 'Selected activities',
  meals: 'Meals and other expenses',
}

const roomLabels: Record<RoomPlan, string> = {
  single: 'One person per room',
  shared: 'Two people per room',
}

const assumptionText: Record<CostAssumption, string> = {
  rooms_single: 'One person per room: each member pays for a whole room. This is how the group budget is checked, so it errs high.',
  rooms_shared: 'Two people per room: rooms are shared and their cost is split evenly across the group.',
  flights_own_city: 'Flights are the round-trip price from your own departure city. Other members may pay a different fare.',
  flights_one_way: 'Only the outbound flight is priced. The return flight is not included yet.',
  flights_missing: 'No flights from your departure city were found, so flights are not counted.',
  meals_allowance: 'Meals and small expenses use a general daily allowance per person. It is not from a source.',
  activities_not_included: 'Selected activities are not added to these totals yet.',
  group_total_all_cities: 'The group total adds every member’s own flights and the shared costs for everyone.',
  group_total_unavailable: 'The group total could not be worked out right now.',
  prices_may_change: 'All prices are estimates from the last check and may change before booking.',
}

const budgetMessages: Record<OwnBudget, string> = {
  within: 'Within your budget',
  over: 'Over your budget by {amount}',
  unconfirmed: 'Within your budget on the known prices, but some prices are unconfirmed or missing',
  unknown: 'We could not check this against your budget',
}

function Amount({ amount }: { amount: CostAmount }) {
  const { t } = useLanguage()
  const sar = useSar()
  if (amount.amount_sar === null) return <span className="details-value">— <StatusBadge status="Not available" /></span>
  const value = sar(amount.amount_sar)
  return <span className="details-value">
    <span>{amount.status === 'Sourced' ? value : t('About {amount}', { amount: value })}</span>
    <StatusBadge status={amount.status} />
    {amount.partial && <span className="details-hint">{t('Some prices are missing, so the real cost is higher.')}</span>}
  </span>
}

function BudgetCheck({ status, overBy }: { status: OwnBudget; overBy: string | null }) {
  const { t } = useLanguage()
  const sar = useSar()
  const Icon = status === 'within' ? MetIcon : status === 'over' ? WarningIcon : UnverifiedIcon
  return <p className={`details-budget details-budget--${status}`} role={status === 'over' ? 'alert' : 'status'}>
    <Icon /> <span>{t(budgetMessages[status], { amount: overBy ? sar(overBy) : '' })}</span>
    <Hint text={t('Only you see this. Your budget is never shown to other members.')} />
  </p>
}

/** US-13: the member's own costs, the group total, the assumptions and a budget warning. */
export function CostsSection({ costs }: { costs?: ProposalCosts }) {
  const { t, locale } = useLanguage()
  const [rooms, setRooms] = useState<RoomPlan>('single')
  if (!costs) return <section aria-labelledby="details-costs">
    <SectionTitle id="details-costs" icon={<CostsTitleIcon />} title={t('Costs and budget')} />
    <p className="details-card details-hint">{t('The cost breakdown is not available right now. Try again later.')}</p>
  </section>
  const plan = costs.scenarios.find((item) => item.rooms === rooms) ?? costs.scenarios[0]
  return <section aria-labelledby="details-costs">
    <SectionTitle id="details-costs" icon={<CostsTitleIcon />} title={t('Costs and budget')} hint={<Hint text={t('Estimated costs for this proposal. Prices come from the sections above, and every estimate is labelled.')} />} />
    <div className="details-card details-costs">
      <BudgetCheck status={plan.own_budget} overBy={plan.over_by_sar} />
      {costs.scenarios.length > 1 && <fieldset className="details-rooms">
        <legend>{t('Rooms')}</legend>
        {costs.scenarios.map((item) => <label key={item.rooms}>
          <input type="radio" name="details-rooms" value={item.rooms} checked={plan.rooms === item.rooms} onChange={() => setRooms(item.rooms)} />
          {t(roomLabels[item.rooms])}
        </label>)}
      </fieldset>}
      <table className="details-cost-table">
        <caption>{t('Per person, for {days} days and {nights} nights', { days: costs.days.toLocaleString(locale), nights: costs.nights.toLocaleString(locale) })}</caption>
        <thead><tr><th scope="col">{t('Cost')}</th><th scope="col">{t('Per person')}</th></tr></thead>
        <tbody>
          {plan.lines.map((line) => <tr key={line.category} className={line.counted ? undefined : 'is-muted'}>
            <th scope="row">{t(categoryLabels[line.category])}</th>
            <td>{line.counted ? <Amount amount={line.per_person} /> : <span className="details-hint">{t('Not added to the total yet')}</span>}</td>
          </tr>)}
        </tbody>
        <tfoot>
          <tr><th scope="row">{t('Total per person')}</th><td><Amount amount={plan.per_person_total} /></td></tr>
          <tr><th scope="row">{t('Total for the group')}</th><td>{plan.group_total ? <Amount amount={plan.group_total} /> : <span className="details-hint">{t('Not available right now')}</span>}</td></tr>
        </tfoot>
      </table>
      <details className="details-assumptions" open>
        <summary>{t('How this is calculated')}</summary>
        <ul>{costs.assumptions.map((item) => <li key={item}>{t(assumptionText[item])}</li>)}</ul>
      </details>
    </div>
  </section>
}
