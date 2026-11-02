import type { ReactNode } from 'react'

export function SectionTitle({ id, icon, title, hint }: { id: string; icon: ReactNode; title: string; hint?: ReactNode }) {
  return <h2 id={id} className="details-title"><span className="details-title-icon">{icon}</span><span>{title}</span>{hint}</h2>
}
