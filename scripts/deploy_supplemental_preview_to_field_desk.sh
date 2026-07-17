#!/usr/bin/env bash
# Deploy supplemental export preview to field-desk main (GitHub Actions).
# Requires FIELD_DESK_TOKEN env var with push access to setoxxx/nycif-field-desk.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PREVIEW_SRC="$ROOT/docs/field-desk-map-deploy/supplemental-export-preview"

if [ -z "${FIELD_DESK_TOKEN:-}" ]; then
  echo "::error::FIELD_DESK_TOKEN is not set"
  exit 1
fi

git clone "https://x-access-token:${FIELD_DESK_TOKEN}@github.com/setoxxx/nycif-field-desk.git" /tmp/field-desk
cd /tmp/field-desk
git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git checkout main
git pull origin main

cp "$PREVIEW_SRC/supplemental-approved-export-preview-v01.js" ./supplemental-approved-export-preview-v01.js
cp "$PREVIEW_SRC/approved-export-preview.html" ./approved-export-preview.html
mkdir -p ./tools/public-map
cp "$PREVIEW_SRC/supplemental-export-preview.test.mjs" ./tools/public-map/supplemental-export-preview.test.mjs

if ! grep -q 'supplemental-approved-export-preview-v01.js' desk.html; then
  sed -i 's|feed-status-panel-v01.js?v=01"></script>|feed-status-panel-v01.js?v=01"></script>\n  <script src="./supplemental-approved-export-preview-v01.js?v=01"></script>|' desk.html
fi
grep -q 'supplemental-approved-export-preview-v01.js' desk.html

if ! grep -q "Supplemental approved export preview" README.md; then
  {
    echo ""
    echo "### Supplemental approved export preview (admin / QA only)"
    echo ""
    echo "- Standalone: \`approved-export-preview.html\` (**3,566** approved supplemental events)"
    echo "- Desk overlay: \`desk.html?previewExport=1\`"
    echo "- Feed: \`https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/main/dist/supplemental_approved_export_feed.json\`"
    echo "- Preview only — not production map; \`promotion_allowed=false\`."
  } >> README.md
fi

node --check supplemental-approved-export-preview-v01.js
node --test tools/public-map/supplemental-export-preview.test.mjs
grep -q "3,566" approved-export-preview.html
grep -q "supplemental_approved_export_feed" supplemental-approved-export-preview-v01.js

git add \
  supplemental-approved-export-preview-v01.js \
  approved-export-preview.html \
  tools/public-map/supplemental-export-preview.test.mjs \
  desk.html \
  README.md

if git diff --cached --quiet; then
  echo "Field-desk already has supplemental export preview runtime."
  exit 0
fi

git commit -m "Deploy supplemental approved export preview (3566 events)"
git push origin main
