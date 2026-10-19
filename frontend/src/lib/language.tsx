/* eslint-disable react-refresh/only-export-components */
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { arabic } from './translations'

export type Language = 'en' | 'ar'
type Values = Record<string, string | number>

export function translate(language: Language, text: string, values: Values = {}): string {
  const known = Object.hasOwn(arabic, text)
  let result = language === 'ar' && known ? arabic[text] : text
  if (language === 'ar' && !known) {
    const failedRequest = text.match(/^The request failed \(HTTP (\d+)\)\. Check your input and try again\.$/)
    const failedHealth = text.match(/^The backend returned HTTP (\d+)\.$/)
    const timeout = text.match(/^The backend did not respond within ([\d.]+) seconds\.$/)
    if (failedRequest) result = `تعذّر تنفيذ الطلب (HTTP ${failedRequest[1]}). تحقق من مدخلاتك وحاول مجددًا.`
    if (failedHealth) result = `أعاد الخادم حالة HTTP ${failedHealth[1]}.`
    if (timeout) result = `لم يستجب الخادم خلال ${timeout[1]} ثانية.`
  }
  return result.replace(/\{(\w+)\}/g, (placeholder, name: string) => String(values[name] ?? placeholder))
}

interface LanguageContextValue {
  language: Language
  locale: string
  setLanguage: (language: Language) => void
  t: (text: string, values?: Values) => string
}
const LanguageContext = createContext<LanguageContextValue | null>(null)

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [language, setLanguageState] = useState<Language>(() => {
    try { return localStorage.getItem('rihla-language') === 'ar' ? 'ar' : 'en' } catch { return 'en' }
  })
  const setLanguage = useCallback((next: Language) => {
    setLanguageState(next)
    try { localStorage.setItem('rihla-language', next) } catch { /* Available for this session when storage is blocked. */ }
  }, [])
  useEffect(() => {
    document.documentElement.lang = language
    document.documentElement.dir = language === 'ar' ? 'rtl' : 'ltr'
    document.title = language === 'ar' ? 'رحلة | خططوا معًا' : 'Rihla | Plan together'
  }, [language])
  const value = useMemo(() => ({
    language, locale: language === 'ar' ? 'ar-SA-u-ca-gregory' : 'en-US', setLanguage,
    t: (text: string, values?: Values) => translate(language, text, values),
  }), [language, setLanguage])
  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>
}

export function useLanguage() {
  const context = useContext(LanguageContext)
  if (!context) throw new Error('useLanguage must be used inside LanguageProvider')
  return context
}
