# تسليم Developer 2: US-11 وUS-12

هذا الدليل يربط شغلك في US-11 وUS-12 مع صفحة تفاصيل العرض (US-10)، بنفس التصميم والمنطق، وبأقل تعارض. الفرع: `sprint-2/ai-proposals`.

> لقينا شغلك في فرع `origin/Ziyad`، فهذا الدليل يطابق كودك وأسماءك، وما يفرض شكلًا ثانيًا. وما عدّلنا شي في فرعك.

## 1. المطلوب منك

**US-11 Explore activities and places (SF-08, Should)**

As a trip member, I want to explore suggested activities, attractions, and restaurants so that I can see what the group could do at each destination.

- US-11-AC01: Given a proposal includes a city, when I open its suggestions, then I can see relevant activities, attractions, and restaurants.
- US-11-AC02: Given details are available, when a suggestion is displayed, then it includes a description, location, approximate cost, duration, and image.
- US-11-AC03: Given an image or cost is unavailable, when the suggestion is displayed, then the system uses a placeholder or labels the cost as unknown.
- US-11-AC04: Given an event has fixed dates, when it is suggested, then those dates fall within the proposed travel period or the event is clearly marked as unsuitable.

**US-12 Choose preferred activities (SF-08, Should)**

As a trip member, I want to select or remove suggested activities so that the plan stays flexible.

- US-12-AC01: Given activities are available, when I select or remove one, then my latest choices are saved for the trip.
- US-12-AC02: Given I choose an activity, when it is saved, then I am not required to assign it to a specific day or time.
- US-12-AC03: Given selected activities have known costs, when proposal costs are updated, then those costs are included in the relevant estimate.

**قرارات من هذا النص:**

- **الفعاليات من Sprint 2:** US-11-AC04 يطلبها، فهي مو لاحقًا. وكودك يتحقق من `scheduled_date` داخل إقامة المدينة، ويتوافق مع هذا.
- **الاختيار لكل عضو:** النص يقول "my choices"، وجدولك `activity_selections` لكل عضو، فهو مطابق.
- **US-12-AC03:** يرتبط بـ Developer 3 (US-13). نسّق معه على `activity_estimate.py`. انظر [developer-3-handoff.md](developer-3-handoff.md).
- **صورة بديلة (US-11-AC03):** استخدم التصميم البديل في `PlacePhoto` بدل `activity-image-unavailable`، حتى تتوحد الصفحة.

## التعارضات مع `sprint-2/ai-proposals`

`git merge-tree` يبيّن 3 ملفات فقط. والحلول مقترحة، وما طبقنا شي:

| الملف | السبب | الحل المقترح |
| --- | --- | --- |
| `backend/app/schemas/proposals.py` | كلانا أضاف حقولًا في `CityStay` وفي الملف | احتفظ بالجهتين: `activities` مع `image` و`labels_en` وغيرها |
| `frontend/src/components/ProposalsPanel.tsx` | أضفت `ActivitiesPanel` تحت القائمة، وأنا أضفت الصور وحالة التوليد | احتفظ بالجهتين، أو الأفضل انقل `ActivitiesPanel` لصفحة التفاصيل (تحت) |
| `docs/proposal-schema-handoff.md` | تعديلان على نفس الفقرات | احتفظ بالجهتين |

- **migration:** ملفك `20261103000100_activity_selections.sql` يتطبق بعد `20261102000100_ai_proposals.sql`، وما فيه تعارض. والخمسة القديمة اندمجت في ملف واحد.
- **حساب التكلفة:** `activity_estimate.py` يفترض غرفة لكل شخص، وصفحتي تعرض افتراضيًا غرفًا مشتركة، فالرقمان ممكن يختلفان. هذي نقطة نقاش مع Developer 3.
- **صفحة `/demo/activities`:** في `App.tsx`، وخلّها للتطوير فقط كما هي، أو احذفها قبل الدمج مع `main`.

## 2. وش جاهز لك

| الشيء | وين |
| --- | --- |
| شكل العرض في الباكند | `backend/app/schemas/proposals.py`: الصنفان `Proposal` و`CityStay` |
| نفس الشكل في الفرونت | `frontend/src/types/proposal.ts`. أي تغيير لازم في الملفين |
| `activities` | في `CityStay` في فرعك: `activities: list[Activity]`، ويحتاج ينضاف عند الدمج |
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

`StrictModel` يرفض أي حقل غير معرّف، وحقلك `activities` قيمته الافتراضية قائمة فاضية، فالعروض القديمة تشتغل.

## 3. مكانك في الصفحة

ترتيب الصفحة: الرأس، ثم الطيران، ثم الفنادق، ثم التنقل بين المدن، ثم **أنت**، ثم التكاليف (Developer 3).

| الملف في `components/proposal-details/` | يظهر وين | يستقبل |
| --- | --- | --- |
| `ActivitiesSection.tsx` | قسم كامل بعد التنقل بين المدن | `proposal` |
| `CityActivities.tsx` | داخل بطاقة كل مدينة، تحت الفندق | `stay` |

