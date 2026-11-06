import { useEffect, useRef, useState } from 'react'
import { useLanguage } from '../../lib/language'
import { safeLink } from '../../lib/proposals'
import type { PlaceImage } from '../../types/proposal'
import { InfoIcon } from './icons'

/** A photo that opens nothing. Its credit, which its licence asks for, is on the icon. */
export function PlacePhoto({ image, place, variant = 'card', onUnavailable }: { image?: PlaceImage | null; place: string; variant?: 'card' | 'hero'; onUnavailable?: () => void }) {
  const { t } = useLanguage()
  const [failures, setFailures] = useState(0)
  const [loaded, setLoaded] = useState(false)
  const [open, setOpen] = useState(false)
  const photo = useRef<HTMLImageElement>(null)
  useEffect(() => { if (photo.current?.complete) setLoaded(true) }, [])
  const url = image && failures < 2 ? safeLink(failures ? image.fallback_url ?? null : image.url) : null
  if (!url || !image) return variant === 'hero' ? null : <figure className="details-photo"><span className="details-photo-empty" aria-hidden="true"><bdi>{place}</bdi></span></figure>
  const credit = safeLink(image.source_url)
  const sourceName = credit && new URL(credit).hostname.endsWith('wikimedia.org') ? t('Wikimedia') : t('Image credits')
  return <figure className={`details-photo details-photo--${variant}${loaded ? '' : ' is-loading'}`} onBlur={event => { if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false) }}>
    <img ref={photo} className={loaded ? 'is-loaded' : undefined} src={url} alt={variant === 'hero' ? '' : t('Photo of {place}', { place })} loading="lazy" decoding="async" referrerPolicy="no-referrer" onLoad={() => setLoaded(true)} onError={() => { setLoaded(false); setFailures(value => { if (value + 1 >= 2) onUnavailable?.(); return value + 1 }) }} />
    <button type="button" className="details-photo-info" aria-expanded={open} aria-label={t('Photo source and licence')} onClick={() => setOpen((value) => !value)}><InfoIcon /></button>
    <figcaption className={`details-photo-credit${open ? ' is-open' : ''}`}>{image.artist && <><bdi>{image.artist}</bdi> · </>}<bdi>{image.license}</bdi> · {credit ? <a href={credit} target="_blank" rel="noreferrer" tabIndex={open ? 0 : -1}>{sourceName}</a> : sourceName}</figcaption>
  </figure>
}
