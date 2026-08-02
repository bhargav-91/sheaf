"""Bake today's edition: providers -> sanitize -> extract -> editor -> JSON.

Usage:
    python -m baker [--config config.yaml] [--out editions/] [--no-extract]
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .editor import build_edition, main_story_urls
from .extract import enrich_bodies
from .providers import NewsDataProvider, NewsMeshProvider, RSSProvider
from .sanitize import sanitize

log = logging.getLogger("baker")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--out", default="editions")
    parser.add_argument("--no-extract", action="store_true",
                        help="skip full-article text extraction")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")

    config = yaml.safe_load(Path(args.config).read_text())

    providers = [RSSProvider(config["rss_feeds"])]
    for env_var, cls in (("NEWSMESH_API_KEY", NewsMeshProvider),
                         ("NEWSDATA_API_KEY", NewsDataProvider)):
        key = os.environ.get(env_var, "").strip()
        if key:
            providers.append(cls(key))
        else:
            log.info("%s not set — skipping %s", env_var, cls.__name__)

    stories = []
    for provider in providers:
        stories.extend(provider.fetch())
    log.info("fetched %d raw stories from %d providers",
             len(stories), len(providers))

    stories = sanitize(stories)
    log.info("%d stories after sanitation", len(stories))

    if not stories:
        log.error("no stories survived — refusing to publish an empty edition")
        return 1

    if not args.no_extract:
        enrich_bodies(stories, main_story_urls(
            stories, config.get("max_briefs_per_section", 8)))

    edition = build_edition(
        stories,
        city=config.get("city", "Bengaluru"),
        max_briefs=config.get("max_briefs_per_section", 8),
    )

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    payload = json.dumps(edition, ensure_ascii=False, indent=1)
    (out_dir / f"edition-{today}.json").write_text(payload)
    (out_dir / "latest.json").write_text(payload)

    total = sum(len(s["stories"]) + len(s["briefs"])
                for s in edition["sections"])
    log.info("published %d stories -> %s/edition-%s.json",
             total, out_dir, today)
    return 0


if __name__ == "__main__":
    sys.exit(main())
