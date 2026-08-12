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

from .editor import build_edition, select_candidates
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

    # Extract before building: the editor needs body text to decide which
    # stories are fit for main slots.
    candidates = select_candidates(stories)
    log.info("%d candidates selected for extraction", len(candidates))
    if not args.no_extract:
        enrich_bodies(candidates)

    edition = build_edition(
        candidates,
        city=config.get("city", "Bengaluru"),
        max_briefs=config.get("max_briefs_per_section", 8),
        bylined_sources=set(config.get("bylined_sources", [])),
    )

    readable = sum(1 for s in edition["sections"]
                   for st in s["stories"] + s["briefs"]
                   if len(st["bodyText"]) >= 400)
    total = sum(len(s["stories"]) + len(s["briefs"]) for s in edition["sections"])
    pct = (100 * readable // total) if total else 0
    log.info("readability: %d/%d stories (%d%%) have full body text",
             readable, total, pct)

    min_readable = config.get("min_readable_percent", 0)
    if not args.no_extract and pct < min_readable:
        log.error("readability %d%% is below the %d%% floor — not publishing; "
                  "yesterday's edition stays up", pct, min_readable)
        return 1

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
