import asyncio

from activity_fixture import mock_data

from app.core.config import Settings
from app.schemas.proposals import Proposal
from app.services.place_images import _trusted_photo, with_place_images

WIKI = {
    "url": "https://upload.wikimedia.org/a.jpg",
    "source_url": "https://commons.wikimedia.org/wiki/File:a.jpg",
    "license": "CC BY-SA 4.0",
}
OPEN_SEARCH = {
    "url": "https://live.staticflickr.com/a.jpg",
    "source_url": "https://www.flickr.com/photos/someone/1",
    "license": "CC BY 2.0",
}


def test_restaurants_keep_only_photos_checked_on_wikipedia():
    assert _trusted_photo("restaurant", OPEN_SEARCH) is None
    assert _trusted_photo("restaurant", WIKI).url == WIKI["url"]


def test_landmarks_keep_open_photos_and_nothing_is_invented():
    assert _trusted_photo("attraction", OPEN_SEARCH).url == OPEN_SEARCH["url"]
    assert _trusted_photo("restaurant", None) is None


def test_restaurant_source_domain_must_be_real_and_image_schema_valid():
    assert (
        _trusted_photo(
            "restaurant", {**WIKI, "source_url": "https://evilwikimedia.org/a"}
        )
        is None
    )
    assert _trusted_photo("restaurant", {"url": "not a complete photo"}) is None


def test_saved_unrelated_restaurant_photo_is_removed_even_with_lookups_disabled():
    proposal = Proposal.model_validate(mock_data()["proposals"][0])
    restaurant = next(
        a for a in proposal.cities[0].activities if a.category == "restaurant"
    )
    from app.schemas.proposals import PlaceImage

    restaurant.image = PlaceImage.model_validate(OPEN_SEARCH)
    restaurant.image_url = "https://live.staticflickr.com/unrelated.jpg"
    clean = asyncio.run(
        with_place_images([proposal], Settings(place_images_enabled=False))
    )[0]
    result = next(a for a in clean.cities[0].activities if a.id == restaurant.id)
    assert result.image is None
    assert result.image_url is None
    assert restaurant.image is not None  # Reading must not mutate the stored proposal.
