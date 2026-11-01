# دليل Proposal Schema للفريق

هذا الدليل لـ Developer 2 (US-11/12: الأنشطة) و Developer 3 (US-13/14/15: التكاليف والمصادر والتوافق). يوضح شكل بيانات العرض، وكيف تقرؤونها، ووين تضيفون شغلكم.

> **الحالة الحالية:** الـ endpoints مختبرة محليًا، لكنها ما انختبرت على Supabase الحقيقي بعد. اشتغلوا الحين على ملف الـ Mock.

## وش هو العرض (Proposal)؟

العرض خيار رحلة كامل: وجهة، وتواريخ، ومدن، وطيران، وفندق، وتنقل. لكل رحلة حتى ٣ عروض.

يتولد العرض على مراحل: Gemini يخطط، والبحث يجيب المعلومات والأسعار (Ignav للطيران، و Tavily للباقي)، والباكند يفحص كل عرض قبل حفظه.

**كيف يوصلكم:** لأي عضو في الرحلة:

```
GET /api/trips/{trip_id}/proposals
Authorization: Bearer <توكن المستخدم>
```

الرد:

| الحقل | النوع | المعنى |
| --- | --- | --- |
| `version` | `int` أو `null` | رقم آخر توليد |
| `complete` | `bool` | `false` إذا نجح أقل من ٣ عروض |
| `generated_at` | تاريخ ووقت أو `null` | وقت آخر حفظ |
| `generating` | `bool` | فيه توليد شغال الحين |
| `needs_regeneration` | `bool` | العروض ما فيها طيران من مدينة هذا العضو |
| `proposals` | `Proposal[]` | حتى ٣ عروض، وممكن تكون فاضية |

## حقول Proposal

| الحقل | النوع | المعنى | مثال |
| --- | --- | --- | --- |
| `id` | UUID | معرّف العرض | `"00000000-…-0001"` |
| `trip_id` | UUID | الرحلة | `"00000000-…-00aa"` |
| `version` | `int` | رقم التوليد | `1` |
| `option_number` | `1` أو `2` أو `3` | رقم الخيار | `1` |
| `title` | `str` | عنوان عام | `"Nile Heritage Experience"` |
| `destination` | `str` | الوجهة المعروضة | `"Cairo"` |
| `start_date` | تاريخ `YYYY-MM-DD` | أول يوم | `"2026-12-13"` |
| `end_date` | تاريخ `YYYY-MM-DD` | آخر يوم | `"2026-12-17"` |
| `cities` | `CityStay[]` | المدن بالترتيب، واحدة على الأقل | انظر قسم الفنادق |
| `flights` | `Flights[]` | طيران مدينة العضو فقط، وممكن تكون فاضية | انظر قسم الطيران |
| `intercity_transport` | `IntercityTransfer[]` | التنقل بين المدن، وفاضية لمدينة واحدة | انظر تحت |
| `flexible_adjustments` | `FlexibleAdjustment[]` | شرح أي تفضيل Flexible ما تحقق | انظر تحت |
| `budget_status` | نص | حالة الميزانية | `"includes_unconfirmed"` |
| `sources` | `ProposalSource[]` | المصادر المستشهد بها | انظر تحت |

### الأنواع الصغيرة

| النوع | الحقول |
| --- | --- |
| `InfoField` | `value` (نص أو `null`)، `status`، `evidence` |
| `SarPrice` | `amount_sar` (**نص** مثل `"1200.00"` أو `null`)، `status`، `evidence` |
| `Evidence` | `source_id` (رقم من `sources`)، `quote` (اقتباس) |
| `ProposalSource` | `id`، `title`، `url` |
| `IntercityTransfer` | `from_city`، `to_city`، `mode`، `duration`، `price_per_person` |
| `FlexibleAdjustment` | `category` (`destinations` أو `interests` أو `flights` أو `accommodation`)، `explanation` |

**انتبهوا:** `amount_sar` يوصل كنص، فحوّلوه لرقم قبل أي جمع.

## الحالات

كل معلومة قابلة للنقص لها `status`:

