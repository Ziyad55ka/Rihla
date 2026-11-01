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
    id: UUID
    category: Literal["activity", "attraction", "restaurant"] = "activity"
    name: InfoField
    description: InfoField
    location: InfoField
    duration: InfoField
    scheduled_date: InfoField
    price_per_person: ActivityPrice  # SarPrice status rules; zero is allowed
    booking_url: BookingUrl
    image_url: BookingUrl

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


US-11/12 implementation and local mock demo: [activities.md](activities.md).
