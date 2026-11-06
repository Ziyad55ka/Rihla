import type { InterestFocus } from './preferences'

export type DiscoveryAnswers = {
  experience: 'culture' | 'beach' | 'adventure' | 'surprise'
  pace: 'relaxed' | 'balanced' | 'active'
  reach: 'nearby' | 'anywhere'
}

export function discoveryInterests(answers: DiscoveryAnswers): { focus: InterestFocus[]; notes: string[] } {
  const focus: Record<DiscoveryAnswers['experience'], InterestFocus[]> = {
    culture: ['landmarks', 'museums_history', 'food'],
    beach: ['beaches_water', 'nature_outdoors'],
    adventure: ['adventure_sports', 'nature_outdoors'],
    surprise: [],
  }
  const pace = { relaxed: 'A relaxed trip with free time.', balanced: 'A balanced mix of activities and rest.', active: 'An active trip with varied experiences.' }
  const reach = { nearby: 'Prefer a nearby destination and shorter travel time when feasible.', anywhere: 'Open to international destinations when feasible.' }
  return { focus: focus[answers.experience], notes: [pace[answers.pace], reach[answers.reach]] }
}
