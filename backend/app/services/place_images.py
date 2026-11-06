"""Free photos of cities and destinations from Wikipedia, with their credit.

No key is needed. Wikimedia asks for a descriptive User-Agent, and only freely licensed
files are accepted. A missing photo is normal: the page has a designed placeholder.
"""

import asyncio
import html
import json
import logging
import re
import sqlite3
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx2 as httpx
from pydantic import ValidationError

from app.core.config import Settings
from app.schemas.proposals import PlaceImage, Proposal
from app.services.activity_content import ActivityContentCache, content_for
from app.services.activity_images import (
    fetch_activity_image,
    image_name,
    public_image_url,
)

logger = logging.getLogger(__name__)

API_URL = "https://en.wikipedia.org/w/api.php"
HEADERS = {
    "User-Agent": "Rihla/1.0 (https://github.com/Ziyad55ka/Rihla; academic project)"
}
IMAGE_WIDTH = 1280
# Reading proposals must stay quick, so a slow lookup just shows the placeholder.
READ_TIMEOUT_SECONDS = 4.0


class ImageCache:
    """Remembers a found photo, or that there is none. Public data only."""

    def __init__(self, path: Path, ttl_seconds: int) -> None:
        self.path = path
        self.ttl_seconds = ttl_seconds

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.execute(
            "CREATE TABLE IF NOT EXISTS images "
            "(place TEXT PRIMARY KEY, at REAL NOT NULL, body TEXT)"
        )
        return connection

    def get(self, place: str) -> tuple[bool, PlaceImage | None]:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT at, body FROM images WHERE place = ?", (place,)
            ).fetchone()
        finally:
            connection.close()
        if row is None or time.time() - row[0] >= (self.ttl_seconds if row[1] else 300):
            return False, None
        return True, PlaceImage(**json.loads(row[1])) if row[1] else None

    def put(self, place: str, image: PlaceImage | None) -> None:
        connection = self._connect()
        try:
            with connection:
                connection.execute(
                    "INSERT OR REPLACE INTO images VALUES (?, ?, ?)",
                    (
                        place,
                        time.time(),
                        image.model_dump_json() if image else None,
                    ),
                )
        finally:
            connection.close()


def _plain(text: str | None) -> str | None:
    cleaned = html.unescape(re.sub(r"<[^>]+>", "", text or "")).strip()
    return cleaned[:200] or None


def _meta(info: dict, name: str) -> str | None:
    return (info.get("extmetadata") or {}).get(name, {}).get("value")


async def fetch_place_image(
    place: str, transport: httpx.AsyncBaseTransport | None = None
) -> PlaceImage | None:
    """The main free photo of the Wikipedia page with this exact title, or None."""
    async with httpx.AsyncClient(
        timeout=READ_TIMEOUT_SECONDS,
        trust_env=False,
        transport=transport,
        headers=HEADERS,
    ) as client:
        page = await client.get(
            API_URL,
            params={
                "action": "query",
                "format": "json",
                "redirects": 1,
                "prop": "pageimages",
                "piprop": "name",
                "pilicense": "free",
                "titles": place,
            },
        )
        page.raise_for_status()
        pages = (page.json().get("query") or {}).get("pages") or {}
        name = next((item.get("pageimage") for item in pages.values()), None)
        if not name or name.lower().endswith(".svg"):
            return None
        file = await client.get(
            API_URL,
            params={
                "action": "query",
                "format": "json",
                "prop": "imageinfo",
                "iiprop": "url|extmetadata",
                "iiurlwidth": IMAGE_WIDTH,
                "titles": f"File:{name}",
            },
        )
        file.raise_for_status()
    pages = (file.json().get("query") or {}).get("pages") or {}
    info = next(
        (item["imageinfo"][0] for item in pages.values() if item.get("imageinfo")),
        None,
    )
    if not info:
        return None
    licence = _plain(_meta(info, "LicenseShortName"))
    url = info.get("thumburl") or info.get("url")
    if _meta(info, "NonFree") == "true" or not licence or not url:
        return None
    return PlaceImage(
        url=url,
        source_url=info.get("descriptionurl") or url,
        artist=_plain(_meta(info, "Artist")),
        license=licence[:100],
    )


async def _image_for(place: str, cache: ImageCache) -> PlaceImage | None:
    known, image = cache.get(place)
    if known:
        return image
    try:
        image = await fetch_place_image(place)
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        # Not remembered, so a passing network failure can recover on the next read.
        logger.info("place_image_failed")
        return None
    cache.put(place, image)
    return image


# Polite to Wikimedia: a few lookups at a time. Found photos are cached, so a
# lookup cut off by the time limit is simply finished on a later read.
ACTIVITY_LOOKUPS_AT_ONCE = 6
ACTIVITY_TIMEOUT_SECONDS = 9.0
# Photo searches per pass. Every photo is cached, so later reads fill the rest.
# Activities with no photo are not shown, so this covers a full city list.
ACTIVITY_PHOTO_SEARCHES = 36


# Photos checked against the place's own Wikipedia article. An open photo search
# only matches words in a title: a restaurant named "Beyaz İstanbul" matched a
# personal photo titled the same on 6 Nov 2026, so restaurants use these only.
CHECKED_PHOTO_HOSTS = ("wikipedia.org", "wikimedia.org")


def _trusted_photo(category: str | None, image: dict | None) -> PlaceImage | None:
    if not image:
        return None
    try:
        photo = PlaceImage.model_validate(image)
    except ValidationError:
        return None
    if not public_image_url(photo.url) or not public_image_url(photo.source_url):
        return None
    if category == "restaurant":
        host = (urlparse(photo.source_url or "").hostname or "").casefold()
        if photo.license != "Source website — rights reserved" and not any(
            host == domain or host.endswith(f".{domain}")
            for domain in CHECKED_PHOTO_HOSTS
        ):
            return None
    return photo


