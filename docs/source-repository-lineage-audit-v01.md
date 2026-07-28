# Source repository lineage audit v01

Status: proposed audit scope

This document defines the next protected audit lane for the NYC In Focus City Engine / Enigma processing repository.

## Purpose

Prove that every repository, source snapshot, generated feed, review layer, cache, and public-facing output involved in event processing is inventoried and classified before any production-feed promotion or public map launch.

The audit is separate from:

- PR #322, which audits unresolved-borough/location coverage proposals.
- PR #323, which audits strict source-occurrence reconciliation by dataset, source event ID, and event date.
- Issue #324, which tracks the implementation fix for source-ID-only suppression of dated Open Data occurrences.

## Core question

For every event-like data record, can the system explain:

1. where it came from,
2. which repository or source layer owns it,
3. whether it is raw intake, generated output, review-only, historical-only, duplicative, cache/reference, or public output,
4. which dated occurrence key represents it,
5. whether it was accepted, rejected, excluded, merged, hidden, or promoted,
6. whether it is eligible for a map pin, list entry, review-only display, or no public display,
7. whether any downstream feed changed because of it.

## Initial repository set to verify

The audit should inspect and classify at least the following known NYCIF repositories:

- `setoxxx/nycif-live-feeds`
- `setoxxx/nycif-web-platform`
- `setoxxx/nycif-open-data`
- `setoxxx/nycif-data-pipeline`
- `setoxxx/-nycif-data-pipeline`
- `setoxxx/nycif-event-radar`
- `setoxxx/nycif-field-desk`
- `setoxxx/nycif-prompt-engine`
- `setoxxx/nycif-national-pilot`

Additional repositories discovered during audit should be added with an explicit status rather than ignored.

## Required classification vocabulary

Each repository and file/source path should be assigned one primary role:

- raw_intake_source
- raw_snapshot
- processor
- enrichment_or_geocoding
- review_queue
- generated_feed
- page_shard_or_manifest
- public_surface
- staging_surface
- editorial_signal
- prompt_or_generation_support
- reference_cache
- historical_snapshot
- duplicative_copy
- national_expansion_pilot
- unknown_pending_review

## Required outputs

The audit should produce protected artifacts only:

- repository inventory JSON
- source/file lineage JSON
- cross-repo dataflow Markdown report
- unexplained-source exception report
- generated-output double-counting report
- public-surface mutation safety report

## Acceptance criteria

- Every known NYCIF repository receives an explicit role and reason code.
- Every event-like source path used by the current pipeline is tied to a repository and owner role.
- Raw intake is separated from generated feeds, page shards, duplicative copies, caches, and historical snapshots.
- The audit flags any event-like file that is not in the current hardcoded source catalog.
- The audit flags any repository that can affect public output but is missing from the launch gate.
- The audit verifies that no public `/map/`, homepage, navigation, WordPress production page, production feed, or `location_cache.json` changes are made by the audit.
- The audit remains proposal-only until reviewed.

## Launch boundary

This document does not authorize production-feed promotion or public launch. Issue `setoxxx/nycif-web-platform#132` remains open and issue #96 remains blocked until all launch gates pass and Howard gives explicit final approval.
