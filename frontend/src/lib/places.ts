import type { Language } from './language'

// For proposals saved before Arabic names were stored, and for typed departure cities.
const ARABIC_PLACES: Record<string, string> = {
  riyadh: 'الرياض', jeddah: 'جدة', dammam: 'الدمام', medina: 'المدينة المنورة', abha: 'أبها', tabuk: 'تبوك', taif: 'الطائف', jazan: 'جازان', hail: 'حائل',
  paris: 'باريس', strasbourg: 'ستراسبورغ', nice: 'نيس', lyon: 'ليون', marseille: 'مرسيليا', france: 'فرنسا',
  manama: 'المنامة', bahrain: 'البحرين', dubai: 'دبي', 'abu dhabi': 'أبوظبي', 'united arab emirates': 'الإمارات', doha: 'الدوحة', qatar: 'قطر', muscat: 'مسقط', oman: 'عمان', kuwait: 'الكويت',
  cairo: 'القاهرة', alexandria: 'الإسكندرية', luxor: 'الأقصر', aswan: 'أسوان', egypt: 'مصر',
  amman: 'عمّان', aqaba: 'العقبة', 'dead sea': 'البحر الميت', jordan: 'الأردن', beirut: 'بيروت', lebanon: 'لبنان',
  istanbul: 'إسطنبول', ankara: 'أنقرة', antalya: 'أنطاليا', trabzon: 'طرابزون', turkey: 'تركيا',
  london: 'لندن', 'united kingdom': 'المملكة المتحدة', rome: 'روما', milan: 'ميلانو', venice: 'البندقية', florence: 'فلورنسا', italy: 'إيطاليا',
  madrid: 'مدريد', barcelona: 'برشلونة', spain: 'إسبانيا', vienna: 'فيينا', austria: 'النمسا', berlin: 'برلين', munich: 'ميونخ', germany: 'ألمانيا',
  athens: 'أثينا', greece: 'اليونان', geneva: 'جنيف', zurich: 'زيورخ', switzerland: 'سويسرا', amsterdam: 'أمستردام', netherlands: 'هولندا',
  tbilisi: 'تبليسي', batumi: 'باتومي', georgia: 'جورجيا', baku: 'باكو', azerbaijan: 'أذربيجان',
  'kuala lumpur': 'كوالالمبور', malaysia: 'ماليزيا', bangkok: 'بانكوك', phuket: 'بوكيت', thailand: 'تايلاند', bali: 'بالي', indonesia: 'إندونيسيا',
  tokyo: 'طوكيو', japan: 'اليابان', casablanca: 'الدار البيضاء', marrakech: 'مراكش', morocco: 'المغرب', tunis: 'تونس',
}
const ENGLISH_PLACES = Object.fromEntries(Object.entries(ARABIC_PLACES).map(([english, arabic]) => [arabic, english.replace(/\b\w/g, (letter) => letter.toUpperCase())]))

/** A place in the page's language. Unknown names stay as they were written. */
export function placeName(name: string, language: Language, stored?: string | null): string {
  const key = name.trim()
  if (language === 'ar') return stored || ARABIC_PLACES[key.toLowerCase()] || name
  return ENGLISH_PLACES[key] ?? name
}
