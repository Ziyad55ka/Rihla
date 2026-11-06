import asyncio
from copy import deepcopy

import httpx2 as httpx
import pytest

from app.services.activity_images import (
    fetch_activity_image,
    pick_activity_image,
    public_image_url,
)


def image_result():
    return {
        "images_results": [
            {
                "title": "Gyeongbokgung Palace Seoul — visitor photos",
                "original": "https://travel.example/seoul-palace.jpg",
                "thumbnail": "https://thumbs.example/seoul-palace.jpg",
                "link": "https://travel.example/gyeongbokgung-palace-seoul",
                "source": "Travel guide",
                "original_width": 1200,
                "original_height": 800,
            }
        ]
    }


def test_correct_place_photo_can_come_from_any_publisher_with_a_thumbnail():
    photo = pick_activity_image(image_result(), "Gyeongbokgung Palace", "Seoul")
    assert photo and photo.url == "https://travel.example/seoul-palace.jpg"
    assert photo.fallback_url == "https://thumbs.example/seoul-palace.jpg"
    assert photo.source_url == "https://travel.example/gyeongbokgung-palace-seoul"
    assert "rights reserved" in photo.license


def test_plural_place_label_still_matches_the_same_palace():
    assert (
        pick_activity_image(image_result(), "Gyeongbokgung Palaces", "Seoul")
        is not None
    )


def test_city_match_alone_does_not_select_an_unrelated_person_or_place():
    body = image_result()
    body["images_results"][0].update(
        title="A couple in Istanbul", link="https://travel.example/istanbul-selfie"
    )
    assert pick_activity_image(body, "Biz Istanbul", "Istanbul") is None


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "data:image/png;base64,xx",
        "http://image.example/a.jpg",
        "https://127.0.0.1/a",
        "https://localhost/a",
        "https://10.0.0.1/a",
        "https://user:secret@image.example/a",
    ],
)
def test_images_never_point_at_credentials_scripts_or_private_networks(url):
    assert public_image_url(url) is None


def test_broken_original_can_use_a_public_thumbnail_and_tiny_icons_are_ignored():
    body = image_result()
    body["images_results"][0]["original"] = "javascript:bad"
    assert pick_activity_image(body, "Gyeongbokgung Palace", "Seoul").url.startswith(
        "https://thumbs.example/"
    )
    small = deepcopy(body)
    small["images_results"][0]["original_width"] = 32
    assert pick_activity_image(small, "Gyeongbokgung Palace", "Seoul") is None


def test_one_public_image_query_uses_the_place_and_city_not_group_data():
    seen = []

    def handle(request):
        seen.append(request)
        return httpx.Response(200, json=image_result())

    photo = asyncio.run(
        fetch_activity_image(
            "Gyeongbokgung Palace",
            "Seoul",
            "attraction",
            "test-key",
            httpx.MockTransport(handle),
        )
    )
    assert photo
    assert len(seen) == 1
    assert seen[0].url.params["engine"] == "google_images"
    assert '"Gyeongbokgung Palace" Seoul' in seen[0].url.params["q"]
    assert "budget" not in str(seen[0].url)
