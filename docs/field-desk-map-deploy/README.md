# Field-desk public map deploy (emergency restore 2026-07-13)

This package replaces the earlier M10 mirror with the validated emergency restore.

## Why this exists here

The repair was implemented and locally validated against `nycif-field-desk`, but this cloud agent token cannot push to `setoxxx/nycif-field-desk` (GitHub 403 for `cursor[bot]`). Until Field Desk repo write access is granted, deploy from this mirror.

## Copy into nycif-field-desk root

```bash
cd /path/to/nycif-field-desk
git switch main
git pull --ff-only origin main
git switch -c cursor/emergency-public-map-restoration-20260713

cp ../nycif-live-feeds/docs/field-desk-map-deploy/app-v06-safe.js ./
cp ../nycif-live-feeds/docs/field-desk-map-deploy/public-map-defaults-v01.js ./
cp ../nycif-live-feeds/docs/field-desk-map-deploy/index.html ./
cp ../nycif-live-feeds/docs/field-desk-map-deploy/service-worker.js ./
cp ../nycif-live-feeds/docs/field-desk-map-deploy/public-map-v01.css ./
cp ../nycif-live-feeds/docs/field-desk-map-deploy/event-significance-v01.js ./
cp ../nycif-live-feeds/docs/field-desk-map-deploy/map-date-key-v01.js ./
mkdir -p docs tests
cp ../nycif-live-feeds/docs/field-desk-map-deploy/event-significance-v01.md docs/
cp ../nycif-live-feeds/docs/field-desk-map-deploy/public-map-emergency-restoration-diagnostic.md docs/
cp ../nycif-live-feeds/docs/field-desk-map-deploy/public-map-emergency-restoration-qa.md docs/
cp ../nycif-live-feeds/docs/field-desk-map-deploy/tests/map-restore-unit.test.js tests/

git add app-v06-safe.js public-map-defaults-v01.js index.html service-worker.js public-map-v01.css \
  event-significance-v01.js map-date-key-v01.js docs tests
git commit -m "Emergency: restore public event population, fitness, and significance badges"
git push -u origin cursor/emergency-public-map-restoration-20260713
```

Alternate artifact:

- `dist/nycif-field-desk-map-restore-v01.zip`
- `dist/nycif-field-desk-emergency-restore-20260713.patch`

## What this restore does

- Boots staged feed first, then full, then major
- Public defaults `staged-live-v03` (parks/general/fitness on, majorOnly off)
- Next-available-date fallback when Today is empty
- Fitness / wellness category everywhere
- Gold/Silver/Bronze evidence-based significance UI
- Service worker cache `nycif-v015-emergency-map-restore`
- Preserves 5PM / cannabis / correlation overlays

## Do not

- Modify `data/location_cache.json`
- Upload the WordPress plugin before GitHub Pages serves this Field Desk build
