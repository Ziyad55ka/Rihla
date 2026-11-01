import { useLanguage } from '../../lib/language'
import { safeLink } from '../../lib/proposals'
import type { InfoStatus, ProposalSource } from '../../types/proposal'
import { StatusBadge } from './values'

const statuses: InfoStatus[] = ['Sourced', 'Estimated', 'Unconfirmed', 'Not available']

export function SourcesSection({ sources }: { sources: ProposalSource[] }) {
  const { t } = useLanguage()
  return <section aria-labelledby="details-sources">
    <h2 id="details-sources">{t('Sources')}</h2>
    <div className="details-card">
      {sources.length > 0
        ? <ol className="details-sources">{sources.map((source) => {
          const link = safeLink(source.url)
          return <li key={source.id}>{link ? <a href={link} target="_blank" rel="noopener noreferrer"><bdi>{source.title}</bdi></a> : <bdi>{source.title}</bdi>}</li>
        })}</ol>
        : <p className="details-hint">{t('No sources are listed for this proposal.')}</p>}
      <div className="details-legend"><span>{t('Status guide:')}</span>{statuses.map((status) => <StatusBadge key={status} status={status} short />)}</div>
    </div>
  </section>
}
