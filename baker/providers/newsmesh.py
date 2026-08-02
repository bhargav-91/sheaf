"""NewsMesh provider: port of the app's NewsMeshService.

Breadth filler behind the publication RSS feeds. Requires
NEWSMESH_API_KEY in the environment; the adapter is skipped otherwise.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime

import requests

from ..models import NormalizedStory

log = logging.getLogger(__name__)

_HOST = "https://api.newsmesh.co"
_RATE_LIMIT_SLEEP = 1.1  # NewsMesh throttles per-second

_ENDPOINTS = (
    ("/v1/latest?country=in&category=world,politics&limit=10", "frontPage", "HEADLINES"),
    ("/v1/search?q=Bengaluru+OR+Karnataka&country=in&limit=10", "city", "CITY"),
    ("/v1/latest?country=in&category=politics&limit=10", "nation", "NATIONAL"),
    ("/v1/latest?country=in&category=business&limit=10", "business", "BUSINESS"),
    ("/v1/latest?country=in&category=sports&limit=10", "sport", "SPORTS"),
    ("/v1/latest?category=world&limit=10", "frontPage", "WORLD"),
)


class NewsMeshProvider:
    name = "newsmesh"

    def __init__(self, api_key: str):
        self.api_key = api_key

    def fetch(self) -> list[NormalizedStory]:
        stories: list[NormalizedStory] = []
        for i, (endpoint, section, category) in enumerate(_ENDPOINTS):
            if i > 0:
                time.sleep(_RATE_LIMIT_SLEEP)
            try:
                stories.extend(self._fetch_section(endpoint, section, category))
            except Exception:
                log.exception("newsmesh: %s failed", category)
        return stories

    def _fetch_section(self, endpoint: str, section: str,
                       category: str) -> list[NormalizedStory]:
        url = f"{_HOST}{endpoint}&apiKey={self.api_key}"
        resp = requests.get(url, timeout=10)
        payload = resp.json()
        articles = payload.get("data") or []

        out: list[NormalizedStory] = []
        for a in articles:
            if a.get("type") == "video":
                continue
            title, link = a.get("title"), a.get("link")
            if not title or not link:
                continue
            out.append(NormalizedStory(
                headline=title,
                deck=a.get("description") or "",
                article_url=link,
                section=section,
                category=category,
                source_name=a.get("source") or "NewsMesh",
                provider=self.name,
                image_url=a.get("media_url"),
                published_at=_parse_date(a.get("published_date")),
                source_weight=60,
            ))
        log.info("newsmesh: %s status=%s -> %d stories",
                 category, resp.status_code, len(out))
        return out


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z",
                "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None