| الحالة | متى تظهر | `value` / `amount_sar` | `evidence` | كيف تعرضها الواجهة |
| --- | --- | --- | --- | --- |
| `Sourced` | المصدر قالها صراحة. وللأسعار: سعر طيران `round_trip` متحقق منه بالريال فقط | موجودة | لازم | القيمة عادية، مع رابط المصدر |
| `Estimated` | تقدير من مصدر: سعر محوّل، أو نطاق (ناخذ الأعلى)، أو "starting from" | موجودة | لازم | القيمة مع شارة "Estimated"، ومع المصدر |
| `Unconfirmed` | غير واضحة، أو تقدير Gemini العام بدون مصدر | موجودة | **ممكن فاضية** | القيمة مع شارة "Unconfirmed" بشكل مختلف، وبدون رابط إذا ما فيه مصدر |
| `Not available` | ما عرفناها | `null` | فاضية | اكتبوا "Not available"، ولا تخفوا الحقل |

`Sourced` معناها "المصدر قال هذا الكلام"، مو "تأكدنا إنه صحيح". والفنادق والتنقل ما تقبل `Sourced` في السعر أبدًا.

## الطيران

كل عنصر في `flights` يخص مدينة انطلاق واحدة:

| الحقل | المعنى |
| --- | --- |
| `origin` | مدينة الانطلاق |
| `trip_type` | `round_trip` أو `split` أو `one_way` |
| `legs` | الرحلات: ذهاب ثم عودة، أو ذهاب فقط |
| `airline`, `duration` | ملخص رحلة الذهاب |
| `price_per_person` | تكلفة الرحلة كلها للفرد |

وكل عنصر في `legs` فيه: `direction` (`outbound` أو `return`)، و`date`، و`airline`، و`duration`، و`price`، و`booking_url`.

**مهم:** استخدموا `price_per_person` للتكلفة، ولا تجمعوا أسعار `legs` فوقه حتى ما يتكرر المبلغ.

في الأمثلة، `AIR` اختصار لـ `InfoField` فيه الشركة، و`NA` اختصار لحقل `Not available`.

### `round_trip`: حجز واحد

رابط واحد مشترك، وسعر كل رحلة `Not available` لأن السعر على الحجز كله.

```json
{
  "origin": "Riyadh",
  "trip_type": "round_trip",
  "legs": [
    { "direction": "outbound", "date": "2026-12-13", "airline": "AIR", "duration": "NA", "price": "NA", "booking_url": "https://air.example/book" },
    { "direction": "return", "date": "2026-12-17", "airline": "AIR", "duration": "NA", "price": "NA", "booking_url": "https://air.example/book" }
  ],
  "airline": "AIR",
  "duration": "NA",
  "price_per_person": { "amount_sar": "918.00", "status": "Sourced", "evidence": [{ "source_id": 1, "quote": "…" }] }
}
```

### `split`: حجزان منفصلان

لكل رحلة رابطها وسعرها، والمجموع `Estimated` دائمًا. وممكن يكون رابط إحدى الرحلتين `null`.

```json
{
  "origin": "Riyadh",
  "trip_type": "split",
  "legs": [
    { "direction": "outbound", "date": "2026-12-13", "airline": "AIR", "duration": "NA", "price": { "amount_sar": "400.00", "status": "Estimated", "evidence": [{ "source_id": 1, "quote": "…" }] }, "booking_url": "https://a.example/out" },
    { "direction": "return", "date": "2026-12-17", "airline": "AIR", "duration": "NA", "price": { "amount_sar": "329.00", "status": "Estimated", "evidence": [{ "source_id": 1, "quote": "…" }] }, "booking_url": "https://b.example/back" }
  ],
  "airline": "AIR",
  "duration": "NA",
  "price_per_person": { "amount_sar": "729.00", "status": "Estimated", "evidence": [{ "source_id": 1, "quote": "…" }] }
}
```

### `one_way`: ذهاب فقط

رحلة واحدة، وسعر العودة **غير محسوب**، فلازم توضحونه للمستخدم. و`budget_status` هنا ما يكون `within_group_budget`.

