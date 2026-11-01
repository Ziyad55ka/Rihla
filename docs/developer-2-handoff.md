# تسليم Developer 2: US-11 وUS-12

هذا الدليل يكفيك تبني الأنشطة والمطاعم والمعالم واختيارها فوق صفحة تفاصيل العرض (US-10)، بنفس التصميم والمنطق، بدون ما تتعارض مع شغل US-09 وUS-10. الفرع: `sprint-2/ai-proposals`.

> ما أضفنا `activities` للكود. الشكل في القسم 6 اقتراح، ونقرره سوا في النقاش.

## 1. المطلوب منك

- **US-11:** عرض الأنشطة والمطاعم والمعالم لكل مدينة، مع الوصف والصورة والتكلفة والمدة.
- **US-12:** اختيار النشاط أو إزالته، وحفظ الاختيارات.

**Acceptance Criteria:** نص Sprint 0 الأصلي لـ US-11 وUS-12 **غير موجود في المستودع**، ولا نخترعه هنا. Eyad يرسله لك، والصقه في هذا القسم:

- US-11-AC01: `[من وثيقة Sprint 0]`
- US-12-AC01: `[من وثيقة Sprint 0]`

## 2. وش جاهز لك

| الشيء | وين |
| --- | --- |
| شكل العرض في الباكند | `backend/app/schemas/proposals.py`: الصنفان `Proposal` و`CityStay` |
| نفس الشكل في الفرونت | `frontend/src/types/proposal.ts`. أي تغيير لازم في الملفين |
| وين تضيف `activities` | داخل `CityStay` في الملفين، بعد الاتفاق |
| جلب العروض | `GET /api/trips/{trip_id}/proposals`، وفي الفرونت `getProposals` من `lib/proposals.ts` |
| بيانات بدون AI | `docs/examples/proposals.mock.json` و`backend/app/data/demo_proposals.json` |
| وضع Demo | `PROPOSALS_DEMO_MODE=true` في `backend/.env`: يخدم عروضًا محفوظة بدون Gemini ولا Tavily ولا Ignav |

مثال لمدينة من ملف الـ Demo:

```json
{
  "order": 1,
  "city": "Cairo",
  "nights": 4,
  "hotel_name": { "value": null, "status": "Not available", "evidence": [] },
  "hotel_price_per_night": { "amount_sar": "375.00", "status": "Unconfirmed", "evidence": [] },
  "booking_url": "https://www.booking.com/searchresults.html?ss=Cairo%2C+Egypt&checkin=2026-12-13&checkout=2026-12-17&group_adults=2"
}
```

`StrictModel` يرفض أي حقل غير معرّف، فأضف الحقل في الـ Schema أول. وخلّه اختياريًا، لأن العروض القديمة ما فيها.

## 3. مكانك في الصفحة

ترتيب الصفحة: الرأس، ثم الطيران، ثم الفنادق، ثم التنقل بين المدن، ثم **أنت**، ثم التكاليف (Developer 3).

| الملف في `components/proposal-details/` | يظهر وين | يستقبل |
| --- | --- | --- |
| `ActivitiesSection.tsx` | قسم كامل بعد التنقل بين المدن | `proposal` |
| `CityActivities.tsx` | داخل بطاقة كل مدينة، تحت الفندق | `stay` |

عدّل هذين الملفين فقط، وما تحتاج تلمس `pages/ProposalDetailPage.tsx`. وكلاهما يرجع `null` اليوم، وخلّه كذا لما ما فيه بيانات، حتى ما يشوف المستخدم قسمًا فاضيًا. وتصميم الصفحة مرسوم في `docs/design/us10-proposal-details-mock.html`، لكن الترتيب تغيّر عنه.

## 4. نظام التصميم

