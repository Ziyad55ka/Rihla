import type { Language } from './language'

// Sources answer in the language of their market, so Saudi fares come back in Arabic.
const AIRLINES: [english: string, arabic: string][] = [
  ['Gulf Air', 'طيران الخليج'], ['flynas', 'طيران ناس'], ['Saudia', 'الخطوط السعودية'], ['Saudi Arabian Airlines', 'الخطوط الجوية العربية السعودية'], ['flyadeal', 'طيران أديل'],
  ['Emirates', 'طيران الإمارات'], ['Etihad', 'الاتحاد للطيران'], ['Qatar Airways', 'الخطوط الجوية القطرية'], ['Oman Air', 'الطيران العماني'],
  ['Kuwait Airways', 'الخطوط الجوية الكويتية'], ['flydubai', 'فلاي دبي'], ['Air Arabia', 'العربية للطيران'], ['EgyptAir', 'مصر للطيران'],
  ['Royal Jordanian', 'الملكية الأردنية'], ['Turkish Airlines', 'الخطوط الجوية التركية'], ['Pegasus', 'طيران بيغاسوس'], ['AJet', 'إيه جيت'],
  ['Aegean Airlines', 'طيران ايجين'], ['Lufthansa', 'لوفتهانزا'], ['Air France', 'الخطوط الجوية الفرنسية'], ['KLM', 'كيه إل إم'],
  ['British Airways', 'الخطوط الجوية البريطانية'], ['ITA Airways', 'إيتا'],
  ['SunExpress', 'صن إكسبرس'], ['Jazeera Airways', 'طيران الجزيرة'], ['Middle East Airlines', 'طيران الشرق الأوسط'], ['Air Algérie', 'الخطوط الجوية الجزائرية'], ['Royal Air Maroc', 'الخطوط الملكية المغربية'], ['Air Cairo', 'إير القاهرة'], ['Nile Air', 'نايل إير'], ['Riyadh Air', 'طيران الرياض'],
]
const toArabic = new Map(AIRLINES.map(([english, arabic]) => [english.toLowerCase(), arabic]))
const toEnglish = new Map(AIRLINES.map(([english, arabic]) => [arabic, english]))

/** An airline in the page's language. Unknown names stay as the source wrote them. */
export function airlineName(name: string, language: Language): string {
  const key = name.trim()
  return (language === 'ar' ? toArabic.get(key.toLowerCase()) : toEnglish.get(key)) ?? name
}
