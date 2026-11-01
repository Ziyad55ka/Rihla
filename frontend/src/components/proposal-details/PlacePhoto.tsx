import { useState } from 'react'
import { useLanguage } from '../../lib/language'
import { safeLink } from '../../lib/proposals'
import type { PlaceImage } from '../../types/proposal'

/** A city photo with its credit. No photo, or a broken one, shows the designed panel. */
export function PlacePhoto({ image, place, variant = 'card' }: { image?: PlaceImage | null; place: string; variant?: 'card' | 'hero' }) {
  const { t } = useLanguage()
  const [failed, setFailed] = useState(false)
  const url = !failed && image ? safeLink(image.url) : null
  const source = image ? safeLink(image.source_url) : null
  return <figure className={`details-photo details-photo--${variant}`}>
    {url
      ? <img src={url} alt={variant === 'hero' ? '' : t('Photo of {place}', { place })} loading="lazy" decoding="async" referrerPolicy="no-referrer" onError={() => setFailed(true)} />
      : <span className="details-photo-empty" aria-hidden="true"><bdi>{place}</bdi></span>}
    {url && image && <figcaption>{source
      ? <a href={source} target="_blank" rel="noopener noreferrer">{t('Photo:')} {image.artist && <bdi>{image.artist}</bdi>} · {image.license} · {t('Wikimedia')}</a>
      : <>{t('Photo:')} {image.license}</>}</figcaption>}
  </figure>
}
