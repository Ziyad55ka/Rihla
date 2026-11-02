import { useLanguage } from '../../lib/language'

export function useSar() {
  const { t, locale } = useLanguage()
  return (amount: string | number) => t('{amount} SAR', { amount: Number(amount).toLocaleString(locale) })
}
