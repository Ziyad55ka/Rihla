# تسليم Developer 3: US-13 وUS-14 وUS-15

بعض شغل صفحة العرض (US-10) يدخل في قصصك. هذا الملف يوضح وش موجود منه، ووين، وكيف تملكه وتطوره، بدون ما نكرر الشغل. الفرع: `sprint-2/ai-proposals`.

نص الـ Acceptance Criteria الكامل لـ US-13 وUS-14 وUS-15 مو في المستودع، فراجعه من وثيقة Sprint 0.

## شغلك في الفروع

فحصت `origin/Rawaf` و`origin/ibrahim` و`origin/Ziyad`، وما لقيت شغلًا لـ US-13 أو US-14 أو US-15. فالفرعان `Rawaf` و`ibrahim` ما فيهما أي commit فوق `main`، فما فيه تعارض مع كودك حاليًا. وإذا عندك شغل محلي غير مرفوع، ارفعه أو قل لنا حتى نطابق.

## وش موجود، ووين

| القصة | الموجود | وين بالكود |
| --- | --- | --- |
| US-13-AC01 إجمالي الإقامة | السعر × الليالي لكل مدينة | `Hotel` و`PersonShare` في `components/proposal-details/CityStaysSection.tsx` |
| US-13-AC02 سعر الفرد والمجموعة | `price_per_person` للشخص. و`group_total_sar` فقط إذا كل الأعضاء من مدينة وحدة | `_with_group_totals` في `backend/app/api/routes/proposals.py`، والعرض في `FlightsSection.tsx` |
| US-13-AC03 الغرف المشتركة والفردية | اختيار عرض لكل عضو، ما ينحفظ، ويغيّر سعر الشخص و`no_rooms` في رابط Booking | `lib/rooms.ts` و`RoomPicker` في `CityStaysSection.tsx` |
| US-14 المصادر وحالتها | `Proposal.sources`، و`ProposalSource.kind`، و`evidence`، والحالات الأربع. **قسم المصادر انحذف من الصفحة بطلب سابق، والبيانات باقية في الـ API** | `backend/app/services/source_policy.py`، و`StatusBadge` في `values.tsx`، و`staySource` في `lib/proposals.ts` |
| US-15-AC02 ملاحظة التنازل | `flexible_adjustments` في رأس الصفحة، بنص عام بدون أي تفصيل خاص | `ProposalHeader.tsx`، و`build_proposal` في `proposal_generation.py` |
| فحص الميزانية | `budget_status`، ويفترض غرفة لكل شخص حتى يخطئ للأعلى | `budget_status` في `backend/app/services/proposal_generation.py` |

## كيف تملكه وتطوره

- **مكانك في الصفحة:** `components/proposal-details/CostsAndCompatibility.tsx`، بعد الأنشطة، ويستقبل `proposal`. يرجع `null` اليوم، وما تحتاج تلمس `ProposalDetailPage.tsx`.
- **الملفات أعلاه صارت لك:** طوّرها مباشرة، وما تحتاج نسخة ثانية. وإذا نقلت الأرقام لقسم التكاليف، احذفها من `CityStaysSection.tsx` في نفس التغيير حتى ما تتكرر.
- **المصادر:** لو US-14 يطلب قائمة مصادر في الصفحة، ابنها داخل `CostsAndCompatibility.tsx` أو ملف جديد، من `proposal.sources`، مع إخفاء `kind === 'flight'`، لأنها ملاحظات داخلية.
- **الحالات:** استخدم `PriceValue` و`InfoValue` و`StatusBadge` من `values.tsx`، وكل النصوص في `lib/translations.ts` باللغتين.
- **الخصوصية:** ما يوصل المتصفح أي ميزانية أو عدد أعضاء أو مدينة عضو ثانٍ. و`rihla_flight_group` يوصل الباكند فقط، ويوصل الفرونت منه `all_same_city` و`group_total_sar`.
- **الاختبارات:** قلّد `pages/ProposalDetailPage.test.tsx` و`backend/tests/test_flight_group.py`.

## تداخل لازم ننتبه له

Developer 2 بنى `backend/app/services/activity_estimate.py` و`ActivityProposalEstimate` في `origin/Ziyad` لـ US-12-AC03. يجمع الطيران والإقامة والتنقل والأنشطة للشخص، ويفترض غرفة لكل شخص. وهذا يتقاطع مع US-13، فنسّق معه: هل يبقى عنده، أو يصير جزءًا من حساب التكاليف عندك؟

## نقاط للنقاش

1. من يملك حساب التكلفة الإجمالية: `budget_status`، أو `activity_estimate.py`، أو خدمة جديدة واحدة؟
2. اختيار الغرف اليوم ما ينحفظ، و`budget_status` يفترض غرفة لكل شخص. هل US-13-AC03 يحتاج حفظ الاختيار، وأن يؤثر على الميزانية؟
3. سعر الغرفة نفترضه كما هو في `hotel_price_per_night`. هل هو مقبول كتقدير؟
4. سعر المجموعة في رحلة المدينة الواحدة يكشف العدد بالقسمة. هل هذا مقبول في US-13-AC02؟
5. US-14: نرجّع قسم مصادر في الصفحة، أو نكتفي بذكر المصدر جنب كل قيمة كما هو الآن؟
