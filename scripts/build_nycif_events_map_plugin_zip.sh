#!/usr/bin/env bash
# Build uploadable WordPress plugin ZIP for review before install.
# WordPress expects: nycif-events-map/nycif-events-map.php inside the archive.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/docs/wordpress-plugin-deploy/nycif-events-map"
OUT="$ROOT/dist"
VER="$(grep "NYCIF_EVENTS_MAP_VERSION" "$SRC/nycif-events-map.php" | head -1 | sed "s/.*'\\([^']*\\)'.*/\\1/")"
ZIP="$OUT/nycif-events-map-${VER}.zip"
STAGING="$(mktemp -d)"

cleanup() {
  rm -rf "$STAGING"
}
trap cleanup EXIT

mkdir -p "$OUT"
rm -f "$ZIP"
cp -a "$SRC" "$STAGING/nycif-events-map"
(
  cd "$STAGING"
  zip -r "$ZIP" nycif-events-map -x '*/.DS_Store'
)

echo "Built: $ZIP"
echo "Contents:"
unzip -l "$ZIP"
echo
echo "Structure check (must list nycif-events-map/ prefix):"
if ! unzip -l "$ZIP" | grep -q 'nycif-events-map/nycif-events-map.php'; then
  echo "FAIL: ZIP missing nycif-events-map/nycif-events-map.php"
  exit 1
fi
echo "PASS: nycif-events-map/nycif-events-map.php present"
echo
echo "Verify version in PHP:"
grep NYCIF_EVENTS_MAP_VERSION "$SRC/nycif-events-map.php" | head -1
grep NYCIF_RUNTIME_CACHE_BUST "$SRC/nycif-events-map.php" | head -1