```json
{
  "origin": "Riyadh",
  "trip_type": "one_way",
  "legs": [
    { "direction": "outbound", "date": "2026-12-13", "airline": "AIR", "duration": "NA", "price": { "amount_sar": "500.00", "status": "Estimated", "evidence": [{ "source_id": 1, "quote": "…" }] }, "booking_url": "https://a.example/out" }
  ],
  "airline": "AIR",
  "duration": "NA",
  "price_per_person": { "amount_sar": "500.00", "status": "Estimated", "evidence": [{ "source_id": 1, "quote": "…" }] }
}
```

**مصدر الروابط:** روابط الطيران من Ignav، و`booking_url` يكون `https` أو `null`. لا تقرؤوا الروابط من `sources`، فهي حقول مستقلة.

**حالة ثانية:** إذا Ignav ما اشتغل، يرجع الطيران من بحث الويب. يظهر النوع `round_trip` مع روابط `null`، والسعر `Estimated` أو `Unconfirmed`. فاعتمدوا على حالة السعر، مو على النوع وحده.

## الفنادق

كل عنصر في `cities` (`CityStay`):

| الحقل | المعنى | مثال |
| --- | --- | --- |
| `order` | الترتيب من 1 | `1` |
| `city` | المدينة | `"Cairo"` |
| `nights` | عدد الليالي، ومجموعها يساوي أيام الرحلة ناقص واحد | `4` |
| `hotel_name` | `InfoField` | `"Mock Hotel"` |
| `hotel_price_per_night` | `SarPrice`، وما يكون `Sourced` | `"450.00"` |
| `booking_url` | رابط بحث Booking.com أو `null` | انظر تحت |

الرابط مبني من الكود، بدون API:

```
https://www.booking.com/searchresults.html?ss=Mock+Hotel%2C+Cairo%2C+Egypt&checkin=2026-12-13&checkout=2026-12-17&group_adults=2
```

فيه اسم الفندق والمدينة والدولة والتواريخ وعدد الأعضاء. وإذا الفندق غير معروف، يبحث بالمدينة فقط. **هذا رابط بحث،** ما يضمن توفر الفندق ولا السعر.

## `budget_status`

| القيمة | المعنى | في الواجهة |
| --- | --- | --- |
| `within_group_budget` | الإجمالي داخل أقل ميزانية، وكل الأسعار لها مصدر | "ضمن ميزانية المجموعة" |
| `includes_unconfirmed` | الإجمالي المعروف داخل الميزانية، لكن فيه سعر `Unconfirmed` أو ناقص | "ضمن الميزانية، مع أسعار غير مؤكدة" |
| `over_group_budget` | يتجاوز الميزانية. العرض يُرفض ويُعاد توليده، فما تشوفونه في الردود عادةً | تعاملوا معه احتياطًا |

الإجمالي يشمل أغلى طيران بين مدن الأعضاء، وكل ليالي الفنادق بدون مشاركة غرف، والتنقل. **ما يشمل الأكل والأنشطة.**

## وين تضيف شغلك

### Developer 2: الأنشطة

أضيفوا حقل `activities` داخل `CityStay`، لأن النشاط يخص مدينة:

```python
class Activity(StrictModel):
    name: InfoField
    price_per_person: SarPrice
    booking_url: BookingUrl

class CityStay(StrictModel):
    activities: list[Activity] = Field(default_factory=list)
```

### Developer 3: التكاليف والتوافق

- **التكاليف التفصيلية:** حقل `cost_breakdown` داخل كل عنصر في `flights`، لأن التكلفة تختلف حسب مدينة الانطلاق. لا تحطونه على مستوى `Proposal`، لأنه بيكشف تكلفة مدن الأعضاء الثانين، وفلتر الطيران ما يشيله.
- **المصادر:** استخدموا `sources` و`evidence` الموجودين.
- **التوافق مع Essential:** حقل `essential_checks` على مستوى `Proposal`، فيه `category` و`met` فقط، بدون نص المتطلب:

