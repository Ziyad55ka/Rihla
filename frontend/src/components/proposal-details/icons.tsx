import { ArrowLeft, ArrowRight, BedDouble, Bus, Car, Check, ChevronDown, CircleAlert, CircleCheck, CircleHelp, CircleX, Clock, ExternalLink, Info, Library, ListChecks, Luggage, Plane, RefreshCw, Route, Ship, TrainFront, Users, Wallet } from 'lucide-react'

// One library, one line weight. The words beside each icon carry the meaning.
const look = { className: 'details-icon', strokeWidth: 1.75, 'aria-hidden': true, focusable: false } as const

export function ClockIcon() { return <Clock {...look} size={16} /> }
export function CheckIcon() { return <Check {...look} size={16} /> }
export function InfoIcon() { return <Info {...look} size={16} /> }
export function BagIcon() { return <Luggage {...look} size={16} /> }
export function UsersIcon() { return <Users {...look} size={16} /> }
export function RefreshIcon() { return <RefreshCw {...look} size={16} /> }
export function ExternalIcon() { return <ExternalLink {...look} size={14} /> }
export function ChevronIcon() { return <ChevronDown {...look} size={16} /> }
export { AiPlaneIcon as SparkleIcon } from '../FlightIcons'
export function FlightsTitleIcon() { return <Plane {...look} size={20} /> }
export function StaysTitleIcon() { return <BedDouble {...look} size={20} /> }
export function RouteTitleIcon() { return <Route {...look} size={20} /> }
export function TrainIcon() { return <TrainFront {...look} size={16} /> }
export function BusIcon() { return <Bus {...look} size={16} /> }
export function PlaneIcon() { return <Plane {...look} size={16} /> }
export function CarIcon() { return <Car {...look} size={16} /> }
export function FerryIcon() { return <Ship {...look} size={16} /> }
export function RouteIcon() { return <Route {...look} size={16} /> }
export function CostsTitleIcon() { return <Wallet {...look} size={20} /> }
export function MatchTitleIcon() { return <ListChecks {...look} size={20} /> }
export function SourcesTitleIcon() { return <Library {...look} size={20} /> }
export function MetIcon() { return <CircleCheck {...look} size={16} /> }
export function UnverifiedIcon() { return <CircleHelp {...look} size={16} /> }
export function UnmetIcon() { return <CircleX {...look} size={16} /> }
export function WarningIcon() { return <CircleAlert {...look} size={16} /> }

/** Points the way the page reads: left in English and right in Arabic. */
export function BackIcon({ rtl }: { rtl: boolean }) {
  const Shape = rtl ? ArrowRight : ArrowLeft
  return <Shape {...look} size={16} />
}

/** Points the way a trip reads: right in English and left in Arabic. */
export function ForwardIcon({ rtl }: { rtl: boolean }) {
  const Shape = rtl ? ArrowLeft : ArrowRight
  return <Shape {...look} size={16} />
}
