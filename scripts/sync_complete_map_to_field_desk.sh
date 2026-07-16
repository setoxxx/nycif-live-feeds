#!/usr/bin/env bash
# Run from a checkout that has BOTH repos as siblings, OR pass FIELD_DESK path.
# Usage:
#   ./scripts/sync_complete_map_to_field_desk.sh /path/to/nycif-field-desk
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="${1:-$ROOT/../nycif-field-desk}"
SRC="$ROOT/docs/field-desk-map-deploy"
test -d "$DEST/.git" || { echo "field-desk not found at $DEST"; exit 1; }
cp "$SRC/schema-v1-major-all-v01/app-schema-v1-major-all-v01.js" "$DEST/app-schema-v1-major-all-v01.js"
cp "$SRC/discovery-taxonomy-v02/discovery-patch-v02.js" "$DEST/discovery-patch-v02.js"
cp "$SRC/schema-v1-major-all-v01/index.html" "$DEST/index.html"
cd "$DEST"
node --check app-schema-v1-major-all-v01.js
node --check discovery-patch-v02.js
git checkout -b cursor/complete-map-pages-handshake-d65d 2>/dev/null || git checkout cursor/complete-map-pages-handshake-d65d
git add app-schema-v1-major-all-v01.js discovery-patch-v02.js index.html
git commit -m "Deploy Complete-the-Map runtime to Pages (sport emojis + lane handshake)" || true
echo "Ready to: git push -u origin HEAD && gh pr create --fill && gh pr merge"
