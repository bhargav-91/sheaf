"""Full-article text extraction.

Runs over every candidate story (not just main slots) and in parallel,
because body text is what makes the paper readable — a story without it
cannot hold a main slot (see editor.QUALITY GATE).
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

import trafilatura

from .models import NormalizedStory

log = logging.getLogger(__name__)

MIN_BODY_CHARS = 400   # below this it's a paywall stub or a teaser
WORKERS = 8


def _extract_one(story: NormalizedStory) -> bool:
    """Try a precise extraction first; fall back to a greedy one.

    Some publishers (Deccan Herald notably) wrap body copy in markup that
    the precision pass discards, yielding a 150-char stub from a real
    article. Without the retry, those mastheads silently fail the editor's
    quality gate and vanish from main slots.
    """
    try:
        downloaded = trafilatura.fetch_url(story.article_url)
        if not downloaded:
            return False
        for kwargs in ({"favor_precision": True}, {"favor_recall": True}):
            text = trafilatura.extract(
                downloaded,
                include_comments=False,
                include_tables=False,
                **kwargs,
            )
            if text and len(text) >= MIN_BODY_CHARS:
                story.body_text = text.strip()
                return True
    except Exception as exc:
        log.debug("extract failed for %s: %s", story.article_url, exc)
    return False


def enrich_bodies(stories: list[NormalizedStory]) -> int:
    """Fetch and attach body text in parallel. Returns success count."""
    if not stories:
        return 0
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        results = list(pool.map(_extract_one, stories))
    ok = sum(results)
    log.info("extract: %d/%d stories got full body text", ok, len(stories))
    return ok
