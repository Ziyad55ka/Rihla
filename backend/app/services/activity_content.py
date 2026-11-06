"""Identity-checked, free landmark photos and bilingual reference descriptions.

No LLM request on page reads. A translated title in parentheses is not an exact
Wikipedia title. Resolve the canonical name, then check the city's presence in
the article before using its photo or Arabic language link. No generic city
photo is passed off as a photo of a landmark.
"""

import asyncio
import html
import json
import re
import sqlite3
import time
import unicodedata
from contextlib import closing
from pathlib import Path
from urllib.parse import quote

import httpx2 as httpx

from app.schemas.proposals import PlaceImage

HEADERS = {
    "User-Agent": "Rihla/1.0 (academic travel planner; public landmark references)"
}
EN_API = "https://en.wikipedia.org/w/api.php"


def clean_name(name: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"\s*\([^)]*\)\s*", " ", name)).strip()


def normalized(value: str) -> str:
    return " ".join(
        re.findall(
            r"[^\W_]+",
            "".join(
                c
                for c in unicodedata.normalize("NFKD", value.casefold())
                if not unicodedata.combining(c)
            ),
        )
    )


def matches_place(page: dict, name: str, city: str) -> bool:
    if "missing" in page or "disambiguation" in page.get("pageprops", {}):
        return False
    title, extract = str(page.get("title", "")), str(page.get("extract", ""))
    # Require geographical context even for exact names (e.g. Paris, Texas).
    if f" {normalized(city)} " not in f" {normalized(title + ' ' + extract)} ":
        return False
    ignored = {"of", "the", "de", "del", "el", "la", "a", "and", "in"}
    wanted = set(normalized(clean_name(name)).split()) - ignored
    actual = set(normalized(title).split()) - ignored
    return bool(wanted and len(wanted & actual) / len(wanted) >= 0.75)


def _plain(value: str | None, limit=1200) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", value or "")).strip()[:limit]


async def fetch_activity_content(name: str, city: str, transport=None) -> dict:
    try:
        result = await asyncio.wait_for(_api_content(name, city, transport), 2.0)
    except (httpx.HTTPError, ValueError, TimeoutError):
        result = {}
    if not result.get("image"):
        from app.services.landmark_fallback import html_content

        fallback = await html_content(name, city, transport)
        result = {**result, **fallback}
    from app.services.landmark_catalog import reviewed_content

    reviewed = reviewed_content(name, city)
    if reviewed:
        # Keep both reviewed languages together, including tariff conditions.
        result.update(reviewed)
    result.pop("price_per_person", None)  # Prices are applied fresh by source policy.
    return result