| Token | القيمة | الاستخدام |
| --- | --- | --- |
| `--rihla-ink` | `#172b22` | النص |
| `--rihla-muted` | `#687267` | النص الثانوي |
| `--rihla-green` | `#345441` | الأزرار والرأس والخطوط |
| `--rihla-bg` | `#e9e9df` | خلفية الصفحة والصناديق الداخلية |
| `--rihla-paper` | `#f8f8f2` | البطاقات |
| `--rihla-line` | `#d4d9cd` | الحدود |
| الخط | Arial, system-ui | موجود، وما تضيف خطًا |
| زوايا البطاقة | `14px`، والصناديق الداخلية `10px` | |
| البطاقة | `padding: 22px 24px` | |

**المكونات الجاهزة:**

| المكون | وين |
| --- | --- |
| البطاقة | كلاس `details-card` |
| الشارات والحالات الأربع | `StatusBadge`، و`InfoValue`، و`PriceValue` في `values.tsx` |
| "يبدأ من" | `<PriceValue price={...} startsFrom />` |
| عمر السعر | `PriceAgeBadge` في `values.tsx` |
| ملاحظة الأسعار | `PriceNotice` في `values.tsx` |
| الأزرار | كلاسا `trip-primary` و`trip-secondary` |
| الصور | `PlacePhoto.tsx`: تحميل ناعم، وتصميم بديل، والصورة تفتح مصدرها |
| الملصقات | كلاس `details-labels` |
| الأيقونات | `icons.tsx`: SVG بدون إيموجي |
| ظهور عند التمرير | تلقائي لأي `section` مباشر داخل الصفحة |
| ظهور عنصر | كلاس `details-reveal` |
| رقم يتغيّر بنعومة | `useCountUp` في `lib/motion.ts` |

**الحركة:** بين 150 و400ms، وتحترم `prefers-reduced-motion`. وفيه اختبار يفحص ملف `proposal-details.css`.

**RTL والجوال:** استخدم `margin-inline` و`inset-inline`، ولا تستخدم `left` و`right`. وأي اسم من مصدر خارجي داخل `<bdi>`. وأقل حجم للضغط 44px، وما فيه تمرير أفقي عند 390px.

**الوصول:** كل زر له اسم واضح، وكل صورة لها `alt`، ولا تعتمد على اللون وحده.

**اللغة:** كل نص في `lib/translations.ts` بالعربي والإنجليزي، بدون خلط. وأسماء الأماكن من `placeName` في `lib/places.ts`، والشركات من `airlineName`. و`npm run lint` يفشل إذا ناقص نص.

**بطاقة نشاط كبداية:**

```tsx
import { useLanguage } from '../../lib/language'
import { PlacePhoto } from './PlacePhoto'
import { PriceValue } from './values'

// اسم الصنف Activity مؤقت حتى نتفق على الشكل.
export function ActivityCard({ activity, place }: { activity: Activity; place: string }) {
  const { t } = useLanguage()
  return <article className="details-card">
    <PlacePhoto image={activity.image} place={place} />
    <h3><bdi>{activity.name}</bdi></h3>
    <p className="details-hint"><bdi>{activity.description}</bdi></p>
    <PriceValue price={activity.price_per_person} unit="per person" startsFrom />
    <button type="button" className="trip-secondary">{t('Add to the trip')}</button>
  </article>
}
```

## 5. قواعد لازم تلتزم فيها

