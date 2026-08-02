"""NewsData.io provider: second aggregator, breadth filler.

Requires NEWSDATA_API_KEY in the environment; skipped otherwise.
Free tier: 200 credits/day, 30 per 15 min — a daily bake uses 6.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

import requests

from ..models import NormalizedStory

log = logging.getLogger(__name__)

_HOST = "https://newsdata.io/api/1/latest"

_QUERIES = (
    ({"country": "in", "category": "top"}, "frontPage", "HEADLINES"),
    ({"country": "in", "q": "Bengaluru OR Karnataka"}, "city", "CITY"),
    ({"country": "in", "category": "politics"}, "nation", "NATIONAL"),
    ({"country": "in", "category": "business"}, "business", "BUSINESS"),
    ({"country": "in", "category": "sports"}, "sport", "SPORTS"),
    ({"category": "world"}, "frontPage", "WORLD"),
)


class NewsDataProvider:
    name = "newsdata"

    def __init__(self, api_key: str):
        self.api_key = api_key

    def fetch(self) -> list[NormalizedStory]:
        stories: list[NormalizedStory] = []
        for i, (params, section, category) in enumerate(_QUERIES):
            if i > 0:
                time.sleep(0.5)
            try:
                stories.extend(self._fetch_query(params, section, category))
            except Exception:
                log.exception("newsdata: %s failed", category)
        return stories

    def _fetch_query(self, params: dict, section: str,
                     category: str) -> list[NormalizedStory]:
        query = {"apikey": self.api_key, "language": "en", "size": 10, **params}
        resp = requests.get(_HOST, params=query, timeout=10)
        payload = resp.json()
        if payload.get("status") != "success":
            log.warning("newsdata: %s -> %s", category,
                        payload.get("results", {}).get("message", resp.status_code))
            return []

        out: list[NormalizedStory] = []
        for a in payload.get("results") or []:
            if a.get("video_url"):
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
                source_name=a.get("source_name") or a.get("source_id") or "NewsData",
                provider=self.name,
                image_url=a.get("image_url"),
                published_at=_parse_date(a.get("pubDate")),
                source_weight=65,
            ))
        log.info("newsdata: %s -> %d stories", category, len(out))
        return out


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        # NewsData pubDate is "YYYY-MM-DD HH:MM:SS" in UTC
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=timezone.utc)
    except ValueError:
        return None
