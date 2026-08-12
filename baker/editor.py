"""The editor layer: dedupe, candidate selection, quality gating, layout.

Three rules do the editorial work:

  QUALITY GATE   a story with no extracted body cannot hold a main slot.
                 An unreadable hero is worse than a smaller paper.
  SOURCE CAP     no single publication may take more than MAX_PER_SOURCE
                 of a section's main slots, so no section is one-source.
  RANK           readable + recent + illustrated + authoritative, in that
                 order of influence.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from .models import (NormalizedStory, edition_to_swift, section_to_swift,
                     story_to_swift)

log = logging.getLogger(__name__)

_WORD_RE = re.compile(r"[a-z0-9]+")

_MAIN_SLOTS = ("hero", "feature", "feature", "standard", "standard")
MAX_PER_SOURCE = 2          # per section, across main slots
MIN_BODY_CHARS = 400        # must match extract.MIN_BODY_CHARS
CANDIDATES_PER_SECTION = 14  # how many we bother extracting

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
    return len(ta & tb) / len(ta | tb) >= 0.55


def _quality(s: NormalizedStory) -> tuple:
    return (len(s.body_text), 1 if s.image_url else 0,
            -s.source_weight, len(s.deck))


def dedupe(stories: list[NormalizedStory]) -> list[NormalizedStory]:
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


def _recency_key(s: NormalizedStory) -> tuple:
    ts = s.published_at.timestamp() if s.published_at else 0.0
    return (-ts, s.source_weight)


def _group_sections(stories: list[NormalizedStory]) -> dict[str, list[NormalizedStory]]:
    by_section: dict[str, list[NormalizedStory]] = {}
    for s in stories:
        key = "frontPage" if s.section == "nation" else s.section
        by_section.setdefault(key, []).append(s)
    return by_section


def select_candidates(stories: list[NormalizedStory]) -> list[NormalizedStory]:
    """Dedupe, then take the top N per section — the set worth extracting."""
    by_section = _group_sections(dedupe(stories))
    out: list[NormalizedStory] = []
    for section_key, _ in _SECTION_TITLES:
        ranked = sorted(by_section.get(section_key, []), key=_recency_key)
        out.extend(ranked[:CANDIDATES_PER_SECTION])
    return out


def _readable(s: NormalizedStory) -> bool:
    return len(s.body_text) >= MIN_BODY_CHARS


def _pick_mains(ranked: list[NormalizedStory],
                bylined: set[str]) -> tuple[list, list]:
    """Fill main slots under the three editorial rules.

    A main slot needs: full body text, a masthead you would actually put
    on a front page, and room left under that source's cap. Everything
    else keeps its ranking order and falls through to briefs.

    Returns (mains, leftovers).
    """
    mains: list[NormalizedStory] = []
    used: list[NormalizedStory] = []
    per_source: dict[str, int] = {}

    for story in ranked:
        if len(mains) == len(_MAIN_SLOTS):
            break
        if not _readable(story):
            continue
        if bylined and story.source_name not in bylined:
            continue
        if per_source.get(story.source_name, 0) >= MAX_PER_SOURCE:
            continue
        mains.append(story)
        used.append(story)
        per_source[story.source_name] = per_source.get(story.source_name, 0) + 1

    leftovers = [s for s in ranked if s not in used]
    return mains, leftovers


def build_edition(stories: list[NormalizedStory], city: str,
                  max_briefs: int = 8,
                  date: datetime | None = None,
                  bylined_sources: set[str] | None = None) -> dict:
    """bylined_sources: mastheads allowed to hold main slots. Empty or
    None disables the rule (every readable story may lead)."""
    by_section = _group_sections(dedupe(stories))
    bylined = bylined_sources or set()

    sections = []
    for section_key, title in _SECTION_TITLES:
        ranked = sorted(by_section.get(section_key, []), key=_recency_key)
        picked, leftovers = _pick_mains(ranked, bylined)

        if len(picked) < len(_MAIN_SLOTS):
            log.warning("%s: only %d/%d main slots met the quality gate",
                        title, len(picked), len(_MAIN_SLOTS))

        mains = [story_to_swift(s, _MAIN_SLOTS[i]) for i, s in enumerate(picked)]
        briefs = [story_to_swift(s, "brief") for s in leftovers[:max_briefs]]
        sources = {s.source_name for s in picked}
        log.info("%s: %d mains from %d sources, %d briefs",
                 title, len(mains), len(sources), len(briefs))
        sections.append(section_to_swift(title, mains, briefs))

    return edition_to_swift(city, sections, date or datetime.now(timezone.utc))
