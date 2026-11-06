import { Plane, PlaneTakeoff } from 'lucide-react'

/** "Go" on a button: a plane taking off, in place of an arrow. Flips for Arabic. */
export function TakeoffIcon({ size = 17 }: { size?: number }) {
  return <PlaneTakeoff className="rihla-go-icon" size={size} strokeWidth={1.6} aria-hidden="true" focusable={false} />
}

/** "Open" on a button: a plane heading out, in place of a diagonal arrow. */
export function FlyIcon({ size = 17 }: { size?: number }) {
  return <Plane className="rihla-go-icon" size={size} strokeWidth={1.6} aria-hidden="true" focusable={false} />
}

/** AI work: a plane with a small spark, so it stays a travel mark. */
export function AiPlaneIcon({ size = 16 }: { size?: number }) {
  return <svg className="details-icon" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
    <path transform="translate(3 3) scale(.86)" d="M17.8 19.2 16 11l3.5-3.5C21 6 21.5 4 21 3c-1-.5-3 0-4.5 1.5L13 8 4.8 6.2c-.5-.1-.9.1-1.1.5l-.3.5c-.2.5-.1 1 .3 1.3L9 12l-2 3H4l-1 1 3 2 2 3 1-1v-3l3-2 3.5 5.3c.3.4.8.5 1.3.3l.5-.2c.4-.3.6-.7.5-1.2z" />
    <path d="M5 1.5v4M3 3.5h4" />
  </svg>
}