```python
class EssentialCheck(StrictModel):
    category: PreferenceCategory
    met: bool

class Proposal(StrictModel):
    essential_checks: list[EssentialCheck] = Field(default_factory=list)
```

### خطوات الإضافة بدون كسر الموجود

1. خلوا الحقل الجديد **اختياريًا بقيمة افتراضية**. النماذج ترفض أي حقل غير معروف، والعروض المحفوظة والـ Demo ما فيها حقولكم.
2. عدّلوا **الملفين معًا**: `proposals.py` و`proposal.ts`.
3. أي حقل جديد فيه `evidence` أضيفوه في دالة `evidence_fields()` داخل `Proposal`. وإلا مصادره تنحذف قبل الحفظ.
4. حدّثوا `proposals.mock.json`، واختبار الـ Schema يفحصه تلقائيًا.
5. شغّلوا الاختبارات قبل أي commit: `uv run pytest` في `backend`، و`npm run typecheck` في `frontend`.
6. أي تغيير لحقل موجود أو حذفه، نسقوه مع Eyad أول.

## صفحة التفاصيل

الرابط: `/trips/:tripId/proposals/:proposalId`. الصفحة [ProposalDetailPage.tsx](../frontend/src/pages/ProposalDetailPage.tsx) تركّب الأقسام فقط، وكل قسم له ملف داخل `frontend/src/components/proposal-details/`.

- **Developer 2 (الأنشطة):** عدّلوا `CityActivities.tsx` فقط. يظهر داخل بطاقة كل مدينة، ويستقبل `stay`، فاقرؤوا `stay.activities`.
- **Developer 3 (التكاليف والتوافق):** عدّلوا `CostsAndCompatibility.tsx` فقط. يظهر قبل المصادر، ويستقبل `proposal`.
- **المصادر:** في `SourcesSection.tsx`، مقسمة: مصادر الحجز ومصادر الأفكار. طوروها في نفس الملف بدل قسم ثانٍ.
- **القيم:** استخدموا `InfoValue` و`PriceValue` و`PriceAgeBadge` من `values.tsx`.
- **النصوص:** كل نص جديد في `frontend/src/lib/translations.ts`، والأنماط في `frontend/src/proposal-details.css`.

### حقول جديدة (كلها اختيارية، والعروض القديمة ما فيها)

| الحقل | وين | المعنى |
| --- | --- | --- |
| `title_ar`, `title_en`, `destination_ar` | `Proposal` | العنوان باللغتين والوجهة بالعربي. والبديل `title` و`destination` |
| `city_ar`, `area` | `CityStay` | اسم المدينة بالعربي، ومنطقة مقترحة |
| `priced_at` | `Flights` و`CityStay` | وقت فحص السعر |
| `flight_number`, `departure_time`, `arrival_time`, `stops`, `seller` | `FlightLeg` | تفاصيل الرحلة والبائع |
| `origin_airport`, `destination_airport` | `Flights` | رموز المطارات |
| `group_availability` | `Flights` | `available` أو `not_found` أو `unknown`. Ignav ما يعطي عدد مقاعد، فما فيه حقل عدد |
| `fare_basis`, `solo_saving_sar` | `Flights` | هل السعر لحجز جماعي أو منفرد، والفرق للشخص |
| `group_total_sar` | `Flights` | سعر المجموعة، ويوصل بس إذا كل الرحلة من مدينة وحدة |
| `provider`, `seller_type`, `price_source` | `Flights` | مصدر السعر، ونوع البائع، وهل السعر من البائع أو من البحث |
| `cabin_class`, `fare_name`, `checked_bags`, `carry_on_bags` | `Flights` | الفئة والشنط إذا المصدر رجعها |
| `hotel_url`, `hotel_source` | `CityStay` | صفحة الفندق نفسه واسم المصدر. يظهر زر "احجز هذا الفندق" إذا موجودة |
| `image` | `Proposal` و`CityStay` | صورة مع `url` و`source_url` و`artist` و`license`. تنضاف عند القراءة وما تنحفظ |
| `kind` | `ProposalSource` | `booking` أو `ideas` أو `flight` |

