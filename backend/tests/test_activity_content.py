import asyncio

import httpx2 as httpx
import pytest

from app.services.activity_content import (
    ActivityContentCache,
    _api_content,
    clean_name,
    fetch_activity_content,
    matches_place,
)


def page(**changes):
    return {
        "title": "Prado Museum",
        "extract": "The Prado Museum is in Madrid, Spain.",
        "pageimage": "Prado.jpg",
        "langlinks": [{"lang": "ar", "*": "متحف برادو"}],
        **changes,
    }


def test_identity_checks_city_name_disambiguation_and_parenthetical_translation():
    assert clean_name("Prado Museum (متحف برادو)") == "Prado Museum"
    assert matches_place(page(), "Prado Museum (متحف برادو)", "Madrid")
    assert not matches_place(page(), "Prado Museum", "Paris")
    assert not matches_place(page(title="Madrid"), "Prado Museum", "Madrid")
    assert not matches_place(
        page(pageprops={"disambiguation": ""}), "Prado Museum", "Madrid"
    )


def test_bilingual_reference_and_licensed_image():
    def handler(request):
        params = request.url.params
        if request.url.host.startswith("ar."):
            value = {"title": "متحف برادو", "extract": "متحف فني في مدريد."}
        elif params.get("prop") == "imageinfo":
            value = {
                "imageinfo": [
                    {
                        "thumburl": "https://upload.wikimedia.org/prado.jpg",
                        "descriptionurl": "https://commons.wikimedia.org/wiki/File:Prado.jpg",
                        "extmetadata": {
                            "LicenseShortName": {"value": "CC BY-SA 4.0"},
                            "Artist": {"value": "<b>Artist</b>"},
                        },
                    }
                ]
            }
        else:
            value = page()
        return httpx.Response(200, json={"query": {"pages": {"1": value}}})

    result = asyncio.run(
        _api_content(
            "Prado Museum (متحف برادو)", "Madrid", httpx.MockTransport(handler)
        )
    )
    assert result["name_ar"] == "متحف برادو"
    assert result["description_en"].startswith("The Prado")
    assert result["image"]["artist"] == "Artist"
    assert len(result["content_urls"]) == 2


def test_image_outage_preserves_descriptions():
    def handler(request):
        if request.url.params.get("prop") == "imageinfo":
            return httpx.Response(503)
        return httpx.Response(200, json={"query": {"pages": {"1": page(langlinks=[])}}})

    result = asyncio.run(
        _api_content("Prado Museum", "Madrid", httpx.MockTransport(handler))
    )
    assert result["description_en"] and "image" not in result


def test_miss_cache_expires_in_five_minutes_but_success_does_not(tmp_path, monkeypatch):
    now = [1000]
    monkeypatch.setattr("app.services.activity_content.time.time", lambda: now[0])
    cache = ActivityContentCache(tmp_path / "public.sqlite3")
    cache.put("Missing", "Madrid", {})
    success = {
        "name_en": "Prado",
        "image": {"url": "https://example.test/photo"},
        "description_ar": "متحف",
    }
    cache.put("Prado", "Madrid", success)
    now[0] += 301
    assert cache.get("Missing", "Madrid") is None
    assert cache.get("Prado", "Madrid") == success


def test_fallback_photo_survives_article_outage_and_has_reviewed_bilingual_copy():
    from app.services.landmark_catalog import reviewed_content
    from app.services.landmark_fallback import html_content

    def handler(request):
        if request.url.host != "api.openverse.org":
            return httpx.Response(403)
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": "Prado Museum, Madrid, Spain",
                        "license": "by-sa",
                        "license_version": "2.0",
                        "creator": "Photographer",
                        "url": "https://example.test/photo.jpg",
                        "foreign_landing_url": "https://example.test/credit",
                    }
                ]
            },
        )

    result = asyncio.run(
        html_content("Prado Museum", "Madrid", httpx.MockTransport(handler))
    )
    assert result["image"]["artist"] == "Photographer"
    reviewed = reviewed_content("Prado Museum", "Madrid")
    assert reviewed["description_ar"] and reviewed["description_en"]
    final = asyncio.run(
        fetch_activity_content("Prado Museum", "Madrid", httpx.MockTransport(handler))
    )
    assert final["image"]["source_url"] == reviewed["image"]["source_url"]


