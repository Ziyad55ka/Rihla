export type HotelStars = 3 | 4 | 5
export type HotelPreference = { stars: HotelStars | null; lower: HotelStars[]; notes: string }

/** One set of accepted classes, encoded compatibly with existing saved preferences. */
export function toggleHotelClass(hotel: HotelPreference, stars: HotelStars): HotelPreference {
  const accepted = hotel.stars === null ? [] : [hotel.stars, ...hotel.lower]
  const next = accepted.includes(stars) ? accepted.filter(value => value !== stars) : [...accepted, stars]
  const preferred = next.length ? Math.max(...next) as HotelStars : null
  return { stars: preferred, lower: next.filter(value => value !== preferred).sort(), notes: hotel.notes }
}
export function parseAccommodation(value: string): HotelPreference {
  const match = /^stay:stars=([345]);lower=([345,]*);notes:([\s\S]*)$/.exec(value)
  if (!match) return { stars: null, lower: [], notes: value }
  const stars = Number(match[1]) as HotelStars
  const lower = [...new Set(match[2].split(',').filter(Boolean).map(Number))].filter(n => n < stars) as HotelStars[]
  return { stars, lower, notes: match[3] }
}
export function formatAccommodation({ stars, lower, notes }: HotelPreference): string {
  return stars === null ? notes : `stay:stars=${stars};lower=${[...new Set(lower)].filter(n => n < stars).sort().join(',')};notes:${notes}`
}