اليوم `ActivitiesPanel` عندك تحت قائمة العروض. **الاقتراح:** انقله لصفحة التفاصيل، باستدعائه من `ActivitiesSection.tsx`، لأن العرض يتشاف كاملًا هناك، وتشيل التعديل من `ProposalsPanel.tsx`، فيختفي التعارض. عدّل هذين الملفين فقط، وما تحتاج تلمس `pages/ProposalDetailPage.tsx`. وكلاهما يرجع `null` اليوم، وخلّه كذا لما ما فيه بيانات، حتى ما يشوف المستخدم قسمًا فاضيًا. وتصميم الصفحة مرسوم في `docs/design/us10-proposal-details-mock.html`، لكن الترتيب تغيّر عنه.

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
| الأيقونات | `icons.tsx`: كلها من Lucide بوزن واحد. لا إيموجي ولا رموز نصية، لأنها تطلع مربعات |
| شرح قصير عند الطلب | `Hint.tsx` |
| عنوان القسم بأيقونة | `SectionTitle.tsx` |
| ظهور عند التمرير | تلقائي لأي `section` مباشر داخل الصفحة |
| ظهور عنصر | كلاس `details-reveal` |
| رقم يعد لقيمته | `useCountUp` في `lib/motion.ts` |
| حالة شغل بإحساس AI | `AiStatus` في `components/AiStatus.tsx` |

**الحركة:** نفس إحساس الصفحة الرئيسية: دخول 600 إلى 700ms، وتفاعل 150 إلى 350ms. و`prefers-reduced-motion` في CSS فقط.

**الخط:** IBM Plex Sans Arabic على `.proposal-details` و`.proposals-panel` فقط. فلو نقلت الأنشطة تحت `.proposal-details`، تاخذه تلقائيًا.

**البطاقات:** أضف كلاس `details-city` لبطاقتك إذا تبي نفس تأثير المرور.

**RTL والجوال:** استخدم `margin-inline` و`inset-inline`، ولا تستخدم `left` و`right`. وأي اسم من مصدر خارجي داخل `<bdi>`. وأقل حجم للضغط 44px، وما فيه تمرير أفقي عند 390px.

**الوصول:** كل زر له اسم واضح، وكل صورة لها `alt`، ولا تعتمد على اللون وحده.

**اللغة:** كل نص في `lib/translations.ts` بالعربي والإنجليزي، بدون خلط. وأسماء الأماكن من `placeName` في `lib/places.ts`، والشركات من `airlineName`. و`npm run lint` يفشل إذا ناقص نص.

## 5. قواعد لازم تلتزم فيها

- **الخصوصية:** لا تذكر ميزانية أو مدينة انطلاق أو تفضيل أي عضو في أي نص. والاقتراحات تكون عامة، مثل "قريب من المتاحف". وعندك `PRIVATE_DETAIL` في `schemas/proposals.py`.
- **الحالات:** كل سعر أو معلومة لها حالة: `Sourced` أو `Estimated` أو `Unconfirmed` أو `Not available`. و`Sourced` و`Estimated` يحتاجان `evidence`.
- **المصادر:** الأسعار من مصادر معتمدة بس، والمقالات والمدونات للأفكار بس. وتقدر تستخدم `classify_source` و`on_domain` من `source_policy.py`.
- **الصور:** Wikimedia عبر `place_images.py`، أو مصدر تسمح شروطه. ولا صور من مواقع بدون إذن.
- **الحصص:** Gemini حده 20 طلبًا في اليوم، ومشترك بيننا. فالأنشطة تتولد مع العرض أو بطلب واحد لكل عرض، ومع كاش. وTavily له حد مجاني أيضًا، و`SearchCache` جاهز في `trip_research.py`.
- **Migrations:** فقط إذا ضرورية، واسأل قبل التطبيق على Supabase. وملف Sprint 2 هو `20261102000100_ai_proposals.sql`، فلا تعدّله، وضف ملفًا جديدًا.
- **Trip.com:** تم تقييمه واستبعاده، فلا تعتمد عليه.

## 6. "وش يصير في [المدينة] خلال أيام رحلتكم"

مطلوب في US-11-AC04، وكودك يغطي أغلبه. فالفعالية هي `Activity` نفسها، بدون حقول ثانية، و`scheduled_date` يعطيها التاريخ.

- **ناقص:** `category` فيه `activity` و`attraction` و`restaurant`. فلو تبي فرزًا للفعاليات، أضف `event`.
- **وين تنعرض:** ملخص في `CityActivities` داخل كل مدينة، والتفاصيل في `ActivitiesSection`.
- **مصدر البيانات:** بحث Tavily واستخراج Gemini، بنفس منطق `trip_research.py`. وتوليد الأنشطة الحقيقي لسه غير موجود، وهو دور مشترك، لأن كودك يعتمد على ملف mock.
- **الحدود:** مواعيد الفعاليات تتغير، والأسعار غالبًا غير مؤكدة، وكل بحث يستهلك من الحصة.

## 7. نقاط للنقاش (قرارات مشتركة)

1. الأنشطة تتولد مع العرض بطلب Gemini واحد، أو بطلب منفصل لما يفتح المدينة؟ وأثر هذا على الحصة.
2. من يملك حساب التكلفة: `activity_estimate.py`، أو حساب Developer 3؟
3. هل الأنشطة تدخل في `budget_status`؟ كودك يكتب "Before selected activities" جنبه.
4. نقل `ActivitiesPanel` لصفحة التفاصيل: موافق؟
5. من يدمج أول؟ واللي بعده يحل التعارضات الثلاثة.

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
