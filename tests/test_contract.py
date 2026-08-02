"""Contract tests: the baker's output must satisfy the edition schema
that the Swift app (and later the Flutter app) decodes."""

import json
from datetime import datetime, timezone
from pathlib import Path

import jsonschema
import pytest

from baker.editor import build_edition, dedupe
from baker.models import NormalizedStory, swift_date
from baker.sanitize import sanitize

SCHEMA = json.loads(
    (Path(__file__).parent.parent / "schema" / "edition.schema.json").read_text())


def _story(headline, section="frontPage", **kw):
    defaults = dict(
        deck="A deck long enough to look like a real summary of the story.",
        article_url="https://example.com/" + headline.replace(" ", "-").lower(),
        category="HEADLINES",
        source_name="The Hindu",
        provider="rss",
        published_at=datetime.now(timezone.utc),
    )
    defaults.update(kw)
    return NormalizedStory(headline=headline, section=section, **defaults)


def _sample_stories():
    return [
        _story("Cabinet clears new energy policy after marathon session"),
        _story("Monsoon session begins with stormy exchanges in both houses"),
        _story("Bengaluru metro phase three gets environmental clearance",
               section="city", category="CITY",
               image_url="https://example.com/metro.jpg"),
        _story("Rupee steadies as markets await inflation print",
               section="business", category="BUSINESS"),
        _story("India name squad for home test series",
               section="sport", category="SPORTS"),
        _story("National capital records coldest morning of the season",
               section="nation", category="NATIONAL"),
    ]


def test_edition_matches_schema():
    edition = build_edition(sanitize(_sample_stories()), city="Bengaluru")
    jsonschema.validate(edition, SCHEMA)


def test_dates_are_swift_reference_encoded():
    unix_2026 = datetime(2026, 8, 1, tzinfo=timezone.utc)
    encoded = swift_date(unix_2026)
    # 2026-08-01 is ~25.6 years after 2001-01-01
    assert 25 * 365 * 86400 < encoded < 26 * 365 * 86400


def test_nation_merges_into_front_page():
    edition = build_edition(sanitize(_sample_stories()), city="Bengaluru")
    titles = [s["title"] for s in edition["sections"]]
    assert titles == ["Front Page", "City", "Business", "Sport"]
    front = edition["sections"][0]
    headlines = [s["headline"] for s in front["stories"] + front["briefs"]]
    assert any("coldest morning" in h for h in headlines)


def test_layout_slots():
    edition = build_edition(sanitize(_sample_stories()), city="Bengaluru")
    front = edition["sections"][0]
    block_types = [s["blockType"] for s in front["stories"]]
    assert block_types[0] == "hero"
    assert all(b in ("hero", "feature", "standard") for b in block_types)
    assert all(s["blockType"] == "brief" for s in front["briefs"])


def test_cross_provider_dedupe_keeps_best():
    a = _story("Cabinet clears new energy policy after marathon session")
    b = _story("Cabinet clears new energy policy after marathon session ends",
               provider="newsmesh", source_name="NewsMesh",
               image_url="https://example.com/best.jpg", source_weight=60)
    survivors = dedupe([a, b])
    assert len(survivors) == 1
    assert survivors[0].image_url == "https://example.com/best.jpg"


def test_visual_discriminator():
    edition = build_edition(sanitize(_sample_stories()), city="Bengaluru")
    city = edition["sections"][1]
    hero = city["stories"][0]
    assert hero["visual"]["type"] == "remoteImage"
    assert hero["visual"]["url"].startswith("https://")


def test_sanitizer_drops_junk():
    junk = [
        _story("LIVE: parliament session updates today"),
        _story("Too short"),
        _story("WATCH: something happened somewhere in a video"),
    ]
    assert sanitize(junk) == []
