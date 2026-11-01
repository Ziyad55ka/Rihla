// Decorative only: the words beside each icon carry the meaning.
function Icon({ path }: { path: string }) {
  return <svg className="details-icon" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false"><path d={path} /></svg>
}

export const ClockIcon = () => <Icon path="M12 7v5l3 2M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
export const CheckIcon = () => <Icon path="m5 12 5 5L20 7" />
export const InfoIcon = () => <Icon path="M12 11v5M12 8h.01M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
export const BagIcon = () => <Icon path="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M5 7h14a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V8a1 1 0 0 1 1-1Z" />
export const SwapIcon = () => <Icon path="M7 16V4M7 4 3 8M7 4l4 4M17 8v12M17 20l4-4M17 20l-4-4" />
export const TrainIcon = () => <Icon path="M8 3h8a3 3 0 0 1 3 3v9a3 3 0 0 1-3 3H8a3 3 0 0 1-3-3V6a3 3 0 0 1 3-3ZM5 11h14M9 15h.01M15 15h.01M8 21l1.5-3M16 21l-1.5-3" />
export const BusIcon = () => <Icon path="M6 4h12a2 2 0 0 1 2 2v11H4V6a2 2 0 0 1 2-2ZM4 11h16M7.5 20a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3ZM16.5 20a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3Z" />
export const PlaneIcon = () => <Icon path="M21 15v-2l-8-5V4a1.5 1.5 0 0 0-3 0v4l-7 5v2l7-2v4l-2 1.5V21l3.5-1 3.5 1v-1.5L13 18v-5l8 2Z" />
export const CarIcon = () => <Icon path="M5 16 6.5 9.5A2 2 0 0 1 8.4 8h7.2a2 2 0 0 1 1.9 1.5L19 16M4 16h16v3H4ZM7 19v1.5M17 19v1.5" />
export const FerryIcon = () => <Icon path="M12 3v5M7 8h10l2 6H5l2-6ZM3 18c2 1.5 4 1.5 6 0s4-1.5 6 0 4 1.5 6 0" />
export const RouteIcon = () => <Icon path="M6 19a2 2 0 1 0 0-4 2 2 0 0 0 0 4ZM18 9a2 2 0 1 0 0-4 2 2 0 0 0 0 4ZM8 17h7a3 3 0 0 0 0-6H9a3 3 0 0 1 0-6h7" />
