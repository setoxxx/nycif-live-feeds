# AGENTS.md - NYCIF Live Feeds Coding-Agent Rules

This repository powers NYC In Focus live-event feed generation and GPS review workflows.

These instructions apply to Cursor, GitHub Copilot, Claude Code, Codex, ChatGPT, and any other coding agent or automated assistant working in this repository.

## Prime directive

Do not publish bad data.

This project is allowed to generate staging artifacts, reports, review queues, and validation outputs. It must not silently promote unreviewed GPS data or alter the public map without explicit human approval.

## Protected files

Treat the following files as protected. Do not modify them unless the human explicitly asks for that exact file and exact operation.

- `data/location_cache.json`
- `data/nycif_staged_live_events.json`
- `data/staged_live_manifest.json`
- `data/previous_staged_live_events_snapshot.json`
- public map feed outputs used by NYC In Focus
- WordPress/public-map embed code, if present in any connected workflow
- GitHub Actions secrets or deployment settings

If a task can be completed by writing a staging/report file instead of editing a protected file, use the staging/report file.

## Public-map rule

Never publish to the public map unless the human explicitly says to publish or promote.

The following are not permission to publish:

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
- "publish this to the public map"

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

Final responses should include:

- files changed
- safety confirmation
- what must be run next
- what remains unapproved/unpromoted

Never claim public-map changes unless the public map was intentionally changed and verified.
