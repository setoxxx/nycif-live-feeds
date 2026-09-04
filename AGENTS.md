# AGENTS.md - NYCIF Live Feeds Coding-Agent Rules

This repository powers NYC In Focus live-event feed generation and GPS review workflows.

These instructions apply to Cursor, GitHub Copilot, Claude Code, Codex, ChatGPT, and any other coding agent or automated assistant working in this repository.

## Related repositories

Primary backend/feed repo:

- `setoxxx/nycif-live-feeds`

Frontend/map repo:

- `setoxxx/nycif-field-desk`

GitHub Pages admin experiments are retired. Do not deploy or restore:

- `https://setoxxx.github.io/nycif-field-desk/admin/`
- `https://setoxxx.github.io/nycif-field-desk/admin/calendar.html`
- `https://setoxxx.github.io/nycif-field-desk/admin/platform-roadmap.html`

Those pages were versioned prototypes. The product client is the iOS/Android app via Supabase (`event_reader_rolling_v1` / `nycif-native-map-feed`). That is the only place official event data goes. WordPress is not a live map destination; at app launch the site becomes QR codes to the app. Do not treat God View, admin calendar, platform-roadmap, or WordPress `/map/` as live event systems.

The backend repo is the source of truth for generated event feeds, GPS staging artifacts, manual approval queues, GPS review findings, and GPS promotion controls.

The frontend repo is not a live event-data surface. Do not publish official events into the WordPress iframe or field-desk admin pages. Do not add admin/God View pages.

A frontend change must not treat backend GPS review artifacts as public-ready data unless the backend promotion pipeline has explicitly published them into the approved public feed.

## Prime directive

Do not publish bad data.

This project is allowed to generate staging artifacts, reports, review queues, and validation outputs. It must not silently promote unreviewed GPS data. Official catch-up writes to the native app feed are the product path. Do not send live event data to WordPress.

## Protected files

Treat the following files as protected. Do not modify them unless the human explicitly asks for that exact file and exact operation.

- `data/location_cache.json`
- `data/nycif_staged_live_events.json`
- `data/staged_live_manifest.json`
- `data/previous_staged_live_events_snapshot.json`
- GitHub Actions secrets or deployment settings

If a task can be completed by writing a staging/report file instead of editing a protected file, use the staging/report file.

## Product destination (native app only)

Official events go only to the native app through Supabase catch-up (`event_occurrences` → `nycif-native-map-feed`). Do not publish live event pins to WordPress. At launch, WordPress becomes QR codes to the app, not a map.

## Public-map / location-cache rule

Never write `location_cache.json` or treat WordPress as a live map unless the human explicitly says to.

The following are not permission to publish to WordPress or `location_cache.json`:

- "review"
- "inspect"
- "stage"
- "prepare"
- "generate proposals"
- "create approval queue"
- "create review sheet"
- "ready for promotion"

Publishing or promotion requires explicit language such as:

- "promote these approved rows"
- "update location_cache.json with these approved rows"
- "publish this to WordPress" (not a live data destination)

## Official TVPP pins (native app)

Public `tvpp-9vvx` street permits must be certified pins on the official Supabase event feed every time. Resolve them from Parks facility coordinates, NYC DCP LION centerline midpoints, Geoclient blockface midpoints, or NYC Planning Labs GeoSearch. Do not use Google. This is not Phase 2E: do not edit `location_cache.json`. Do not publish to WordPress. Projected feast stays list-only.

## GPS pipeline phases

### Phase 1 - Backend reliability

Goal: account for every current/future incoming raw NYC Open Data row.

Each row must be classified as one of:

1. staged with valid GPS
2. matched to known GPS memory
3. sent to GPS review queue
4. rejected with clear reason

Important artifacts:

- `data/row_disposition_report.json`
- `data/row_disposition_events.json`
- `data/backend_reliability_gate_report.json`

Phase 1 success means no silent drops.

### Phase 2A - Controlled GPS review grouping

Goal: group unresolved GPS rows into readable human-review groups.

