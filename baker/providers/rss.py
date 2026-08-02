"""RSS provider: publications' own feeds, configured in config.yaml."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

import feedparser

from ..models import NormalizedStory
from ..sanitize import clean_text

log = logging.getLogger(__name__)

_USER_AGENT = "SheafBaker/1.0 (personal morning-edition builder)"


class RSSProvider:
    name = "rss"

    def __init__(self, feeds: list[dict]):
        """feeds: [{url, section, category, source, source_weight?}, ...]"""
        self.feeds = feeds

    def fetch(self) -> list[NormalizedStory]:
        stories: list[NormalizedStory] = []
        for feed in self.feeds:
            try:
                stories.extend(self._fetch_feed(feed))
            except Exception:
                log.exception("rss: %s failed", feed.get("url"))
        return stories

    def _fetch_feed(self, feed: dict) -> list[NormalizedStory]:
        parsed = feedparser.parse(feed["url"], agent=_USER_AGENT)
        if parsed.bozo and not parsed.entries:
            log.warning("rss: %s unparseable (%s)", feed["url"],
                        parsed.get("bozo_exception"))
            return []

        out: list[NormalizedStory] = []
        for entry in parsed.entries[: feed.get("limit", 10)]:
            link = entry.get("link", "")
            title = entry.get("title", "")
            if not link or not title:
                continue
            out.append(NormalizedStory(
                headline=title,
                deck=clean_text(entry.get("summary", "")),
                article_url=link,
                section=feed["section"],
                category=feed["category"],
                source_name=feed["source"],
                provider=self.name,
                image_url=_entry_image(entry),
                published_at=_entry_date(entry),
                source_weight=feed.get("source_weight", 40),
            ))
        log.info("rss: %s -> %d stories", feed["source"] + "/" + feed["category"],
                 len(out))
        return out


def _entry_image(entry) -> str | None:
    for media in entry.get("media_content", []) or []:
        if media.get("url"):
            return media["url"]
    for thumb in entry.get("media_thumbnail", []) or []:
        if thumb.get("url"):
            return thumb["url"]
    for enc in entry.get("enclosures", []) or []:
        if enc.get("type", "").startswith("image") and enc.get("href"):
            return enc["href"]
    return None


def _entry_date(entry) -> datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        parsed = entry.get(key)
        if parsed:
            return datetime.fromtimestamp(time.mktime(parsed), tz=timezone.utc)
    return None
