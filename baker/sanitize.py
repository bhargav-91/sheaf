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
    re.compile(r"^in photos[:\s]", re.IGNORECASE),
    re.compile(r"horoscope|rashifal|numerology|tarot", re.IGNORECASE),
    re.compile(r"wordle|quiz|crossword", re.IGNORECASE),
    # trivia and chum that reads as filler on a front page
    re.compile(r"box office (collection|day \d+)", re.IGNORECASE),
    re.compile(r"\b\d+ (things|reasons|ways|foods|habits|tips)\b", re.IGNORECASE),
    re.compile(r"^(shocking|viral|watch the moment)\b", re.IGNORECASE),
    re.compile(r"zodiac|astrolog", re.IGNORECASE),
    re.compile(r"(recap|spoilers|episode \d+)", re.IGNORECASE),
    re.compile(r"^\s*(photos|videos)\s*[:|]", re.IGNORECASE),
)

MAX_DECK_CHARS = 400
MIN_HEADLINE_CHARS = 12
MAX_STORY_AGE = timedelta(hours=36)

# Syndicated press releases and aggregator chum. These arrive from the
# API providers dressed as news; they are never worth a slot.
_PR_PATTERNS = (
    re.compile(r"^(business|technology|sports|entertainment) news \|", re.IGNORECASE),
    re.compile(r"exhibitor list|press release|prnewswire|businesswire", re.IGNORECASE),
    re.compile(r"\b(webinar|whitepaper|book your (seat|slot))\b", re.IGNORECASE),
)

# The city section must actually be about this city's region.
_CITY_TERMS = re.compile(
    r"bengaluru|bangalore|karnataka|mysuru|mysore|hubballi|mangaluru|"
    r"belagavi|kalaburagi|tumakuru|udupi|shivamogga|bbmp|bmtc|bmrcl|kempegowda",
    re.IGNORECASE)

# Soft-news topics that don't belong on a front page. They stay in the
# paper only if their own section asked for them (e.g. Sport).
_SOFT_FRONT_PAGE = re.compile(
    r"tie the knot|engagement rumou?rs|dating|red carpet|fashion week|"
    r"box office|celebrity|\bwedding\b|birthday bash|net worth",
    re.IGNORECASE)


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
        if any(p.search(s.headline) for p in _PR_PATTERNS):
            continue
        # The city section is fed by keyword queries ("Bengaluru OR
        # Karnataka"); anything matching neither term is a false positive,
        # not local news. Drop it rather than promote it — the front page
        # has its own feeds and doesn't need another paper's local story.
        if s.section == "city" and not _CITY_TERMS.search(
                f"{s.headline} {s.deck}"):
            continue
        # Soft news is fine in its own section, never on the front.
        if s.section in ("frontPage", "nation") and _SOFT_FRONT_PAGE.search(
                s.headline):
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
