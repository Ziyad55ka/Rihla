import { useLanguage } from '../../lib/language'
import { isInternalSource, safeLink } from '../../lib/proposals'
import type { InfoStatus, ProposalSource } from '../../types/proposal'
import { StatusBadge } from './values'

const statuses: InfoStatus[] = ['Sourced', 'Estimated', 'Unconfirmed', 'Not available']

function SourceList({ title, sources }: { title: string; sources: ProposalSource[] }) {
  if (sources.length === 0) return null
  return <>
    <h3>{title}</h3>
    <ol className="details-sources">{sources.map((source) => {
      const link = safeLink(source.url)
      return <li key={source.id}>{link ? <a href={link} target="_blank" rel="noopener noreferrer"><bdi>{source.title}</bdi></a> : <bdi>{source.title}</bdi>}</li>
    })}</ol>
  </>
}

export function SourcesSection({ sources }: { sources: ProposalSource[] }) {
  const { t } = useLanguage()
  const shown = sources.filter((source) => !isInternalSource(source))
  const booking = shown.filter((source) => source.kind === 'booking')
  const ideas = shown.filter((source) => source.kind !== 'booking')
  return <section aria-labelledby="details-sources">
    <h2 id="details-sources">{t('Sources')}</h2>
    <div className="details-card">
      <SourceList title={t('Booking and price sources')} sources={booking} />
      <SourceList title={t('Sources for ideas')} sources={ideas} />
      {shown.length === 0 && <p className="details-hint">{t('No sources are listed for this proposal.')}</p>}
      <div className="details-legend"><span>{t('Status guide:')}</span>{statuses.map((status) => <StatusBadge key={status} status={status} short />)}</div>
    </div>
  </section>
}