### تغييرات لازم تنتبهون لها

- **ما فيه "عرض الدليل":** `evidence` يبقى في البيانات للتحقق، بس لا تعرضون الاقتباسات ولا مصادر `flight` للمستخدم.
- **لا تستخدمون `booking_url` للطيران:** الرابط المحفوظ ممكن ينتهي. زر الحجز يطلب رابطًا جديدًا عبر `book-flight`.
- **الفنادق:** الاسم والسعر يجون من مصادر الحجز المعتمدة بس، وغيرها يظهر `Not available`.
- **`over_group_budget` ممكن يظهر الحين:** تحديث سعر الطيران ممكن يخلي عرضًا محفوظًا فوق الميزانية.

## قواعد لازم تلتزمون فيها

1. **الخصوصية:** ما يظهر في أي نص ميزانية عضو، ولا مدينته، ولا اسمه، ولا تفضيلاته. يعني العناوين والشروحات عامة، مثل "مناسب لميزانية المجموعة".
2. **كل معلومة لها حالة:** أي قيمة ممكن تنقص أو تتقدر تكون `InfoField` أو `SarPrice`، مو نص عادي.
3. **لا تخفوا الناقص:** اعرضوا "Not available" بدل ما يختفي الحقل.
4. **الأسعار بالريال:** عملات ثانية تتحول وتصير `Estimated`، والحقل دائمًا `amount_sar`.
5. **لا تخترعون مصادر:** `source_id` لازم يطابق عنصرًا في `sources`.
6. **لا تعتمدون على الطيران موجود:** `flights` ممكن تكون فاضية للعضو.

## روابط

- [backend/app/schemas/proposals.py](../backend/app/schemas/proposals.py): تعريف Python
- [frontend/src/types/proposal.ts](../frontend/src/types/proposal.ts): تعريف TypeScript
- [docs/examples/proposals.mock.json](examples/proposals.mock.json): ٣ عروض وهمية للتطوير
- [docs/ai-proposals.md](ai-proposals.md): كيف يشتغل التوليد، والخصوصية، وسياسة الأسعار

### الصور والأسعار (لـ Developer 2 و 3)

- **الصور:** استخدموا `PlacePhoto` من `components/proposal-details/PlacePhoto.tsx`. يعرض ذكر المصدر والرخصة، ولوحة بديلة إذا ما فيه صورة.
- **أسعار الطيران:** مرروا `startsFrom` إلى `PriceValue` حتى يظهر "يبدأ من". والملاحظة الثابتة هي `PriceNotice`.
- **التكاليف (Developer 3):** استخدموا `price_per_person`، فهو نفس الرقم اللي يدخل في `budget_status`.
- **الحجز:** `book-flight` صار `POST`، لأنه يحفظ السعر الجديد.

### الأنشطة وTrip.com (لـ Developer 2)

`searchAttractionAndActivity` موجود في ملف Trip.com المؤرشف بتاريخ 1 مايو 2026، **لكنه غير مجرب**، لأن مسارات Trip.com ترجع 404 منذ 1 نوفمبر 2026. فما عندنا مثال حقيقي من التجربة، وتأكدوا إنه يشتغل قبل الاعتماد عليه.

الطلب حسب الملف: `POST https://www.trip.com/ai-resource/searchAttractionAndActivity` بدون مفتاح.

```json
{
  "locale": "en-XX",
  "destination": "Manama",
  "beginDate": "2026-11-20",
  "endDate": "2026-11-30",
  "limit": 5,
  "originalInput": "Things to do in Manama",
  "originalInputInEnglish": "Things to do in Manama"
}
```

الرد حسب الملف: `results`، وكل عنصر فيه `title` و`summary` و`url` و`categories` و`attributes`. لا تولدوا الرابط بأنفسكم، واذكروا Trip.com جنب أي شيء يجي منه، وخلوه تحت `TRIPCOM_ENABLED`. والشروط في `docs/ai-proposals.md`.