Allowed outputs:

- `data/gps_review_group_report.json`
- `data/gps_review_location_groups.json`
- `data/gps_review_geocoding_queue.json`

Do not geocode, approve, promote, or publish in this phase.

### Phase 2B - Controlled geocoding proposals

Goal: create a proposal queue for unresolved GPS groups.

Allowed outputs:

- `data/gps_review_geocoding_proposals.json`
- `data/gps_review_geocoding_proposal_report.json`

Rules:

- proposed coordinates may be null
- `manual_review_status` must remain `pending`
- `promotion_allowed` must remain `false`
- public map must remain unchanged

### Phase 2C - Controlled geocoder fill

Goal: fill proposed coordinates into a separate staging artifact.

Allowed outputs:

- `data/gps_review_geocoding_filled_proposals.json`
- `data/gps_review_geocoding_fill_report.json`

Preferred fill order:

1. `data/manual_gps_reference.json`, if present
2. `data/nyc_parks_facility_reference.json`, if present
3. conservative existing NYCIF location-cache broad place-name memory
4. leave row unfilled

Rules:

- never edit `data/location_cache.json`
- never edit `data/nycif_staged_live_events.json`
- never set `promotion_allowed` to `true`
- never publish to the public map

### Phase 2D - Manual approval gate

Goal: create human-review artifacts and validation outputs.

Allowed outputs:

- `data/gps_manual_approval_queue.json`
- `data/gps_manual_approval_queue_report.json`
- `data/gps_manual_approval_validation_report.json`
- `data/gps_manual_approval_review_sheet.json`
- `data/gps_manual_approval_review_sheet.csv`
- `data/gps_manual_approval_review_sheet_report.json`
- `data/gps_manual_approval_review_findings.json`

Rules:

- approval queue rows may remain pending
- review sheets are not approval sources of truth
- findings artifacts are notes/evidence only
- do not set `manual_review_status` to `approved` unless explicitly instructed
- do not set `promotion_allowed` to `true` unless explicitly instructed
- do not promote to `location_cache.json`

### Phase 2E - Promotion

Phase 2E has not been authorized by default.

A promotion script may only be created or run if the human explicitly asks for Phase 2E promotion.

A row may be promoted only if all of the following are true:

- valid NYC coordinates
- documented source
- confidence reason present
- `manual_review_status` is `approved`
- `manual_reviewer` is present
- `manual_reviewed_at_utc` is present
- `approval_decision_reason` is present
- `promotion_allowed` is `true`
- validation report passes

Promotion must write a report showing exactly what changed.

## Cross-repo coordination

When backend changes affect frontend/map behavior:

1. Confirm the backend artifact is intended for public or frontend consumption.
2. Review `setoxxx/nycif-field-desk/AGENTS.md` before asking a frontend agent to change the map.
3. Never ask the frontend to load GPS review/proposal/approval artifacts as live public event data.
4. Keep native-app feed behavior separate from admin/test/review behavior.
5. Do not publish official events to WordPress. The live client is the app.
6. Do not edit WordPress `nycinfocus.com/map/` as an event map. At launch it becomes QR codes to the app.

When frontend changes depend on backend data:

1. Confirm the backend artifact exists.
2. Confirm the artifact is public-ready, not just staged/review-only.
3. Cite or inspect the backend QA report before making native-app map claims.

## QA requirements

Before claiming success, inspect the generated artifacts.

Do not say a workflow passed unless the relevant report file says it passed or the artifacts prove it.

Important QA artifacts:

- `data/backend_reliability_gate_report.json`
- `data/row_disposition_report.json`
- `data/gps_repository_report.json`
- `data/gps_review_group_report.json`
- `data/gps_review_geocoding_proposal_report.json`
- `data/gps_review_geocoding_fill_report.json`
- `data/gps_manual_approval_queue_report.json`
- `data/gps_manual_approval_validation_report.json`
- `data/gps_manual_approval_review_sheet_report.json`

