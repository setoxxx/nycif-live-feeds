#!/usr/bin/env bash
# Build uploadable WordPress plugin ZIP for review before install.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/docs/wordpress-plugin-deploy/nycif-events-map"
OUT="$ROOT/dist"
VER="$(grep "NYCIF_EVENTS_MAP_VERSION" "$SRC/nycif-events-map.php" | head -1 | sed "s/.*'\\([^']*\\)'.*/\\1/")"
ZIP="$OUT/nycif-events-map-${VER}.zip"

mkdir -p "$OUT"
rm -f "$ZIP"
(
  cd "$SRC"
  zip -r "$ZIP" . -x '*.DS_Store'
)

echo "Built: $ZIP"
echo "Contents:"
unzip -l "$ZIP"
echo
echo "Verify version in PHP:"
grep NYCIF_EVENTS_MAP_VERSION "$SRC/nycif-events-map.php" | head -1
grep NYCIF_RUNTIME_CACHE_BUST "$SRC/nycif-events-map.php" | head -1
