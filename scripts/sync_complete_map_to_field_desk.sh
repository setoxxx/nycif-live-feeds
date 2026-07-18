#!/usr/bin/env bash
# Copy canonical RC public map runtime from live-feeds to field-desk.
# Usage:
#   ./scripts/sync_complete_map_to_field_desk.sh /path/to/nycif-field-desk
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="${1:-$ROOT/../nycif-field-desk}"
SRC="$ROOT/docs/field-desk-map-deploy"
MAP="$SRC/schema-v1-major-all-v01"
test -d "$DEST/.git" || { echo "field-desk not found at $DEST"; exit 1; }

cp "$MAP/app-schema-v1-major-all-v01.js" "$DEST/app-schema-v1-major-all-v01.js"
cp "$SRC/discovery-taxonomy-v02/discovery-patch-v02.js" "$DEST/discovery-patch-v02.js"
cp "$SRC/discovery-taxonomy-v02/public-approved-overlays-v01.js" "$DEST/public-approved-overlays-v01.js"
cp "$MAP/index.html" "$DEST/index.html"
cp "$MAP/public-map-v01.css" "$DEST/public-map-v01.css"
cp "$MAP/service-worker.js" "$DEST/service-worker.js"
cp "$SRC/shared/nycif-tip-jar-v01.js" "$DEST/nycif-tip-jar-v01.js"
rm -f "$DEST/staged-map-mode-v01.css"

cd "$DEST"
node --check app-schema-v1-major-all-v01.js
node --check discovery-patch-v02.js
node --check nycif-tip-jar-v01.js
node --check service-worker.js
grep -q public-map-v09 index.html
grep -q 'nycif-tip-jar-v01.js?v=05' index.html

BRANCH="cursor/rc-public-map-v08-c1f9"
git checkout "$BRANCH" 2>/dev/null || git checkout -b "$BRANCH"
git add \
  app-schema-v1-major-all-v01.js \
  discovery-patch-v02.js \
  public-approved-overlays-v01.js \
  index.html \
  public-map-v01.css \
  service-worker.js \
  nycif-tip-jar-v01.js
git commit -m "Deploy RC public map v08 (tip jar strobe, legacy cleanup)" || true
echo "Ready to: git push -u origin $BRANCH && open PR && merge"