async def _api_content(name: str, city: str, transport=None) -> dict:
    async with httpx.AsyncClient(
        timeout=4.0, trust_env=False, headers=HEADERS, transport=transport
    ) as client:

        async def get(api, params):
            response = await client.get(
                api, params={"action": "query", "format": "json", **params}
            )
            response.raise_for_status()
            body = response.json()
            if not isinstance(body, dict) or body.get("error"):
                raise ValueError("Invalid reference response")
            return (body.get("query") or {}).get("pages") or {}

        common = {
            "prop": "pageimages|extracts|langlinks|pageprops",
            "piprop": "name",
            "pilicense": "free",
            "exintro": 1,
            "explaintext": 1,
            "lllang": "ar",
            "redirects": 1,
        }
        pages = await get(EN_API, {**common, "titles": clean_name(name)})
        page = next((p for p in pages.values() if matches_place(p, name, city)), None)
        if page is None:
            pages = await get(
                EN_API,
                {
                    **common,
                    "generator": "search",
                    "gsrsearch": f'"{clean_name(name)}" "{city}"',
                    "gsrlimit": 3,
                    "gsrnamespace": 0,
                },
            )
            page = next(
                (
                    p
                    for p in sorted(pages.values(), key=lambda p: p.get("index", 999))
                    if matches_place(p, name, city)
                ),
                None,
            )
        if page is None:
            return {}
        title = str(page["title"])
        result = {
            "name_en": title[:150],
            "description_en": _plain(page.get("extract")),
            "content_urls": [
                "https://en.wikipedia.org/wiki/" + quote(title.replace(" ", "_"))
            ],
        }
        filename = page.get("pageimage")
        if filename and not filename.casefold().endswith(".svg"):
            try:
                files = await get(
                    EN_API,
                    {
                        "prop": "imageinfo",
                        "iiprop": "url|extmetadata",
                        "iiurlwidth": 960,
                        "titles": "File:" + filename,
                    },
                )
                info = next(
                    (p["imageinfo"][0] for p in files.values() if p.get("imageinfo")),
                    {},
                )
                meta = info.get("extmetadata") or {}
                license_name = _plain(
                    meta.get("LicenseShortName", {}).get("value"), 100
                )
                image_url = info.get("thumburl") or info.get("url")
                if (
                    image_url
                    and license_name
                    and meta.get("NonFree", {}).get("value") != "true"
                ):
                    image = PlaceImage(
                        url=image_url,
                        source_url=info.get("descriptionurl") or image_url,
                        artist=_plain(meta.get("Artist", {}).get("value"), 200) or None,
                        license=license_name,
                    )
                    result["image"] = image.model_dump(mode="json")
            except (httpx.HTTPError, ValueError, KeyError, TypeError):
                pass  # Image failure must not discard checked descriptions.
        arabic = next(
            (
                item.get("*")
                for item in page.get("langlinks") or []
                if item.get("lang") == "ar"
            ),
            None,
        )
        if arabic:
            try:
                pages = await get(
                    "https://ar.wikipedia.org/w/api.php",
                    {
                        "prop": "extracts",
                        "titles": arabic,
                        "exintro": 1,
                        "explaintext": 1,
                        "redirects": 1,
                    },
                )
                translated = next(
                    (p for p in pages.values() if "missing" not in p), None
                )
                if translated:
                    result.update(
                        name_ar=str(translated["title"])[:150],
                        description_ar=_plain(translated.get("extract")),
                    )
                    result["content_urls"].append(
                        "https://ar.wikipedia.org/wiki/"
                        + quote(str(translated["title"]).replace(" ", "_"))
                    )
            except (httpx.HTTPError, ValueError):
                pass  # A failed Arabic lookup must not discard a checked photo.
        return result


class ActivityContentCache:
    def __init__(self, path: Path):
        self.path = path

    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.execute(
            "CREATE TABLE IF NOT EXISTS activity_content_v1 "
            "(key TEXT PRIMARY KEY, at REAL NOT NULL, body TEXT NOT NULL)"
        )
        return connection

    def get(self, name: str, city: str) -> dict | None:
        with closing(self.connect()) as connection:
            row = connection.execute(
                "SELECT at, body FROM activity_content_v1 WHERE key=?",
                (json.dumps([name, city]),),
            ).fetchone()
        if not row:
            return None
        body = json.loads(row[1])
        # Misses expire quickly, unlike successful public content.
        complete = body.get("image") and body.get("description_ar")
        return (
            body if time.time() - row[0] < (86400 * 30 if complete else 300) else None
        )

    def put(self, name: str, city: str, body: dict):
        with closing(self.connect()) as connection, connection:
            connection.execute(
                "INSERT OR REPLACE INTO activity_content_v1 VALUES (?, ?, ?)",
                (json.dumps([name, city]), time.time(), json.dumps(body)),
            )


async def content_for(name: str, city: str, cache: ActivityContentCache) -> dict:
    cached = cache.get(name, city)
    if cached is not None:
        return cached
    try:
        result = await fetch_activity_content(name, city)
    except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError):
        return {}  # Transient failures are not cached as missing places.
    cache.put(name, city, result)
    return result
