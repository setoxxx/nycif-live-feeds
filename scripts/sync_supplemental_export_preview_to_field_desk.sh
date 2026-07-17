#!/usr/bin/env bash
# Copy supplemental export preview assets from live-feeds to field-desk.
# Usage:
#   ./scripts/sync_supplemental_export_preview_to_field_desk.sh /path/to/nycif-field-desk
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="${1:-$ROOT/nycif-field-desk}"
SRC="$ROOT/docs/field-desk-map-deploy/supplemental-export-preview"
test -d "$DEST/.git" || { echo "field-desk not found at $DEST"; exit 1; }
test -d "$SRC" || { echo "preview source not found at $SRC"; exit 1; }

cp "$SRC/supplemental-approved-export-preview-v01.js" "$DEST/supplemental-approved-export-preview-v01.js"
cp "$SRC/approved-export-preview.html" "$DEST/approved-export-preview.html"
cp "$SRC/supplemental-export-preview.test.mjs" "$DEST/tools/public-map/supplemental-export-preview.test.mjs"

if ! grep -q 'supplemental-approved-export-preview-v01.js' "$DEST/desk.html"; then
  sed -i 's|feed-status-panel-v01.js?v=01"></script>|feed-status-panel-v01.js?v=01"></script>\n  <script src="./supplemental-approved-export-preview-v01.js?v=03"></script>|' "$DEST/desk.html"
fi
sed -i 's|supplemental-approved-export-preview-v01.js?v=0[12]|supplemental-approved-export-preview-v01.js?v=03|g' "$DEST/desk.html"

cd "$DEST"
node --check supplemental-approved-export-preview-v01.js
node --test tools/public-map/supplemental-export-preview.test.mjs

BRANCH="cursor/supplemental-export-preview-c1f9"
git checkout "$BRANCH" 2>/dev/null || git checkout -b "$BRANCH"
git add supplemental-approved-export-preview-v01.js approved-export-preview.html tools/public-map/supplemental-export-preview.test.mjs
git commit -m "Sync supplemental export preview from nycif-live-feeds (3566 events)" || true
echo "Ready to: git push -u origin $BRANCH && open PR && merge"
