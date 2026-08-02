"""The editor layer: cross-provider dedupe, ranking, layout assignment.

Port of the Prabhaat app's EditionBuilder, plus what it couldn't do
on-device: merging the same wire story arriving from several providers.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from .models import (NormalizedStory, edition_to_swift, section_to_swift,
                     story_to_swift)

_WORD_RE = re.compile(r"[a-z0-9]+")

# index -> blockType, mirroring EditionBuilder.blockType(for:)
_MAIN_SLOTS = ("hero", "feature", "feature", "standard", "standard")

_SECTION_TITLES = (
    ("frontPage", "Front Page"),
    ("city", "City"),
    ("business", "Business"),
    ("sport", "Sport"),
)


def _tokens(headline: str) -> set[str]:
    return set(_WORD_RE.findall(headline.lower()))


def _is_duplicate(a: NormalizedStory, b: NormalizedStory) -> bool:
    if a.headline.lower()[:40] == b.headline.lower()[:40]:
        return True
    ta, tb = _tokens(a.headline), _tokens(b.headline)
    if not ta or not tb:
        return False
    jaccard = len(ta & tb) / len(ta | tb)
    return jaccard >= 0.55


def _quality(s: NormalizedStory) -> tuple:
    """Higher is better. Used to pick the survivor among duplicates."""
    return (
        len(s.body_text),
        1 if s.image_url else 0,
        -s.source_weight,
        len(s.deck),
    )


def dedupe(stories: list[NormalizedStory]) -> list[NormalizedStory]:
    """Cross-provider dedupe; keeps the best version of each story."""
    survivors: list[NormalizedStory] = []
    for story in stories:
        for i, kept in enumerate(survivors):
            if _is_duplicate(story, kept):
                if _quality(story) > _quality(kept):
                    survivors[i] = story
                break
        else:
            survivors.append(story)
    return survivors


def _rank_key(s: NormalizedStory) -> tuple:
    ts = s.published_at.timestamp() if s.published_at else 0.0
    has_image = 1 if s.image_url else 0
    return (-ts, -has_image, s.source_weight)


def build_edition(stories: list[NormalizedStory], city: str,
                  max_briefs: int = 8,
                  date: datetime | None = None) -> dict:
    deduped = dedupe(stories)

    by_section: dict[str, list[NormalizedStory]] = {}
    for s in deduped:
        # nation merges into the front page, as in the app
        key = "frontPage" if s.section == "nation" else s.section
        by_section.setdefault(key, []).append(s)

    sections = []
    for section_key, title in _SECTION_TITLES:
        ranked = sorted(by_section.get(section_key, []), key=_rank_key)
        ranked = ranked[: len(_MAIN_SLOTS) + max_briefs]

        mains, briefs = [], []
        for i, s in enumerate(ranked):
            if i < len(_MAIN_SLOTS):
                mains.append(story_to_swift(s, _MAIN_SLOTS[i]))
            else:
                briefs.append(story_to_swift(s, "brief"))
        sections.append(section_to_swift(title, mains, briefs))

    return edition_to_swift(city, sections, date or datetime.now(timezone.utc))


def main_story_urls(stories: list[NormalizedStory],
                    max_briefs: int = 8) -> set[str]:
    """URLs of stories that will land in main (non-brief) slots.

    Lets the pipeline run full-text extraction only where the body
    is actually rendered, before the edition is built.
    """
    deduped = dedupe(stories)
    by_section: dict[str, list[NormalizedStory]] = {}
    for s in deduped:
        key = "frontPage" if s.section == "nation" else s.section
        by_section.setdefault(key, []).append(s)

    urls: set[str] = set()
    for section_key, _ in _SECTION_TITLES:
        ranked = sorted(by_section.get(section_key, []), key=_rank_key)
        urls.update(s.article_url for s in ranked[: len(_MAIN_SLOTS)])
    return urls
