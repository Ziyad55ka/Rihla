# US-09 and US-10: AI proposals and the proposal details page

> [العربية](#العربية) · [English](#english)

## العربية

### الملخص

Developer 1. المدير يولّد عروض رحلات بالذكاء الاصطناعي (US-09)، وكل عضو يشوف تفاصيل العرض (US-10): الطيران والفنادق والتنقل بين المدن، مع رابط حجز وعمر السعر. Rihla ما يحجز ولا يقبض.

| المعيار | الحالة | الملاحظة |
| --- | --- | --- |
| US-09-AC01 | متحقق | التوليد يبدأ بعد جاهزية الكل ووجود تواريخ مشتركة، والزر والـ API وقاعدة البيانات يرفضون غير ذلك |
| US-09-AC02 | متحقق جزئيًا | المسارات مختلفة، لكن Essential يعتمد على تقرير Gemini، والتجربة الحقيقية الوحيدة أعطت عرضين من 3 |
| US-10-AC01 | متحقق | الوجهة والتواريخ والمدن وترتيبها ومدتها والفندق والتنقل والطيران |
| US-10-AC02 | متحقق | Not available وEstimated وUnconfirmed كلها بشارة واضحة |

### التقنيات والتكلفة

كلها بدون تكلفة بحدود هذا المشروع:

| الخدمة | الاستخدام | الحد |
| --- | --- | --- |
| Gemini | التخطيط واستخراج المعلومات | 20 طلبًا في اليوم |
| Tavily | البحث | الخطة المجانية، مع كاش |
| Ignav | أسعار الطيران وروابطه | أول 1000 طلب مجانية مرة واحدة، **وبعدها مدفوع**. وعندنا حدود استهلاك |
| Supabase | قاعدة البيانات | الخطة الحالية |
| Wikimedia | صور المدن | مجاني، بدون مفتاح |

وحزمتان جديدتان في الفرونت: `lucide-react` للأيقونات، و`@fontsource/ibm-plex-sans-arabic` للخط، على صفحاتي فقط.

### الـ Migration

ملف واحد: `supabase/migrations/20261102000100_ai_proposals.sql`. ودواله مطبّقة على Supabase، وما يحتاج تطبيق جديد. والملف يدمج خمسة ملفات طُبقت قبل، ومختبر على PGlite من الصفر وفوق الملفات القديمة وببيانات، وآمن لو انشغل مرتين.

### ملفات `main` اللي تعدلت

كل الباقي ملفات جديدة. وما تعدلت أي صفحة أو CSS أو اختبار من Sprint 1.

| الملف | + / - | ليش ما فيه بديل |
| --- | --- | --- |
| `frontend/src/components/PlanningPanel.tsx` | 2 / 0 | import وسطر يعرض `ProposalsPanel` |
| `frontend/src/pages/WorkspacePage.tsx` | 2 / 0 | صفحة العرض في المسارات |
| `frontend/src/lib/navigation.ts` | 4 / 1 | المسار الجديد |
| `frontend/src/lib/translations.ts` | 208 / 0 | إضافة في الآخر فقط. `language.tsx` والسكربت يقرؤون هذا الملف وحده |
| `frontend/package.json` | 2 / 0 | الخط والأيقونات |
| `frontend/package-lock.json` | 28 / 2 | الحزمتان |
| `backend/app/main.py` | 2 / 0 | تسجيل الـ router |
| `backend/app/core/config.py` | 4 / 2 | يرث `ProposalSettings`، والإعدادات نفسها في ملف جديد |
| `backend/.env.example` | 71 / 0 | أسماء الإعدادات الجديدة، بدون قيم |
| `backend/pyproject.toml` | 1 / 0 | `google-genai` |
| `backend/uv.lock` | 308 / 0 | ناتج الحزمة |

### المفاتيح ووضع Demo

المفاتيح في `backend/.env` فقط: `SUPABASE_SECRET_KEY` و`GEMINI_API_KEY` و`TAVILY_API_KEY` و`IGNAV_API_KEY` و`PROPOSALS_HASH_KEY`. والمفتاح السري يستخدمه `generation_inputs.py` وحده. و`PROPOSALS_DEMO_MODE=true` يخدم عروضًا جاهزة بدون Gemini ولا Tavily ولا Ignav.

### دقة الأسعار

- **طيران الخليج، تحقق يدوي:** 1,614 في Rihla = 1,614 في موقعهم (999 + 615)، فرق 0%. وهذي الرحلة الوحيدة المتحقق منها يدويًا.
- **الإضافات:** في موقع لوفتهانزا الإجمالي 2,729، منها 474 اختيار مقاعد اختياري. فسعرنا هو التذكرة الأساسية، وصفحة الدفع ممكن تزيد، والصفحة توضح هذا.
- باقي الأسعار يقارنها النظام آليًا مع سعر البائع. التفاصيل في `docs/price-accuracy.md`.

### التعارض المتوقع مع فرع `Ziyad`

| الملف | الحل المقترح |
| --- | --- |
| `backend/app/schemas/proposals.py` | احتفظ بحقول الجهتين |
| `frontend/src/components/ProposalsPanel.tsx` | انقل `ActivitiesPanel` إلى `ActivitiesSection.tsx`، فيختفي التعارض |
| `docs/proposal-schema-handoff.md` | احتفظ بالجهتين |
| `supabase/tests/database.test.mjs` | انقل اختبارات الأنشطة لملف خاص، لأن أدوات Sprint 2 المساعدة صارت في `proposals.test.mjs` |

### Known Limitations

- السعر النهائي ما يتأكد إلا في صفحة الدفع، وكاش Ignav حتى 30 دقيقة.
- مو كل الشركات تعطي رابطًا للرحلة نفسها، وأحيانًا تكون صفحة نتائج.
- `evidence` يوصل المتصفح ولا ينعرض.
- Essential يعتمد على تقرير Gemini، والحصة 20 طلبًا في اليوم.
- عدد المقاعد للمجموعة غير معروف، والنظام يستنتج من بحث `adults=N`.
- جملة "AI planning arrives in Sprint 2" باقية في `trip-stage.ts`، لأنه ملف Sprint 1.
- Trip.com تم تقييمه واستبعاده، ويبقى معطلًا.
- ما فيه صور فنادق ولا أسماء محطات قطار.
- اختيار الغرف وسعر المجموعة وإجمالي الإقامة وملاحظة التنازل لـ Developer 3، في فرع `prep/dev3-costs`.

### كيف تجرب

```powershell
cd backend; uv sync; uv run pytest; uv run uvicorn app.main:app --port 8001
cd frontend; npm install; npm test; npm run lint; npm run dev -- --port 5173
cd supabase; npm test; node --test tests/proposals.test.mjs
```

1. افتح رحلة أعضاؤها جاهزون، واضغط توليد العروض. أو استخدم `PROPOSALS_DEMO_MODE=true`.
2. افتح عرضًا: الملخص، والطيران، والفنادق، وخط التنقل.
3. "حدّث السعر" و"احجز" يستخدمان طلبات Ignav حقيقية، حوالي 3 لكل ضغطة.
4. بدّل اللغة، وجرّب الجوال.

---

## English

### Summary

Developer 1. The administrator generates trip proposals with AI (US-09), and each member sees a proposal's details (US-10): flights, hotels and travel between cities, with booking links and price age. Rihla does not book or take payment.

| Criterion | Status | Note |
| --- | --- | --- |
| US-09-AC01 | Met | Generation starts only when everyone is ready with shared dates. The button, API and database all refuse otherwise |
| US-09-AC02 | Partly met | Routes differ, but Essential relies on Gemini's own report, and the one real trial gave 2 of 3 proposals |
| US-10-AC01 | Met | Destination, dates, cities, their order and length, hotel, transfers and flights |
| US-10-AC02 | Met | Not available, Estimated and Unconfirmed each have a clear label |

### Technology and cost

No cost within this project's limits:

| Service | Use | Limit |
| --- | --- | --- |
| Gemini | Planning and extraction | 20 requests a day |
| Tavily | Search | Free plan, with a cache |
| Ignav | Flight prices and links | First 1,000 requests free once, **then paid**. Usage limits are built in |
| Supabase | Database | Current plan |
| Wikimedia | City photos | Free, no key |

Two new frontend packages: `lucide-react` for icons and `@fontsource/ibm-plex-sans-arabic` for the font, on these pages only.

### Migration

One file: `supabase/migrations/20261102000100_ai_proposals.sql`. Its functions are already applied on Supabase, so nothing needs applying. The file merges five that were applied earlier, and was tested on PGlite from empty, over the old files, and with data. It is safe to run twice.

### Files changed from `main`

Everything else is a new file. No Sprint 1 page, CSS or test changed.

| File | + / - | Why there is no alternative |
| --- | --- | --- |
| `frontend/src/components/PlanningPanel.tsx` | 2 / 0 | Import and one line showing `ProposalsPanel` |
| `frontend/src/pages/WorkspacePage.tsx` | 2 / 0 | The proposal page's route |
| `frontend/src/lib/navigation.ts` | 4 / 1 | The new route |
| `frontend/src/lib/translations.ts` | 208 / 0 | Added at the end only. `language.tsx` and the check script read this file alone |
| `frontend/package.json` | 2 / 0 | Font and icons |
| `frontend/package-lock.json` | 28 / 2 | Those two packages |
| `backend/app/main.py` | 2 / 0 | Router registration |
| `backend/app/core/config.py` | 4 / 2 | Inherits `ProposalSettings`, with the settings in a new file |
| `backend/.env.example` | 71 / 0 | New setting names, without values |
| `backend/pyproject.toml` | 1 / 0 | `google-genai` |
| `backend/uv.lock` | 308 / 0 | Result of that package |

### Keys and demo mode

Keys live only in `backend/.env`: `SUPABASE_SECRET_KEY`, `GEMINI_API_KEY`, `TAVILY_API_KEY`, `IGNAV_API_KEY` and `PROPOSALS_HASH_KEY`. Only `generation_inputs.py` uses the secret key. `PROPOSALS_DEMO_MODE=true` serves ready proposals with no Gemini, Tavily or Ignav.

### Price accuracy

- **Gulf Air, checked by hand:** 1,614 in Rihla = 1,614 on its site (999 + 615), a 0% gap. This is the only flight checked by hand.
- **Extras:** on Lufthansa's site the total was 2,729, including 474 of optional seat selection. Rihla shows the base fare, so checkout can be higher, and the page says so.
- Other prices are compared with the seller's automatically. See `docs/price-accuracy.md`.

### Expected conflicts with the `Ziyad` branch

| File | Suggested fix |
| --- | --- |
| `backend/app/schemas/proposals.py` | Keep both sides' fields |
| `frontend/src/components/ProposalsPanel.tsx` | Move `ActivitiesPanel` to `ActivitiesSection.tsx`, which removes the conflict |
| `docs/proposal-schema-handoff.md` | Keep both sides |
| `supabase/tests/database.test.mjs` | Move the activity tests to their own file, since the Sprint 2 helpers are now in `proposals.test.mjs` |

### Known limitations

- The final price is only confirmed at checkout, and Ignav may reuse a result for up to 30 minutes.
- Not every airline links to the flight itself. Some open a results page.
- `evidence` reaches the browser but is not shown.
- Essential relies on Gemini's own report, and the quota is 20 requests a day.
- Seats for a group are unknown, so they are inferred from a search with `adults=N`.
- "AI planning arrives in Sprint 2" stays in `trip-stage.ts`, a Sprint 1 file.
- Trip.com was evaluated and excluded, and stays off.
- No hotel photos or train station names.
- Room choice, group totals, stay totals and adjustment notes belong to Developer 3, on `prep/dev3-costs`.

### How to try it

```powershell
cd backend; uv sync; uv run pytest; uv run uvicorn app.main:app --port 8001
cd frontend; npm install; npm test; npm run lint; npm run dev -- --port 5173
cd supabase; npm test; node --test tests/proposals.test.mjs
```

1. Open a trip whose members are ready, and generate proposals. Or use `PROPOSALS_DEMO_MODE=true`.
2. Open a proposal: the summary, flights, hotels and route line.
3. "Refresh the price" and "Book" use real Ignav requests, about 3 per press.
4. Switch language, and try a phone.