def test_fallback_rejects_wrong_city_and_noncommercial_or_mature_photos():
    from app.services.landmark_fallback import open_photo

    def handler(request):
        return httpx.Response(
            200,
            json={
                "results": [
                    {"title": "Prado Museum, Paris", "license": "by"},
                    {"title": "Prado Museum, Madrid", "license": "by-nc"},
                    {"title": "Prado Museum, Madrid", "license": "by", "mature": True},
                ]
            },
        )

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await open_photo(client, "Prado Museum", "Madrid")

    assert asyncio.run(run()) is None


def test_reviewed_price_guides_expire_and_preserve_a_provider_price(monkeypatch):
    import json
    from datetime import UTC, datetime
    from pathlib import Path

    from app.schemas.proposals import Proposal
    from app.services import landmark_catalog
    from app.services.landmark_catalog import enrich_reviewed, reviewed_content

    class Active:
        @staticmethod
        def now(tz):
            return datetime(2026, 11, 6, tzinfo=UTC)

    monkeypatch.setattr(landmark_catalog, "datetime", Active)
    raw = json.loads((Path(__file__).parent / "fixtures/activities.json").read_text())[
        "proposals"
    ][0]
    proposal = Proposal.model_validate(raw)
    proposal.cities[0].city = "Madrid"
    item = proposal.cities[0].activities[0]
    item.name.value = "Prado Museum"
    item.price_per_person.status = "Estimated"
    old = item.price_per_person.amount_sar
    assert (
        enrich_reviewed(proposal).cities[0].activities[0].price_per_person.amount_sar
        == old
    )
    item.price_per_person.amount_sar = None
    item.price_per_person.status = "Not available"
    current = enrich_reviewed(proposal)
    assert current.cities[0].activities[0].price_per_person.amount_sar == 70
    assert current.cities[0].activities[0].price_per_person.status == "Unconfirmed"

    class Later:
        @staticmethod
        def now(tz):
            return datetime(2027, 1, 1, tzinfo=UTC)

    monkeypatch.setattr(landmark_catalog, "datetime", Later)
    assert "price_per_person" not in reviewed_content("Prado Museum", "Madrid")


@pytest.mark.parametrize(
    "name,amount,native",
    [("Hagia Sophia", 105, "EUR 25"), ("Topkapı Palace", 210, "TRY 2,750")],
)
def test_reviewed_istanbul_tariffs_replace_model_guesses_but_not_source_quotes(
    monkeypatch, name, amount, native
):
    import json
    from datetime import UTC, datetime
    from pathlib import Path

    from app.schemas.proposals import Proposal
    from app.services import landmark_catalog

    class Active:
        @staticmethod
        def now(tz):
            return datetime(2026, 11, 6, tzinfo=UTC)

    monkeypatch.setattr(landmark_catalog, "datetime", Active)
    raw = json.loads((Path(__file__).parent / "fixtures/activities.json").read_text())[
        "proposals"
    ][0]
    proposal = Proposal.model_validate(raw)
    proposal.cities[0].city = "Istanbul"
    item = proposal.cities[0].activities[0]
    item.name.value = name
    item.price_per_person = item.price_per_person.model_copy(
        update={"amount_sar": 120, "status": "Unconfirmed", "evidence": []}
    )
    updated = landmark_catalog.enrich_reviewed(proposal).cities[0].activities[0]
    assert updated.price_per_person.amount_sar == amount
    assert updated.price_per_person.status == "Unconfirmed"
    assert native in updated.description_en
    assert updated.description_ar and updated.content_urls
    item.price_per_person.status = "Estimated"
    assert (
        landmark_catalog.enrich_reviewed(proposal)
        .cities[0]
        .activities[0]
        .price_per_person.amount_sar
        == 120
    )
