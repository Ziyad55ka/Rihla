"""Public article introductions and openly licensed photos when the API is down."""

import asyncio
import time
from collections import deque
from html.parser import HTMLParser
from urllib.parse import quote, urlsplit

import httpx2 as httpx

from app.schemas.proposals import PlaceImage

_photo_requests = deque()
_photo_blocked_until = 0.0


class Introduction(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = ""
        self.paragraphs = []
        self.arabic_url = None
        self.heading = False
        self.paragraph = None
        self.tables = 0
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "h1":
            self.heading = True
        if tag == "table":
            self.tables += 1
        if tag in {"script", "style", "sup"}:
            self.skip += 1
        if tag == "p" and not self.tables and self.title and len(self.paragraphs) < 3:
            self.paragraph = []
        if tag == "a" and attrs.get("hreflang") == "ar":
            url = attrs.get("href", "")
            if url.startswith("https://ar.wikipedia.org/wiki/"):
                self.arabic_url = url

    def handle_endtag(self, tag):
        if tag == "h1":
            self.heading = False
        if tag == "table":
            self.tables = max(0, self.tables - 1)
        if tag in {"script", "style", "sup"}:
            self.skip = max(0, self.skip - 1)
        if tag == "p" and self.paragraph is not None:
            text = " ".join("".join(self.paragraph).split())
            if len(text) >= 80:
                self.paragraphs.append(text)
            self.paragraph = None

    def handle_data(self, data):
        if self.heading:
            self.title += data
        if self.paragraph is not None and not self.skip and not self.tables:
            self.paragraph.append(data)


async def open_photo(client, name, city) -> dict | None:
    from app.services.activity_content import clean_name, normalized

    global _photo_blocked_until
    now = time.monotonic()
    while _photo_requests and _photo_requests[0] < now - 60:
        _photo_requests.popleft()
    if now < _photo_blocked_until or len(_photo_requests) >= 18:
        return None
    _photo_requests.append(now)
    response = await client.get(
        "https://api.openverse.org/v1/images/",
        params={
            "q": f"{clean_name(name)} {city}",
            "page_size": 10,
            "license": "by,by-sa,cc0,pdm",
            "mature": "false",
        },
    )
    if response.status_code == 429:
        _photo_blocked_until = now + 60
        return None
    response.raise_for_status()
    ignored = {"the", "of", "de", "del", "la", "el", "and"}
    wanted = set(normalized(clean_name(name)).split()) - ignored
    for item in response.json().get("results", []):
        title = normalized(str(item.get("title") or ""))
        tokens = set(title.split()) - ignored
        if not wanted or len(wanted & tokens) / len(wanted) < 0.75:
            continue
        if f" {normalized(city)} " not in f" {title} ":
            continue  # A search result alone does not prove the location.
        if tokens & {"replica", "miniature", "lego"}:
            continue
        if item.get("license") not in {"by", "by-sa", "cc0", "pdm"} or item.get(
            "mature"
        ):
            continue
        url = item.get("url") or ""
        landing = item.get("foreign_landing_url") or ""
        if not all(urlsplit(u).scheme == "https" for u in (url, landing)):
            continue
        return PlaceImage(
            url=url,
            fallback_url=item.get("thumbnail")
            if str(item.get("thumbnail") or "").startswith("https://api.openverse.org/")
            else None,
            source_url=landing,
            artist=str(item.get("creator") or "")[:200] or None,
            license=(
                f"CC {item['license'].upper()} {item.get('license_version') or ''}"
            ).strip(),
        ).model_dump(mode="json")
    return None


async def html_content(name, city, transport=None):
    from app.services.activity_content import clean_name, matches_place

    async with httpx.AsyncClient(
        timeout=8,
        trust_env=False,
        transport=transport,
        follow_redirects=True,
        headers={"User-Agent": "Rihla/1.0 (academic travel planner)"},
    ) as client:
        result = {}

        async def article():
            url = "https://en.wikipedia.org/wiki/" + quote(
                clean_name(name).replace(" ", "_")
            )
            response = await client.get(url)
            response.raise_for_status()
            document = Introduction()
            document.feed(response.text)
            extract = " ".join(document.paragraphs)[:1200]
            if not matches_place(
                {"title": document.title, "extract": extract}, name, city
            ):
                return {}
            result.update(
                {
                    "name_en": document.title[:150],
                    "description_en": extract,
                    "content_urls": [str(response.url)],
                }
            )

            async def arabic():
                if not document.arabic_url:
                    return
                response = await client.get(document.arabic_url)
                response.raise_for_status()
                translated = Introduction()
                translated.feed(response.text)
                if translated.title and translated.paragraphs:
                    result.update(
                        name_ar=translated.title[:150],
                        description_ar=" ".join(translated.paragraphs)[:1200],
                    )
                    result["content_urls"].append(str(response.url))

            await arabic()

        async def photo():
            image = await open_photo(client, name, city)
            if image:
                result["image"] = image

        tasks = [asyncio.create_task(article()), asyncio.create_task(photo())]
        try:
            await asyncio.wait(tasks, timeout=6.0)
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        return result
