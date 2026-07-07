# Live Sync QA Auto-Commit Risk After PR #76

Status: audit note
Scope: workflow gating only
Related recovery PR: #76

## Summary

PR #76 restored generated artifact drift to the verified XRI-G36 baseline. Before any new XRI phase resumes, the live-sync QA workflow must not be able to recreate the same drift automatically.

This audit note documents the risk and the gating change in this branch.

## Risk identified

The previous `.github/workflows/live-sync-qa.yml` configuration could run on an hourly schedule and on pushes to `main`, fetch live NYC Open Data, generate cache/feed/GPS artifacts, commit those generated files, rebase from `origin/main`, and push directly back to `main`.

That behavior was incompatible with the XRI recovery posture because it could mutate:

- `data/location_cache.json`
- `data/raw_nyc_open_data_snapshot.json`
- `data/live_sync_report.json`
- `data/nycif_live_test_enriched_events.json`
- `data/test_enriched_feed_manifest.json`
- `data/nycif_staged_live_events.json`
- `data/staged_live_manifest.json`
- GPS review, geocoding, approval, staging, and QA report artifacts under `data/gps_*`

## Gating policy

This branch changes live-sync QA to be manual and read-only by default:

- removes the scheduled cron trigger
- removes push-to-main triggering
- changes repository permission from `contents: write` to `contents: read`
- removes the generated-artifact commit/push step
- requires `allow_live_fetch == yes` before the job runs
- requires `allow_email == yes` before the email step runs
- does not commit generated artifacts to `main`
- does not create generated data artifacts in the repository
- does not start XRI-G66 or any new XRI phase

## Review expectation

Review this PR as a recovery gate. It should change only:

- `.github/workflows/live-sync-qa.yml`
- `docs/audits/live-sync-qa-autocommit-risk-after-pr76.md`

No generated data files should change in this PR.