- **الخصوصية:** لا تذكر ميزانية أو مدينة انطلاق أو تفضيل أي عضو في أي نص. والاقتراحات تكون عامة، مثل "قريب من المتاحف". وعندك `PRIVATE_DETAIL` في `schemas/proposals.py`.
- **الحالات:** كل سعر أو معلومة لها حالة: `Sourced` أو `Estimated` أو `Unconfirmed` أو `Not available`. و`Sourced` و`Estimated` يحتاجان `evidence`.
- **المصادر:** الأسعار من مصادر معتمدة بس، والمقالات والمدونات للأفكار بس. وتقدر تستخدم `classify_source` و`on_domain` من `source_policy.py`.
- **الصور:** Wikimedia عبر `place_images.py`، أو مصدر تسمح شروطه. ولا صور من مواقع بدون إذن.
- **الحصص:** Gemini حده 20 طلبًا في اليوم، ومشترك بيننا. فالأنشطة تتولد مع العرض أو بطلب واحد لكل عرض، ومع كاش. وTavily له حد مجاني أيضًا، و`SearchCache` جاهز في `trip_research.py`.
- **Migrations:** فقط إذا ضرورية، واسأل قبل التطبيق على Supabase. وملف Sprint 2 هو `20261102000100_ai_proposals.sql`، فلا تعدّله، وضف ملفًا جديدًا.
- **Trip.com:** تم تقييمه واستبعاده، فلا تعتمد عليه.

## 6. اقتراح: "وش يصير في [المدينة] خلال أيام رحلتكم"

فعاليات ومهرجانات وأماكن مشهورة في تواريخ الرحلة بالضبط.

| الحقل المقترح | المعنى |
| --- | --- |
| `name` | `InfoField`: الاسم |
| `kind` | `event` أو `festival` أو `attraction` أو `restaurant` |
| `starts_at`, `ends_at` | التاريخ والوقت، إذا معروفين |
| `place` | المكان داخل المدينة |
| `description` | وصف عام قصير |
| `duration` | المدة |
| `price_per_person` | `SarPrice`: السعر التقديري والحالة |
| `image` | `PlaceImage` أو `null` |
| `url` | رابط المصدر |

- **وين تنعرض:** ملخص في `CityActivities` داخل كل مدينة، والتفاصيل في `ActivitiesSection`.
- **مصدر البيانات:** بحث Tavily واستخراج Gemini، بنفس منطق `trip_research.py`.
- **الحدود:** مواعيد الفعاليات تتغير، والأسعار غالبًا غير مؤكدة، فأغلبها `Unconfirmed`، وكل بحث يستهلك من الحصة.

## 7. نقاط للنقاش (قرارات مشتركة)

1. الأنشطة تتولد مع العرض بطلب Gemini واحد، أو بطلب منفصل لما يفتح المدينة؟ وأثر هذا على الحصة.
2. الاختيارات في US-12 لكل عضو أو للمجموعة؟ ومن يقدر يغيّرها؟ وتأثيرها على الميزانية، بالتنسيق مع Developer 3.
3. هل الأنشطة تدخل في فحص الميزانية؟
4. تخزين الاختيارات: جدول جديد يعني migration؟
5. الترتيب داخل الأيام: جدول يومي أو قائمة بس؟
6. الفعاليات: تدخل في Sprint 2 أو لاحقًا؟

## 8. التجربة

```powershell
# الباكند، داخل backend
uv sync
uv run uvicorn app.main:app --port 8001

# الفرونت، داخل frontend
npm install
npm run dev -- --port 5173
```

- **المفاتيح في `backend/.env` فقط**، وأسماؤها في `.env.example`. ومع `PROPOSALS_DEMO_MODE=true` ما تحتاج Gemini ولا Tavily ولا Ignav.
- **الاختبارات:** `uv run pytest` و`uv run ruff check .` في `backend`، و`npm test` و`npm run lint` في `frontend`، و`npm test` في `supabase`.
- **أمثلة تقلدها:** `backend/tests/test_flight_routes.py` للـ API بدون خدمات خارجية، و`frontend/src/pages/ProposalDetailPage.test.tsx` للواجهة باللغتين، و`supabase/tests/database.test.mjs` لقاعدة البيانات.

## 9. روابط

- [شكل العرض](proposal-schema-handoff.md)
- [منطق التوليد والمصادر](ai-proposals.md)
- [التصميم](design/us10-proposal-details-mock.html)
- `backend/app/services/source_policy.py` و`place_images.py` و`trip_research.py`
- `frontend/src/components/proposal-details/`
