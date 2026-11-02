import type { Language } from '../../lib/language'

type Translate = (text: string, values?: Record<string, string | number>) => string

// Arabic counts differently: one, two, three to ten, then eleven and up.
export function nightsLabel(count: number, language: Language, t: Translate, locale: string): string {
  if (count === 1) return t('One night')
  if (count === 2) return t('Two nights')
  const value = { count: count.toLocaleString(locale) }
  return language === 'ar' && count > 10 ? t('{count} nights (eleven or more)', value) : t('{count} nights', value)
}
