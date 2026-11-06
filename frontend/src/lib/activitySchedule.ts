import type { Activity, CityStay, Proposal } from '../types/proposal'
import { isActivitySuitable } from './activities'

export interface DayVisit { activity: Activity; city: CityStay }
export interface ActivityDay { date: string; visits: DayVisit[]; travel?: boolean }
const dayMs = 86_400_000

/** One admission/visit per selected id. Dated events keep their real date. */
export function buildActivitySchedule(proposal: Proposal, ids: string[]) {
  const first = Date.parse(`${proposal.start_date}T00:00:00Z`)
  const last = Date.parse(`${proposal.end_date}T00:00:00Z`)
  const days: ActivityDay[] = []
  if (!Number.isFinite(first) || !Number.isFinite(last) || last < first || last - first > dayMs * 366) return { days, unscheduled: ids.length }
  const legs = proposal.flights[0]?.legs ?? []
  const arrivalDate = legs.find(leg => leg.direction === 'outbound')?.arrival_time?.slice(0, 10)
  const returnTime = legs.find(leg => leg.direction === 'return')?.departure_time
  const firstVisitDay = arrivalDate && /^\d{4}-\d{2}-\d{2}$/.test(arrivalDate) ? Math.max(first, Date.parse(arrivalDate)) : first
  const earlyReturn = returnTime?.match(/^\d{4}-\d{2}-\d{2}T(\d{2}):/)
  const lastVisitDay = earlyReturn && Number(earlyReturn[1]) < 12 ? last - dayMs : last
  for (let at = first; at <= last; at += dayMs) days.push({ date: new Date(at).toISOString().slice(0, 10), visits: [], travel: at < firstVisitDay || at > lastVisitDay })
  const byDate = new Map(days.map(day => [day.date, day]))
  const selected = new Set(ids), seen = new Set<string>()
  let arrival = first
  let unscheduled = 0
  for (const city of [...proposal.cities].sort((a, b) => a.order - b.order)) {
    const departure = arrival + city.nights * dayMs
    const choices: DayVisit[] = []
    for (const activity of city.activities ?? []) {
      if (!selected.has(activity.id) || seen.has(activity.id)) continue
      seen.add(activity.id)
      if (!isActivitySuitable(proposal, city, activity)) { unscheduled++; continue }
      const fixed = activity.scheduled_date.value
      if (fixed) {
        const day = byDate.get(fixed)
        if (day) day.visits.push({ activity, city }); else unscheduled++
      } else choices.push({ activity, city })
    }
    // Checkout is a transfer day except at the final stay. Each visit appears
    // once, even when a city spans many days or two cities share a transfer day.
    const available = days.filter(day => {
      const at = Date.parse(day.date)
      return !day.travel && at >= arrival && (at < departure || (departure >= last && at <= last) || city.nights === 0 && at === arrival)
    })
    for (const visit of choices) {
      const restaurant = visit.activity.category === 'restaurant'
      const score = (day: ActivityDay) => day.visits.filter(v => (v.activity.category === 'restaurant') === restaurant).length * 100 + day.visits.length
      const day = [...available].sort((a, b) => score(a) - score(b) || a.date.localeCompare(b.date))[0]
      if (day) day.visits.push(visit); else unscheduled++
    }
    arrival = departure
  }
  unscheduled += [...selected].filter(id => !seen.has(id)).length
  return { days, unscheduled }
}

/** Per visiting day: up to two sights or activities and one place to eat. */
const PER_DAY = { visits: 2, meals: 1 }

/**
 * Fills the trip's free days from the suggestions, best match to the group's
 * interests first. Only undated suggestions with a photo that suit their stay;
 * the member's own choices stay. Days with too few suggestions stay free time.
 */
export function suggestDailyPlan(proposal: Proposal, keep: string[], hasPhoto: (activity: Activity) => boolean): string[] {
  const chosen = new Set(keep)
  const { days } = buildActivitySchedule(proposal, [])
  let arrival = Date.parse(`${proposal.start_date}T00:00:00Z`)
  const last = Date.parse(`${proposal.end_date}T00:00:00Z`)
  for (const city of [...proposal.cities].sort((a, b) => a.order - b.order)) {
    const departure = arrival + city.nights * dayMs
    const visiting = days.filter(day => {
      const at = Date.parse(day.date)
      return !day.travel && at >= arrival && (at < departure || (departure >= last && at <= last))
    }).length
    const ranked = (city.activities ?? [])
      .filter(activity => !activity.scheduled_date.value && hasPhoto(activity) && isActivitySuitable(proposal, city, activity))
      .sort((a, b) => (b.fits?.length ?? 0) - (a.fits?.length ?? 0))
    const already = (restaurant: boolean) => ranked.filter(a => chosen.has(a.id) && (a.category === 'restaurant') === restaurant).length
    for (const [restaurant, perDay] of [[false, PER_DAY.visits], [true, PER_DAY.meals]] as const) {
      let room = visiting * perDay - already(restaurant)
      for (const activity of ranked) {
        if (room <= 0) break
        if ((activity.category === 'restaurant') !== restaurant || chosen.has(activity.id)) continue
        chosen.add(activity.id); room--
      }
    }
    arrival = departure
  }
  return [...chosen]
}
