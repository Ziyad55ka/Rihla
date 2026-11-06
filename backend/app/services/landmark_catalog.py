"""Reviewed bilingual guides with limited, expiring admission allowances.

These stable descriptions let popular landmarks remain useful when an external
translation service is unavailable. Other places use cited model translations
or linked Arabic articles. Adding a place requires reviewing both languages.
"""

import json
from datetime import UTC, datetime
from functools import cache
from pathlib import Path

from app.services.activity_content import clean_name, normalized


@cache
def reviewed_photos():
    path = Path(__file__).resolve().parents[1] / "data" / "landmark_photos.json"
    return json.loads(path.read_text())["images"] if path.exists() else {}


# English name, city, Arabic name, English text, Arabic text, reference.
LANDMARKS = [
    (
        "Hagia Sophia",
        "Istanbul",
        "آيا صوفيا",
        (
            "A historic mosque in Istanbul. Tourist gallery access and "
            "worship access are separate; check the official visitor rules "
            "before visiting."
        ),
        (
            "مسجد تاريخي في إسطنبول. دخول رواق الزيارة السياحية منفصل عن "
            "الدخول للعبادة؛ راجع تعليمات الزيارة الرسمية قبل الذهاب."
        ),
        "https://www.tursab.org.tr/announcements/announcement-on-visits-to-hagia-sophia-grand-mosque",
    ),
    (
        "Topkapi Palace",
        "Istanbul",
        "قصر توبكابي",
        (
            "A historic palace in Istanbul. The combined visitor ticket "
            "includes the palace, Harem and Hagia Irene. The palace is closed "
            "on Tuesdays; check the official calendar."
        ),
        (
            "قصر تاريخي في إسطنبول. تشمل التذكرة المجمعة القصر والحرم وآيا "
            "إيريني. القصر مغلق أيام الثلاثاء؛ تحقق من التقويم الرسمي."
        ),
        "https://www.millisaraylar.gov.tr/Lokasyon/2/Topkapi-Sarayi",
    ),
    (
        "Plaza Mayor",
        "Madrid",
        "ساحة بلازا مايور",
        (
            "A historic square in Madrid for a city walk. Shops, meals and "
            "organised activities have separate costs."
        ),
        (
            "ساحة تاريخية في مدريد للتنزه. للمشتريات "
            "والوجبات والأنشطة المنظمة تكاليف منفصلة."
        ),
        "https://www.esmadrid.com/en/tourist-information/plaza-mayor-madrid",
    ),
    (
        "Basílica de San Francisco El Grande",
        "Madrid",
        "كنيسة سان فرانسيسكو إل غراندي",
        (
            "A historic church in Madrid. Check visitor access, services and "
            "admission arrangements before visiting."
        ),
        (
            "كنيسة تاريخية في مدريد. تحقق من إتاحة الزيارة ومواعيد الشعائر "
            "وترتيبات الدخول قبل التوجه إليها."
        ),
        "https://en.wikipedia.org/wiki/Royal_Basilica_of_Saint_Francis_the_Great",
    ),
    (
        "Alcalá Gate",
        "Madrid",
        "بوابة ألكالا",
        (
            "A monumental gateway in Madrid's Plaza de la Independencia. The "
            "suggested activity is viewing the exterior from the surrounding "
            "public area."
        ),
        (
            "بوابة أثرية في ساحة الاستقلال بمدريد. يشمل الاقتراح مشاهدة "
            "البوابة من الخارج من المنطقة العامة المحيطة."
        ),
        "https://www.esmadrid.com/en/tourist-information/puerta-de-alcala",
    ),
    (
        "Retiro Park",
        "Madrid",
        "حديقة ريتيرو",
        (
            "A park in Madrid for walks and outdoor relaxation. Paid "
            "attractions, rentals and special activities are separate from a "
            "park walk."
        ),
        (
            "حديقة في مدريد للمشي والاسترخاء في الهواء الطلق. للمعالم المدفوعة "
            "والتأجير والأنشطة الخاصة تكاليف منفصلة عن التنزه في الحديقة."
        ),
        "https://www.esmadrid.com/en/tourist-information/parque-del-retiro",
    ),
    (
        "Prado Museum",
        "Madrid",
        "متحف برادو",
        (
            "An art museum in Madrid, with a collection of European painting. "
            "Check the official visitor information for tickets and temporary "
            "exhibitions."
        ),
        (
            "متحف فني في مدريد يضم مجموعة من اللوحات الأوروبية. راجع معلومات "
            "الزيارة الرسمية لمعرفة التذاكر والمعارض المؤقتة."
        ),
        "https://www.museodelprado.es/en/visit-the-museum",
    ),
    (
        "Royal Palace of Madrid",
        "Madrid",
        "القصر الملكي في مدريد",
        (
            "A royal palace in Madrid. Its visitor route introduces the "
            "palace's rooms and historic setting; check the official site "
            "before visiting."
        ),
        (
            "قصر ملكي في مدريد. يعرّف مسار الزيارة بقاعات القصر وطابعه "
            "التاريخي؛ راجع الموقع الرسمي قبل الزيارة."
        ),
        "https://www.patrimonionacional.es/en/visita/royal-palace-madrid",
    ),
    (
        "Mosque–Cathedral of Córdoba",
        "Córdoba",
        "جامع قرطبة وكاتدرائيتها",
        (
            "A historic religious monument in Córdoba. Explore its "
            "architecture and history, and check the official visitor guidance "
            "and ticket options."
        ),
        (
            "معلم ديني تاريخي في قرطبة. تعرّف على عمارته وتاريخه، وراجع "
            "إرشادات الزيارة الرسمية وخيارات التذاكر."
        ),
        "https://mezquita-catedraldecordoba.es/en/",
    ),
    (
        "Eiffel Tower",
        "Paris",
        "برج إيفل",
        (
            "A landmark tower in Paris with viewing levels overlooking the "
            "city. Ticket options differ by level and access method; check the "
            "official site for availability."
        ),
        (
            "برج بارز في باريس يضم مستويات مشاهدة تطل على المدينة. تختلف "
            "خيارات التذاكر بحسب المستوى وطريقة الصعود؛ تحقق من التوفر عبر "
            "الموقع الرسمي."
        ),
        "https://www.toureiffel.paris/en",
    ),
    (
        "Champs-Élysées",
        "Paris",
        "الشانزليزيه",
        (
            "A famous avenue in Paris for a city walk and browsing shops. "
            "Purchases, meals and nearby attractions have separate costs."
        ),
        (
            "شارع شهير في باريس للتنزه واستكشاف المتاجر. للمشتريات والوجبات "
            "والمعالم القريبة تكاليف منفصلة."
        ),
        "https://en.wikipedia.org/wiki/Champs-%C3%89lys%C3%A9es",
    ),
    (
        "Louvre",
        "Paris",
        "متحف اللوفر",
        (
            "An art museum in Paris. Explore its collections and visitor "
            "trails, and check the official site for ticket arrangements and "
            "current exhibitions."
        ),
        (
            "متحف فني في باريس. استكشف مجموعاته ومسارات الزيارة، وراجع الموقع "
            "الرسمي لمعرفة ترتيبات التذاكر والمعارض الحالية."
        ),
        "https://www.louvre.fr/en",
    ),
]


