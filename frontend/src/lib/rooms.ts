// A choice for reading the page only. It is not saved, and nobody else sees it.
export type RoomChoice = 'own' | 'shared'

export function roomsFor(choice: RoomChoice, adults: number): number {
  return choice === 'own' ? adults : Math.max(Math.ceil(adults / 2), 1)
}

/** The group's size is already in the Booking.com search. Null when it is not. */
export function adultsInLink(url: string | null): number | null {
  if (!url) return null
  try {
    const adults = Number(new URL(url).searchParams.get('group_adults'))
    return Number.isInteger(adults) && adults > 0 ? adults : null
  } catch { return null }
}

export function linkWithRooms(url: string, rooms: number): string {
  try {
    const link = new URL(url)
    link.searchParams.set('no_rooms', String(rooms))
    return link.toString()
  } catch { return url }
}

/** One person's share of a room price, when the group fills this many rooms. */
export function sharePerPerson(perRoom: number, rooms: number, adults: number): number {
  return Math.round(perRoom * rooms / adults)
}

/** The member's own accommodation preference, or sharing when it does not say. */
export function defaultRoomChoice(preference?: string | null): RoomChoice {
  return /single|private|own room|alone|غرفة (خاصة|مفردة|لوحد)|لحال|لوحدي/i.test(preference ?? '') ? 'own' : 'shared'
}
