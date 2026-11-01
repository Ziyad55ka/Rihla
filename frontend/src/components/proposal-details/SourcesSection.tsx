import { useLanguage } from '../../lib/language'
import { safeLink } from '../../lib/proposals'
import type { InfoStatus, Proposal } from '../../types/proposal'
import { Hint } from './Hint'
import { ExternalIcon, SourcesTitleIcon } from './icons'
import { SectionTitle } from './SectionTitle'
import { StatusBadge } from './values'

const statusMeanings: Record<InfoStatus, string> = {
  Sourced: 'The seller gave this exact price at the last check. It can still change before you book.',
  Estimated: 'Worked out from a source, for example a converted currency or a “from” price. Not a guaranteed price.',
  Unconfirmed: 'Not clear from any source, or a general estimate. Check it before booking.',
  'Not available': 'Unknown. It is not counted as free, and totals that need it are marked as missing prices.',
}

const kindLabels = { booking: 'Booking site', ideas: 'Ideas and guides' } as const

function host(url: string): string {
  try { return new URL(url).hostname.replace(/^www\./, '') } catch { return url }
}

/** US-14: where the information came from, when it was checked, and what each label means. */
export function SourcesSection({ proposal, generatedAt }: { proposal: Proposal; generatedAt: string | null }) {
  const { t, locale } = useLanguage()
  // Only classified web pages. Flight notes and unclassified entries can name internal
  // services, and flights show their own check time above.
  const sources = proposal.sources.filter((item) => item.kind === 'booking' || item.kind === 'ideas')
  const checked = (value?: string | null) => {
    const time = value ?? generatedAt
    return time ? new Date(time).toLocaleString(locale, { dateStyle: 'medium', timeStyle: 'short' }) : null
  }
  return <section aria-labelledby="details-sources">
    <SectionTitle id="details-sources" icon={<SourcesTitleIcon />} title={t('Sources and reliability')} hint={<Hint text={t('Each value above shows its label. Flight and hotel prices also show when they were last checked.')} />} />
    <div className="details-card details-sources">
      <dl className="details-status-legend">
        {(Object.keys(statusMeanings) as InfoStatus[]).map((status) => <div key={status}>
          <dt><StatusBadge status={status} /></dt>
          <dd>{t(statusMeanings[status])}</dd>
        </div>)}
      </dl>
      <h3 className="details-match-subtitle">{t('Sources used')}</h3>
      {sources.length === 0
        ? <p className="details-hint">{t('No web sources were cited for this proposal. Values without a source are marked Unconfirmed or Not available.')}</p>
        : <ul className="details-source-list">
          {sources.map((source) => {
            const link = safeLink(source.url)
            const time = checked(source.retrieved_at)
            return <li key={source.id}>
              {link
                ? <a className="details-text-link" href={link} target="_blank" rel="noopener noreferrer"><bdi>{source.title}</bdi> <ExternalIcon /></a>
                : <bdi>{source.title}</bdi>}
              <span className="details-hint"><bdi>{host(source.url)}</bdi>{source.kind && <> · {t(kindLabels[source.kind as keyof typeof kindLabels])}</>}</span>
              <span className="details-hint">{time ? t('Checked {time}', { time }) : t('Check time not recorded')}</span>
            </li>
          })}
        </ul>}
      <p className="details-hint">{t('A source shows what was found at that time. It does not confirm availability.')}</p>
    </div>
  </section>
}
