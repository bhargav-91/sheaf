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


BODY = "Full article text. " * 40   # comfortably over the 400-char gate


def _story(headline, section="frontPage", **kw):
    defaults = dict(
        deck="A deck long enough to look like a real summary of the story.",
        article_url="https://example.com/" + headline.replace(" ", "-").lower(),
        category="HEADLINES",
        source_name="The Hindu",
        provider="rss",
        published_at=datetime.now(timezone.utc),
        body_text=BODY,
    )
    defaults.update(kw)
    return NormalizedStory(headline=headline, section=section, **defaults)


def _sample_stories():
    return [
        _story("Cabinet clears new energy policy after marathon session"),
        _story("Monsoon session begins with stormy exchanges in both houses",
               source_name="Indian Express"),
        _story("Bengaluru metro phase three gets environmental clearance",
               section="city", category="CITY",
               image_url="https://example.com/metro.jpg"),
        _story("Rupee steadies as markets await inflation print",
               section="business", category="BUSINESS"),
        _story("India name squad for home test series",
               section="sport", category="SPORTS"),
        _story("National capital records coldest morning of the season",
               section="nation", category="NATIONAL",
               source_name="Deccan Herald"),
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
        _story("Business News | HIMTEX 2026 Exhibitor List announced"),
        _story("Jana Nayagan box office day 20 collection crosses record"),
        _story("Ronaldo and Georgina tie the knot after long engagement"),
    ]
    assert sanitize(junk) == []


# ── the three editorial rules added after week one ──────────────────

def test_quality_gate_keeps_bodyless_stories_out_of_main_slots():
    """A story with no extracted body may appear as a brief, never a hero."""
    bodyless = [
        "Parliament debates the new spectrum allocation framework",
        "Coastal highway project clears its final environmental hurdle",
        "Rainfall deficit widens across three northern districts",
        "Import duty revision announced for speciality steel grades",
        "Election commission publishes revised polling schedule",
    ]
    stories = [_story("Readable lead story about the union budget session")]
    stories += [_story(h, body_text="") for h in bodyless]

    edition = build_edition(sanitize(stories), city="Bengaluru")
    front = edition["sections"][0]
    assert len(front["stories"]) == 1
    assert front["stories"][0]["blockType"] == "hero"
    assert "Readable lead" in front["stories"][0]["headline"]
    assert len(front["briefs"]) == len(bodyless)   # the rest fell through


def test_source_cap_prevents_single_source_section():
    """No publication may hold more than MAX_PER_SOURCE main slots."""
    stories = [_story(f"Times exclusive report number {i} on civic works",
                      source_name="Times of India") for i in range(6)]
    stories += [_story("Hindu report on the same civic works programme today",
                       source_name="The Hindu"),
                _story("Express investigates the civic works tender process",
                       source_name="Indian Express")]
    edition = build_edition(sanitize(stories), city="Bengaluru")
    bylines = [s["byline"] for s in edition["sections"][0]["stories"]]
    assert bylines.count("Times of India") <= 2
    assert len(set(bylines)) >= 2


def test_offtopic_city_story_is_dropped():
    """A 'city' story that never names the region is a keyword false
    positive, not local news — it leaves the paper entirely."""
    indore = _story("Missing Indore techie case takes a new turn today",
                    section="city", category="CITY")
    local = _story("Bengaluru metro phase three gets environmental clearance",
                   section="city", category="CITY")
    cleaned = sanitize([indore, local])
    assert [s.headline[:9] for s in cleaned] == ["Bengaluru"]


def test_unknown_source_can_brief_but_not_lead():
    """Content farms stay in the paper as briefs; they never hold a slot."""
    farm = _story("Content farm rewrite of the day's biggest policy story",
                  source_name="Newsbizkoot.com")
    real = _story("Union budget session opens with a debate on fuel duty",
                  source_name="The Hindu")
    edition = build_edition(sanitize([farm, real]), city="Bengaluru",
                            bylined_sources={"The Hindu", "Indian Express"})
    front = edition["sections"][0]
    assert [s["byline"] for s in front["stories"]] == ["The Hindu"]
    assert [b["byline"] for b in front["briefs"]] == ["Newsbizkoot.com"]
