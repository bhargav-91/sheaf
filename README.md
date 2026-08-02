# Sheaf — edition baker

Bakes a daily "morning edition" JSON that the Sheaf app (iOS today,
Flutter later) fetches as a single static file. No servers.

```
Providers (adapters)          Editor layer                 Contract
────────────────────    ─────────────────────────    ────────────────────
RSS  (Hindu, IE, DH) ┐   sanitize → dedupe → rank →   editions/latest.json
NewsMesh (optional)  ┘   sections → layout slots      editions/edition-YYYY-MM-DD.json
```

## Design rules

- **Adapters are the only place that know a provider's wire format.**
  Everything downstream sees `NormalizedStory` (baker/models.py).
- **The contract is `schema/edition.schema.json`** — a mirror of the
  Swift `Edition` Codable model. The app and baker never share code;
  the schema plus `tests/test_contract.py` keep them honest.
- **Dates are Swift-reference encoded**: numbers of seconds since
  2001-01-01T00:00:00Z, because the app decodes with a default
  `JSONDecoder()`. Do not "fix" this to ISO 8601 without changing the
  app's decoder at the same time.

## Run locally

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m baker                 # full bake into editions/
.venv/bin/python -m baker --no-extract    # fast bake, decks only
.venv/bin/python -m pytest tests/ -q      # contract tests
```

`NEWSMESH_API_KEY` in the environment enables the NewsMesh adapter;
without it the bake runs on publication RSS feeds alone (which is fine).

## Daily automation

`.github/workflows/bake.yml` runs at 05:30 IST, commits the edition to
this repo, and the app fetches:

```
https://raw.githubusercontent.com/<user>/sheaf/main/editions/latest.json
```

Requirements: this repo must be **public** on GitHub (raw URLs on
private repos need auth). Add `NEWSMESH_API_KEY` as an Actions secret
if you want the NewsMesh adapter in CI.

## Adding a provider

1. New file in `baker/providers/`, implementing `fetch() -> list[NormalizedStory]`.
   Own your provider's quirks (auth, rate limits, category mapping) there.
2. Register it in `baker/__main__.py`.
3. That's all — sanitation, dedupe, ranking, and layout are shared.

## App side (to do in the app repo)

A `RemoteEditionService: ContentService` that GETs `latest.json`,
wrapped in the existing `CachedContentService`. Plus one unit test that
decodes `editions/latest.json` with the app's models — the drift tripwire.
