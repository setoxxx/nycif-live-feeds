# Field-desk public map deploy

## Complete-the-Map Pages handshake (READY — apply to field-desk)

Backend feed side is already live on `nycif-live-feeds` main (#185).  
GitHub Pages still needs these three files copied into `nycif-field-desk`:

```bash
# From a machine/agent WITH write access to nycif-field-desk:
./scripts/sync_complete_map_to_field_desk.sh /path/to/nycif-field-desk
cd /path/to/nycif-field-desk
git push -u origin HEAD
gh pr create --title "Deploy Complete-the-Map runtime to Pages" --body "Sport emojis + lane handshake."
gh pr merge --squash
```

Or open a Cloud Agent **on the field-desk repo** (not live-feeds) and run the same copy from:

- `schema-v1-major-all-v01/app-schema-v1-major-all-v01.js`
- `discovery-taxonomy-v02/discovery-patch-v02.js`
- `schema-v1-major-all-v01/index.html` (`?v=public-map-v07`)

Issues: https://github.com/setoxxx/nycif-field-desk/issues/127 https://github.com/setoxxx/nycif-field-desk/issues/128

---

# Field-desk public map deploy (M10 staged live)

Civic people-facing Review/Help package (Jobs / Volunteer / markets / help places): see [`civic-people-facing-v01/README.md`](./civic-people-facing-v01/README.md). That lane stays staging/review-only and does not replace Approved permits.

Copy these files into `nycif-field-desk/` root (and admin panel into `admin/`):

```bash
cp docs/field-desk-map-deploy/app-v06-safe.js ../nycif-field-desk/
cp docs/field-desk-map-deploy/public-map-defaults-v01.js ../nycif-field-desk/
cp docs/field-desk-map-deploy/index.html ../nycif-field-desk/
cp docs/field-desk-admin-deploy/admin/live-pipeline-panel-v01.js ../nycif-field-desk/admin/
git add app-v06-safe.js public-map-defaults-v01.js index.html admin/live-pipeline-panel-v01.js
git commit -m "Public map: staged live default (M10 resolver-backed feed)"
git push -u origin cursor/live-staged-map-m10-5215
```

## What changes

- **Default boot feed:** staged (`data/nycif_staged_live_events.json`) instead of stale major feed
- **Filters:** parks + general enabled; major-only off
- **Marker cap:** 2,000 for staged mode
- **Cache bust:** `?v=m10-staged-live` on WordPress iframe

## Prerequisites

Run on `nycif-live-feeds` main (or M10 PR) first:

```bash
NYCIF_ALLOW_LIVE_GEOSEARCH=yes python3 scripts/build_test_enriched_feed.py
python3 scripts/build_staged_production_feed.py
python3 scripts/build_public_map_feeds.py
```

Merge backend PR, then deploy field-desk to GitHub Pages.

## Verify

- https://setoxxx.github.io/nycif-field-desk/ — should show ~32k staged events (filtered by date/category)
- https://nycinfocus.com/map/ — update iframe cache param after deploy
