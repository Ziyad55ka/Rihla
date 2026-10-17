interface StatusBadgeProps {
  tone: 'success' | 'warning' | 'neutral'
  children: React.ReactNode
}

export function StatusBadge({ tone, children }: StatusBadgeProps) {
  return <span className={`status-badge status-badge--${tone}`}><span aria-hidden="true" />{children}</span>
}
