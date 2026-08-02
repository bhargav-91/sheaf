"""Canonical data shapes and Swift-Codable-compatible serialization.

The output contract is the Swift `Edition` struct in the Prabhaat app
(Models/NewsModels.swift). The app decodes with a plain JSONDecoder(),
so Dates must be encoded as seconds since 2001-01-01T00:00:00Z
(Swift's reference date), NOT unix time or ISO 8601.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

SWIFT_REFERENCE_EPOCH = 978_307_200  # unix timestamp of 2001-01-01T00:00:00Z

SECTIONS = ("frontPage", "city", "nation", "business", "sport")


def swift_date(dt: datetime) -> float:
    """Encode a datetime the way Swift's default Codable Date expects."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp() - SWIFT_REFERENCE_EPOCH


@dataclass
class NormalizedStory:
    """The provider-agnostic shape every adapter must emit.

    Adapters own their provider's quirks; everything downstream
    (sanitizer, editor) sees only this.
    """

    headline: str
    deck: str
    article_url: str
    section: str                       # one of SECTIONS
    category: str                      # display label, e.g. "HEADLINES"
    source_name: str                   # e.g. "The Hindu"
    provider: str                      # adapter id, e.g. "rss", "newsmesh"
    image_url: Optional[str] = None
    published_at: Optional[datetime] = None
    body_text: str = ""
    source_weight: int = 50            # lower = more authoritative

    def __post_init__(self) -> None:
        if self.section not in SECTIONS:
            raise ValueError(f"unknown section {self.section!r}")


def story_to_swift(story: NormalizedStory, block_type: str) -> dict:
    """Serialize one story as the Swift `Story` struct."""
    if story.image_url:
        visual = {"type": "remoteImage", "url": story.image_url}
    else:
        visual = {"type": "none"}

    payload = {
        "id": str(uuid.uuid4()),
        "category": story.category,
        "headline": story.headline,
        "deck": story.deck,
        "byline": story.source_name,
        "visual": visual,
        "blockType": block_type,
        "bodyText": story.body_text or story.deck,
        "articleURL": story.article_url,
    }
    if story.published_at is not None:
        payload["pubDate"] = swift_date(story.published_at)
    return payload


def section_to_swift(title: str, stories: list[dict], briefs: list[dict]) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "title": title,
        "stories": stories,
        "briefs": briefs,
        "promotions": [],
    }


def edition_to_swift(city: str, sections: list[dict],
                     date: Optional[datetime] = None) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "publication": "Morning Edition",
        "city": city,
        "date": swift_date(date or datetime.now(timezone.utc)),
        "sections": sections,
    }