def reviewed_content(name: str, city: str) -> dict:
    key = normalized(clean_name(name)).replace("ı", "i")
    for en, place, ar, description_en, description_ar, reference in LANDMARKS:
        if normalized(place) == normalized(city) and key in {
            normalized(en).replace("ı", "i"),
            normalized(ar),
        }:
            result = dict(
                name_en=en,
                name_ar=ar,
                description_en=description_en,
                description_ar=description_ar,
                content_urls=[reference],
            )
            # Reviewed adult admission planning guides, not dated availability
            # or live currency conversion. Expire rather than silently drift.
            if datetime.now(UTC).date().isoformat() <= "2026-12-06":
                guide = {
                    "Hagia Sophia": (
                        105,
                        (
                            "Tourist gallery reference: EUR 25 per person. "
                            "SAR is a rounded planning allowance, not live "
                            "exchange or a dated ticket quote; worship access "
                            "has different rules."
                        ),
                        (
                            "السعر المرجعي لرواق الزيارة السياحية: ٢٥ يورو "
                            "للفرد. المبلغ بالريال مخصص تخطيط مقرب، وليس "
                            "تحويلًا مباشرًا أو عرض تذكرة بتاريخ محدد؛ لدخول "
                            "العبادة شروط مختلفة."
                        ),
                    ),
                    "Topkapi Palace": (
                        210,
                        (
                            "Foreign adult combined ticket reference: TRY "
                            "2,750. SAR is a rounded planning allowance, not "
                            "live exchange or a dated ticket quote; "
                            "concessions and future tariffs may differ."
                        ),
                        (
                            "السعر المرجعي للتذكرة المجمعة للبالغ الأجنبي: "
                            "٢٧٥٠ ليرة تركية. المبلغ بالريال مخصص تخطيط مقرب، "
                            "وليس تحويلًا مباشرًا أو عرض تذكرة بتاريخ محدد؛ "
                            "تختلف الخصومات وقد تتغير التعرفة مستقبلًا."
                        ),
                    ),
                    "Prado Museum": (
                        70,
                        (
                            "Adult general admission: EUR 15. SAR is "
                            "a rough planning allowance; discounts "
                            "and availability vary."
                        ),
                        (
                            "الدخول العام للبالغ: ١٥ يورو. المبلغ "
                            "بالريال مخصص تخطيط تقريبي؛ تختلف "
                            "الخصومات والتوفر."
                        ),
                    ),
                    "Royal Palace of Madrid": (
                        85,
                        (
                            "Basic adult admission reference: EUR 18. "
                            "SAR is a rough planning allowance; "
                            "additional services cost extra."
                        ),
                        (
                            "السعر المرجعي الأساسي للبالغ: ١٨ يورو. "
                            "المبلغ بالريال مخصص تخطيط تقريبي؛ "
                            "للخدمات الإضافية رسوم منفصلة."
                        ),
                    ),
                }.get(en)
                if guide:
                    result["price_per_person"] = dict(
                        amount_sar=str(guide[0]), status="Unconfirmed", evidence=[]
                    )
                    result["description_en"] += " " + guide[1]
                    result["description_ar"] += " " + guide[2]
                    if en == "Prado Museum":
                        result["content_urls"] = [
                            "https://www.museodelprado.es/en/visit/opening-times-and-prices"
                        ]
            image = reviewed_photos().get(f"{normalized(en)}|{normalized(city)}")
            if image:
                result["image"] = image
            return result
    return {}


def enrich_reviewed(proposal):
    """Apply the same current guide to display, cost estimates and budget guards."""
    from app.schemas.proposals import ActivityPrice, PlaceImage

    stays = []
    for stay in proposal.cities:
        activities = []
        for activity in stay.activities:
            content = reviewed_content(activity.name.value or "", stay.city)
            guide = content.pop("price_per_person", None)
            content = {
                key: value
                for key, value in content.items()
                if key in {"content_urls", "image", "description_ar", "description_en"}
                or not getattr(activity, key, None)
            }
            if content.get("content_urls"):
                content["content_urls"] = list(
                    dict.fromkeys(activity.content_urls + content["content_urls"])
                )[:2]
            if guide and (
                activity.price_per_person.amount_sar is None
                or (
                    activity.price_per_person.status == "Unconfirmed"
                    and not activity.price_per_person.evidence
                )
            ):
                content["price_per_person"] = ActivityPrice.model_validate(guide)
            if content.get("image"):
                content["image"] = PlaceImage.model_validate(content["image"])
            activities.append(
                activity.model_copy(update=content) if content else activity
            )
        stays.append(stay.model_copy(update={"activities": activities}))
    return proposal.model_copy(update={"cities": stays})