If a workflow fails during push/commit, distinguish between data failure and Git/GitHub failure.

## Coding-agent workflow

Preferred workflow for Cursor/Copilot/Claude Code/Codex:

1. Work in a branch or local checkout when possible.
2. Make the smallest safe change.
3. Prefer scripts and staging outputs over direct data mutation.
4. Run or rely on GitHub Actions QA.
5. Inspect report artifacts.
6. Summarize exactly what changed and what did not change.

Do not make broad rewrites to unrelated scripts.

Do not rename existing artifacts without updating every dependent workflow step and report.

Do not remove safety fields such as:

- `manual_review_status`
- `promotion_allowed`
- `public_map_modified`
- `location_cache_modified`
- `staged_feed_modified`
- `confidence_reason`
- `approval_decision_reason`

## Required safety fields in GPS review artifacts

GPS proposal/review artifacts should preserve these fields wherever applicable:

- `group_key`
- `display_location`
- `borough`
- `event_count`
- `proposed_lat`
- `proposed_lng`
- `geocoder_source`
- `geocoder_confidence`
- `confidence_reason`
- `manual_review_status`
- `manual_review_notes`
- `manual_reviewer`
- `manual_reviewed_at_utc`
- `approval_decision_reason`
- `promotion_allowed`
- `public_map_modified`
- `location_cache_modified`
- `staged_feed_modified`

## External geocoding and source use

If adding or using external geocoding:

- prefer official NYC/Parks references where available
- record the source in each row
- record confidence and confidence reason
- do not write directly to `location_cache.json`
- do not auto-promote coordinates from Google, Foursquare, or any geocoder
- write a staging artifact first

## Commit and final-response rules

When committing changes, use clear commit messages.

Examples:

- `Add GPS manual review sheet generator`
- `Wire GPS manual review sheet into QA workflow`
- `Add Phase 2D reviewed GPS findings artifact`
- `Coordinate backend and frontend agent rules`

Final responses should include:

- files changed
- safety confirmation
- what must be run next
- what remains unapproved/unpromoted

Never claim native-app map changes unless catch-up wrote them and the feed was verified. Never claim WordPress map changes; WordPress is not a live event destination.

## Cursor Cloud specific instructions

Environment context for future cloud agents (the update script has already installed dependencies before your session starts):

- This repo is a **pure Python batch pipeline** — there is no web server, HTTP API, or long-running service. "Running" means executing `python3 scripts/<name>.py`. Use `python3`, not `python` (there is no `python` alias on the VM).
- **Dependencies:** install from `requirements.txt` (`rapidfuzz==3.*`, `pytest==9.0.2`). `rapidfuzz` is used by GPS staged-feed match diagnostics; `pytest` runs the test suite. Everything else is Python standard library. Cloud/update scripts may pre-install these.
- **Tests:** run `python3 -m pytest` from the repo root (the root must be on `sys.path` so `tools.registry.*` imports resolve). Registry tests under `tests/registry/` are deterministic and offline/fixture-based; full suite size is 400+ and grows with milestones.
- **Lint:** there is no configured linter (no ruff/flake8/pylint config). Use `python3 -m compileall scripts tools tests` as a syntax check.
- **Full pipeline order** is defined in `.github/workflows/live-sync-qa.yml`; run scripts in that order to reproduce CI locally.
- **Offline by default:** the committed JSON snapshots under `data/` (e.g. `data/raw_nyc_open_data_snapshot.json`) are the pipeline's datastore, so the pipeline runs end-to-end offline. Only `sync_nyc_open_data.py` and `build_test_enriched_feed.py` hit the network (NYC Open Data), and `send_live_delta_email.py` needs SMTP secrets — all optional/gated.
- **Gotcha — running scripts rewrites tracked artifacts:** many build scripts overwrite JSON under `data/`, and `build_gps_repository.py` re-serializes the protected `data/location_cache.json`. If you ran scripts only to verify the environment (not to intentionally change data), restore with `git checkout -- data/` so you do not commit unintended (or protected) data changes.
