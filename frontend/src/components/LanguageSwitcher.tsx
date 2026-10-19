import { useLanguage } from '../lib/language'

export function LanguageSwitcher() {
  const { language, setLanguage, t } = useLanguage()
  return <button className="rihla-language-switch" type="button" onClick={() => setLanguage(language === 'en' ? 'ar' : 'en')} aria-label={t(language === 'en' ? 'Switch to Arabic' : 'Switch to English')} lang="en">
    {language === 'en' ? 'AR' : 'EN'}
  </button>
}
