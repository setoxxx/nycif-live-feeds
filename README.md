# NYCIF Live Feeds

Public JSON feed files for NYC In Focus map pages.

This repository contains public event-feed data only.

> **Code name: Enigma** — the normalization/processing system. Its GPS converter
> (`scripts/geocode_unfilled_gps_proposals.py`) resolves unmapped NYC locations
> to latitude/longitude via NYC Planning **GeoSearch**, writing a staging file
> for manual review (never auto-promoted). It pairs with **Borg**
> (`nycif-data-pipeline`, data aggregation), whose Culture geocoding lane bridges
> to Enigma. Code names are branding only and rename nothing; canonical glossary:
> [`nycif-data-pipeline/docs/CODENAMES.md`](https://github.com/setoxxx/nycif-data-pipeline/blob/main/docs/CODENAMES.md).

## Setup

Supported Python version: 3.11 (matches every workflow's `actions/setup-python` declaration; no other version is tested).

Install dependencies:

```
python3 -m pip install -r requirements.txt
```

`requirements.txt` contains exactly:

```
rapidfuzz==3.*
pytest==9.0.2
```

Run the test suite:

```
python3 -m pytest
```

## Workflows

- `.github/workflows/live-sync-qa.yml` is `workflow_dispatch`-only. The live job runs only when `allow_live_fetch` is explicitly set to `yes` (default `no`). The email-notification step additionally requires `allow_email == 'yes'` **and** is skipped whenever the backend reliability gate has failed (`env.BACKEND_GATE_FAILED != 'true'`).
- The three GPS staged-feed commit workflows (`gps-staged-feed-integration-adjudication-summary.yml`, `gps-staged-feed-integration-diagnostic.yml`, `gps-staged-feed-integration-update.yml`) commit their generated artifact only `if: success()` — a failed or cancelled generation step will not be committed.
- Live-source access, SMTP/email, publishing, production, WordPress, and public-map operations all require separate explicit authorization; none of the above workflow behavior enables them automatically.

## Protected data

`data/location_cache.json` and the other files under `data/` are pipeline-generated artifacts. Do not regenerate or overwrite them casually — see `AGENTS.md` for the full protected-file and GPS-pipeline-phase rules.
