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

import httpx2 as httpx

from app.core.config import Settings
from app.schemas.proposals import PlaceImage, Proposal

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
        if row is None or time.time() - row[0] >= self.ttl_seconds:
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


async def with_place_images(
    proposals: list[Proposal], settings: Settings
) -> list[Proposal]:
    """Adds photos for reading. They are not saved with the proposal."""
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
        return proposals
    images = dict(zip(places, found, strict=True))
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
