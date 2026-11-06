"""Activity-specific web photos, independent of the publisher's image domain.

Queries contain public place names only. Never send group inputs or credentials
to an image host. The original publisher and a working thumbnail stay attached.
"""

import ipaddress
import logging
import re
from urllib.parse import unquote, urlparse

import httpx2 as httpx

from app.schemas.proposals import PlaceImage
from app.services.activity_content import clean_name, normalized

logger = logging.getLogger(__name__)
SEARCH_URL = "https://serpapi.com/search.json"
IGNORED = {
    "the",
    "a",
    "an",
    "and",
    "of",
    "in",
    "on",
    "at",
    "to",
    "tour",
    "guided",
    "panoramic",
    "visit",
    "trip",
    "day",
    "experience",
}


def image_name(name: str) -> str:
    return re.sub(
        r"\b(palaces|temples|museums|towers|villages|markets)\b",
        lambda match: match.group(0)[:-1],
        clean_name(name),
        flags=re.IGNORECASE,
    )


def public_image_url(value: object) -> str | None:
    if (
        not isinstance(value, str)
        or len(value) > 2000
        or any(ord(c) < 32 for c in value)
    ):
        return None
    try:
        parsed = urlparse(value)
        host = (parsed.hostname or "").casefold()
        if parsed.scheme != "https" or not host or parsed.username or parsed.password:
            return None
        if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
            return None
        try:
            if not ipaddress.ip_address(host).is_global:
                return None
        except ValueError:
            pass
    except ValueError:
        return None
    return value


def pick_activity_image(body: dict, name: str, city: str) -> PlaceImage | None:
    wanted = set(normalized(image_name(name)).split()) - IGNORED
    # City's name alone must never match a portrait or an unrelated restaurant.
    distinctive = wanted - set(normalized(city).split())
    wanted = distinctive or wanted
    candidates = []
    for item in body.get("images_results") or []:
        if not isinstance(item, dict):
            continue
        original = public_image_url(item.get("original"))
        thumbnail = public_image_url(item.get("thumbnail"))
        source = public_image_url(item.get("link"))
        if not source or not (original or thumbnail):
            continue
        title = normalized(str(item.get("title") or ""))
        text = set(normalized(image_name(title + " " + unquote(source))).split())
        score = len(wanted & text) / len(wanted) if wanted else 0
        if score < 0.6 or any(
            term in title.split() for term in ("logo", "icon", "vector", "selfie")
        ):
            continue
        width, height = item.get("original_width"), item.get("original_height")
        if (
            isinstance(width, int)
            and isinstance(height, int)
            and min(width, height) < 120
        ):
            continue
        candidates.append(
            (
                score,
                PlaceImage(
                    url=original or thumbnail,
                    fallback_url=thumbnail
                    if original and thumbnail != original
                    else None,
                    source_url=source,
                    artist=str(item.get("source") or urlparse(source).hostname)[:200],
                    license="Source website — rights reserved",
                ),
            )
        )
    return max(candidates, key=lambda pair: pair[0])[1] if candidates else None


async def fetch_activity_image(
    name: str, city: str, category: str | None, api_key: str, transport=None
) -> PlaceImage | None:
    qualifier = "restaurant" if category == "restaurant" else "travel attraction"
    try:
        async with httpx.AsyncClient(
            timeout=6.0, trust_env=False, transport=transport
        ) as client:
            response = await client.get(
                SEARCH_URL,
                params={
                    "engine": "google_images",
                    "q": f'"{image_name(name)}" {city} {qualifier}',
                    "hl": "en",
                    "safe": "active",
                    "api_key": api_key,
                },
            )
            if response.status_code != 200:
                logger.info(
                    "activity_photo_search_failed status=%s", response.status_code
                )
                return None
            body = response.json()
            if not isinstance(body, dict) or body.get("error"):
                return None
            return pick_activity_image(body, name, city)
    except (httpx.HTTPError, ValueError, TypeError):
        logger.info("activity_photo_search_failed reason=unavailable")
        return None
