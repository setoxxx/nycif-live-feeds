# NYCIF Live Data Refresh Master Prompt v01

## Purpose

Use this standing prompt for every fresh NYC In Focus event-data pull, normalization run, discovery-taxonomy projection, feed refresh, God View update, and related map-plugin release.

The goal is to accept new source data without losing the existing taxonomy, approved records, operator review history, rollback path, or evidence of what was replaced.

## Standing instruction

You are updating the NYC In Focus event-data system.

Treat the current committed production-ready data and the discovery-taxonomy-v02 contract as the baseline. A fresh pull is an intake candidate, not permission to replace public data.

For every run:

1. Read `AGENTS.md` and the discovery contract before changing generated data.
2. Inventory every incoming source and record its source identity, pull time, row count, and content hash.
3. Load the current canonical baseline before classifying new rows.
4. Match incoming records against existing canonical IDs, source IDs, dates, titles, locations, groups, and recurring-event rules.
5. Apply the existing discovery taxonomy instead of inventing new category slugs.
6. Preserve confirmed manual overrides, recurring-event rules, grouping decisions, and approved classifications unless a documented current source proves they changed.
7. Route every incoming row to exactly one disposition:
   - accepted standalone public event;
   - grouped supporting record;
   - list-only record;
   - maintenance or closure;
   - private or reserved activity;
   - review queue;
   - rejected with a documented reason.
8. Never silently drop a row.
9. Before replacing any generated or public-consumed artifact, create a timestamped backup snapshot and manifest containing:
   - run ID;
   - prior commit SHA;
   - prior file path;
   - prior SHA-256;
   - backup file path;
   - replacement candidate SHA-256;
   - row counts before and after;
   - added, changed, removed, and unchanged counts;
   - rollback instructions.
10. Write replacement candidates to a staging directory first. Do not overwrite the baseline until validation passes.
11. Reconcile the candidate dataset against the intake inventory and the prior baseline.
12. Fail closed when:
   - the backup is missing or hash verification fails;
   - taxonomy/schema validation fails;
   - canonical IDs unexpectedly collapse or multiply;
   - accepted rows do not reconcile;
   - category or role slugs drift from the contract;
   - protected files would be changed without explicit authorization;
   - public-feed promotion is not explicitly approved.
13. Build God View from the same run manifest so operators can see what arrived, what changed, what was filtered, what was backed up, and what remains blocked.
14. Keep the WordPress plugin display-only. It must not perform heavy ingestion, classification, backup, or feed mutation.
15. Do not install, activate, upload, merge, promote, publish, or overwrite production data without Howard's explicit approval.

## Required run artifacts

Each refresh must produce or update reviewable artifacts equivalent to:

- source inventory;
- raw pull manifest;
- pre-overwrite backup manifest;
- baseline-versus-candidate delta report;
- taxonomy audit;
- schema validation report;
- reconciliation report;
- review and rejection queues;
- God View digest;
- rollback manifest;
- operator handoff summary.

## Baseline matching rules

Fresh data must be compared with the existing canonical dataset before being written.

Prefer stable identity in this order:

1. source dataset plus source event ID;
2. existing canonical ID;
3. recurring-event registry identity;
4. normalized title, event date, borough, and location;
5. human review when identity remains uncertain.

Do not treat a title-only match as sufficient for automatic merge. Do not create a competing marker for a supporting permit, street closure, transportation operation, or grouped child record.

## Backup and recovery rule

No destructive replacement is allowed without a verified backup.

The standard repository backup location is:

`data/backups/live-refresh/<RUN_ID>/`

The standard manifest is:

`data/backups/live-refresh/<RUN_ID>/backup-manifest.json`

The standard recovery ZIP location for the WordPress map plugin is:

`docs/wordpress-plugin-deploy/nycif-events-map/releases/`

Before a new plugin package is approved, that directory must contain:

- the currently installed recovery ZIP;
- its SHA-256 checksum;
- the candidate ZIP;
- its SHA-256 checksum;
- `recovery-manifest.json` with install and rollback instructions.

The known safe rollback package from PR #164 is:

`nycif-events-map-1.3.1-safe-rollback.zip`

Known SHA-256:

`ea5b0ac0632fe09f99758b34cab67fa45bf753be4ca724b9bdeb5fa0d79101e9`

Do not claim that ZIP is recoverable until its actual repository or operator-storage path is confirmed and its hash is rechecked.

## WordPress plugin release gate

The next intended plugin version is 1.4.0 for the discovery-taxonomy-v02 Field Desk runtime.

Preparation may include source, package instructions, checksums, and a draft PR. Installation remains blocked until:

- Field Desk live Pages verification passes;
- the default `main` discovery feeds are public-ready;
- the repeated page-fetch bug is fixed or formally accepted;
- the recovery ZIP and checksum are verified;
- PHP lint and ZIP integrity pass;
- Howard explicitly approves installation.

## Final report

Return:

- run ID;
- baseline commit and candidate commit;
- files backed up;
- files proposed for replacement;
- source and row counts;
- added, changed, removed, unchanged counts;
- taxonomy/schema/reconciliation results;
- God View status;
- plugin package status;
- rollback location;
- blocked actions;
- explicit statement of what was not published or overwritten.
