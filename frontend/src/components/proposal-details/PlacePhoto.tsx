import { useEffect, useRef, useState } from 'react'
import { useLanguage } from '../../lib/language'
import { safeLink } from '../../lib/proposals'
import type { PlaceImage } from '../../types/proposal'
import { InfoIcon } from './icons'

/** A photo that opens nothing. Its credit, which its licence asks for, is on the icon. */
export function PlacePhoto({ image, place, variant = 'card' }: { image?: PlaceImage | null; place: string; variant?: 'card' | 'hero' }) {
  const { t } = useLanguage()
  const [failed, setFailed] = useState(false)
  const [loaded, setLoaded] = useState(false)
  const [open, setOpen] = useState(false)
  const photo = useRef<HTMLImageElement>(null)
  useEffect(() => { if (photo.current?.complete) setLoaded(true) }, [])
  const url = !failed && image ? safeLink(image.url) : null
  if (!url || !image) return variant === 'hero' ? null : <figure className="details-photo"><span className="details-photo-empty" aria-hidden="true"><bdi>{place}</bdi></span></figure>
  return <figure className={`details-photo details-photo--${variant}${loaded ? '' : ' is-loading'}`}>
    <img ref={photo} className={loaded ? 'is-loaded' : undefined} src={url} alt={variant === 'hero' ? '' : t('Photo of {place}', { place })} loading="lazy" decoding="async" referrerPolicy="no-referrer" onLoad={() => setLoaded(true)} onError={() => setFailed(true)} />
    <button type="button" className="details-photo-info" aria-expanded={open} aria-label={t('Photo source and licence')} onClick={() => setOpen((value) => !value)} onBlur={() => setOpen(false)}><InfoIcon /></button>
    <figcaption className={`details-photo-credit${open ? ' is-open' : ''}`} role="tooltip">{image.artist && <><bdi>{image.artist}</bdi> · </>}<bdi>{image.license}</bdi> · {t('Wikimedia')}</figcaption>
  </figure>
}