def sanitize_activity_photos(proposals: list[Proposal]) -> list[Proposal]:
    """Apply the same identity policy to saved images, even when lookups fail."""
    return [
        proposal.model_copy(
            update={
                "cities": [
                    stay.model_copy(
                        update={
                            "activities": [
                                activity.model_copy(
                                    update={
                                        "image": _trusted_photo(
                                            activity.category,
                                            activity.image.model_dump()
                                            if activity.image
                                            else None,
                                        ),
                                        "image_url": None
                                        if activity.category == "restaurant"
                                        else activity.image_url,
                                    }
                                )
                                for activity in stay.activities
                            ]
                        }
                    )
                    for stay in proposal.cities
                ]
            }
        )
        for proposal in proposals
    ]


async def _with_activity_images(
    proposals: list[Proposal], cache: ImageCache, settings: Settings
) -> list[Proposal]:
    """Resolve actual landmarks, with city context and linked Arabic descriptions."""
    names = sorted(
        {
            (activity.name.value, stay.city)
            for item in proposals
            for stay in item.cities
            for activity in stay.activities
            if activity.name.value
        }
    )
    if not names:
        return proposals
    gate = asyncio.Semaphore(ACTIVITY_LOOKUPS_AT_ONCE)
    found: dict[tuple[str, str], dict] = {}
    content_cache = ActivityContentCache(cache.path)
    examples = {
        (a.name.value, city.city): a
        for proposal in proposals
        for city in proposal.cities
        for a in city.activities
        if a.name.value
    }
    source_requests = 0

    async def one(name: str, city: str) -> None:
        nonlocal source_requests
        async with gate:
            activity = examples[(name, city)]
            existing = _trusted_photo(
                activity.category,
                activity.image.model_dump() if activity.image else None,
            )
            cached = content_cache.get(name, city) or {}
            cached_photo = _trusted_photo(activity.category, cached.get("image"))
            needs_words = not (activity.description_ar and activity.description_en)
            query_name = image_name(activity.name_en or name)
            image_key = f"activity-web-v1|{activity.category}|{query_name}|{city}"

            async def web_photo():
                nonlocal source_requests
                if existing or cached_photo or not settings.serpapi_api_key:
                    return None
                known, photo = cache.get(image_key)
                if known:
                    return photo
                if source_requests >= ACTIVITY_PHOTO_SEARCHES:
                    return None
                source_requests += 1
                photo = await fetch_activity_image(
                    query_name, city, activity.category, settings.serpapi_api_key
                )
                cache.put(image_key, photo)
                return photo

            async def words():
                if existing and not needs_words:
                    return {}
                if not needs_words and settings.serpapi_api_key:
                    return cached
                return await content_for(name, city, content_cache)

            details, web = await asyncio.gather(words(), web_photo())
            photo = (
                existing
                or web
                or _trusted_photo(activity.category, details.get("image"))
            )
            if photo is None and not needs_words and settings.serpapi_api_key:
                details = await content_for(name, city, content_cache)
                photo = _trusted_photo(activity.category, details.get("image"))
            found[(name, city)] = {
                **details,
                "image": photo.model_dump() if photo else None,
            }

    tasks = [asyncio.ensure_future(one(name, city)) for name, city in names]
    _, pending = await asyncio.wait(tasks, timeout=ACTIVITY_TIMEOUT_SECONDS)
    for task in pending:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    if not any(found.values()):
        return proposals
    return [
        item.model_copy(
            update={
                "cities": [
                    stay.model_copy(
                        update={
                            "activities": [
                                activity.model_copy(
                                    update={
                                        **{
                                            key: value
                                            for key, value in found.get(
                                                (activity.name.value or "", stay.city),
                                                {},
                                            ).items()
                                            if key == "image"
                                            or not getattr(activity, key, None)
                                        },
                                        "image": _trusted_photo(
                                            activity.category,
                                            found.get(
                                                (activity.name.value, stay.city), {}
                                            ).get("image"),
                                        )
                                        or activity.image,
                                    }
                                )
                                for activity in stay.activities
                            ]
                        }
                    )
                    for stay in item.cities
                ]
            }
        )
        for item in proposals
    ]


async def with_place_images(
    proposals: list[Proposal], settings: Settings
) -> list[Proposal]:
    """Adds photos for reading. They are not saved with the proposal."""
    proposals = sanitize_activity_photos(proposals)
    if not settings.place_images_enabled or not proposals:
        return proposals
    cache = ImageCache(settings.place_images_db, settings.place_images_ttl_days * 86400)
    places = sorted(
        {item.destination for item in proposals}
        | {stay.city for item in proposals for stay in item.cities}
    )
    try:
        found = await asyncio.wait_for(
            asyncio.gather(*(_image_for(place, cache) for place in places)),
            READ_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        # City photo latency must not suppress every activity photo.
        found = [None] * len(places)
    images = dict(zip(places, found, strict=True))
    proposals = await _with_activity_images(proposals, cache, settings)
    return [
        item.model_copy(
            update={
                "image": images[item.destination]
                or next(
                    (images[stay.city] for stay in item.cities if images[stay.city]),
                    None,
                ),
                "cities": [
                    stay.model_copy(update={"image": images[stay.city]})
                    for stay in item.cities
                ],
            }
        )
        for item in proposals
    ]
