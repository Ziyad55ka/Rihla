import type { Proposal } from '../../types/proposal'

/**
 * Developer 2 (US-11/12): the page's activities section, after travel between cities.
 * ActivitiesPanel on the Ziyad branch can be called from here, reading
 * CityStay.activities. Show nothing until there is data. See docs/developer-2-handoff.md.
 */
export function ActivitiesSection({ proposal }: { proposal: Proposal }) {
  void proposal
  return null
}
