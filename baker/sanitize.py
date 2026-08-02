"""One shared sanitation pass over NormalizedStory items.

Providers map shapes; this module enforces content quality so no rule
lives in two places.
"""

from __future__ import annotations

import html
import re
from datetime import datetime, timedelta, timezone

from .models import NormalizedStory

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")

_JUNK_HEADLINE_PATTERNS = (
    re.compile(r"^LIVE[:\s]", re.IGNORECASE),
    re.compile(r"live updates", re.IGNORECASE),
    re.compile(r"^watch[:\s]", re.IGNORECASE),
    re.compile(r"^in pics[:\s]", re.IGNORECASE),
    re.compile(r"horoscope", re.IGNORECASE),
    re.compile(r"wordle", re.IGNORECASE),
)

MAX_DECK_CHARS = 400
MIN_HEADLINE_CHARS = 12
MAX_STORY_AGE = timedelta(hours=36)


def clean_text(raw: str) -> str:
    """Strip tags, unescape entities, collapse whitespace."""
    text = html.unescape(raw or "")
    text = _TAG_RE.sub(" ", text)
    text = _WS_RE.sub(" ", text).strip()
    return text


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return cut.rstrip(",;:") + "…"


def sanitize(stories: list[NormalizedStory]) -> list[NormalizedStory]:
    now = datetime.now(timezone.utc)
    kept: list[NormalizedStory] = []
    for s in stories:
        s.headline = clean_text(s.headline)
        s.deck = _truncate(clean_text(s.deck), MAX_DECK_CHARS)
        s.body_text = s.body_text.strip()

        if len(s.headline) < MIN_HEADLINE_CHARS:
            continue
        if not s.article_url.startswith("http"):
            continue
        if any(p.search(s.headline) for p in _JUNK_HEADLINE_PATTERNS):
            continue
        if s.image_url and not s.image_url.startswith("http"):
            s.image_url = None
        if s.published_at is not None:
            if s.published_at.tzinfo is None:
                s.published_at = s.published_at.replace(tzinfo=timezone.utc)
            if s.published_at > now + timedelta(hours=1):   # clock-skew junk
                s.published_at = None
            elif now - s.published_at > MAX_STORY_AGE:      # stale
                continue
        kept.append(s)
    return kept
