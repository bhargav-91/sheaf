"""Full-article text extraction for stories rendered in main slots.

Uses trafilatura; falls back silently to the deck when a page
resists extraction. Only main-slot stories are fetched to keep the
daily run fast and polite.
"""

from __future__ import annotations

import logging

import trafilatura

from .models import NormalizedStory

log = logging.getLogger(__name__)

MIN_BODY_CHARS = 300  # anything shorter is likely a paywall stub


def enrich_bodies(stories: list[NormalizedStory], urls: set[str]) -> None:
    for story in stories:
        if story.article_url not in urls:
            continue
        try:
            downloaded = trafilatura.fetch_url(story.article_url)
            if not downloaded:
                continue
            text = trafilatura.extract(
                downloaded,
                include_comments=False,
                include_tables=False,
                favor_precision=True,
            )
            if text and len(text) >= MIN_BODY_CHARS:
                story.body_text = text.strip()
                log.info("extract: %d chars from %s",
                         len(text), story.article_url)
        except Exception:
            log.exception("extract: failed for %s", story.article_url)
