#!/usr/bin/env bash
# Preflight gate before WordPress /map/ or plugin deploy.
# Usage: ./scripts/preflight_field_desk_map_release.sh [RUNTIME_V]
set -euo pipefail

RUNTIME_V="${1:-public-map-v10}"
BASE="https://setoxxx.github.io/nycif-field-desk"
MAP_URL="${BASE}/?v=${RUNTIME_V}&resetFilters=1&feeds=main"
FEED_MANIFEST="https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/main/data/schema-v1-discovery/approved/manifest.json"
FIELD_DESK_REPO="setoxxx/nycif-field-desk"
LIVE_FEEDS_REPO="setoxxx/nycif-live-feeds"

pass=0
fail=0

check() {
  local name="$1"
  shift
  if "$@"; then
    echo "PASS $name"
    pass=$((pass + 1))
  else
    echo "FAIL $name"
    fail=$((fail + 1))
  fi
}

http_200() {
  local url="$1"
  local code
  code="$(curl -sS -o /dev/null -w '%{http_code}' -L "$url")"
  [[ "$code" == "200" ]]
}

echo "=== NYCIF map release preflight (runtime v=${RUNTIME_V}) ==="
echo "Map URL: $MAP_URL"
echo

check "map index HTTP 200" http_200 "$MAP_URL"

HTML="$(curl -sSL "$MAP_URL")"
check "index references runtime token" grep -q "$RUNTIME_V" <<<"$HTML"
check "index loads display-mode script" grep -q 'public-display-mode-v01.js' <<<"$HTML"
check "index loads app bundle" grep -q 'app-schema-v1-major-all-v01.js' <<<"$HTML"

check "display-mode JS HTTP 200" http_200 "${BASE}/public-display-mode-v01.js"
DM_JS="$(curl -sSL "${BASE}/public-display-mode-v01.js")"
check "display-mode defines NYCIF_DISPLAY_MODE" grep -q 'NYCIF_DISPLAY_MODE' <<<"$DM_JS"
check "display-mode uses 720px breakpoint" grep -q 'max-width: 720px' <<<"$DM_JS"

check "app bundle HTTP 200" http_200 "${BASE}/app-schema-v1-major-all-v01.js"

check "discovery manifest HTTP 200" http_200 "$FEED_MANIFEST"
MANIFEST="$(curl -sSL "$FEED_MANIFEST")"
check "discovery manifest has approved total" python3 -c "import json,sys; m=json.load(sys.stdin); sys.exit(0 if int(m.get('total',0))>0 else 1)" <<<"$MANIFEST"

FIELD_DESK_SHA="$(curl -sS "https://api.github.com/repos/${FIELD_DESK_REPO}/commits/main" | python3 -c "import json,sys; print(json.load(sys.stdin).get('sha','')[:12])" 2>/dev/null || true)"
LIVE_FEEDS_SHA="$(curl -sS "https://api.github.com/repos/${LIVE_FEEDS_REPO}/commits/main" | python3 -c "import json,sys; print(json.load(sys.stdin).get('sha','')[:12])" 2>/dev/null || true)"

if [[ -n "$FIELD_DESK_SHA" ]]; then
  echo "INFO field-desk main @ ${FIELD_DESK_SHA}"
  check "field-desk index contains runtime token" curl -sSL "${BASE}/index.html" | grep -q "$RUNTIME_V"
else
  echo "WARN could not resolve field-desk main commit (API rate limit?)"
fi

if [[ -n "$LIVE_FEEDS_SHA" ]]; then
  echo "INFO live-feeds main @ ${LIVE_FEEDS_SHA}"
  FEED_GEN="$(python3 -c "import json,sys; print(json.load(sys.stdin).get('generated_at_utc',''))" <<<"$MANIFEST")"
  echo "INFO discovery manifest generated_at_utc=${FEED_GEN}"
else
  echo "WARN could not resolve live-feeds main commit (API rate limit?)"
fi

echo
echo "=== Summary: ${pass} passed, ${fail} failed ==="
if [[ "$fail" -gt 0 ]]; then
  echo "DO NOT deploy WordPress until all checks PASS."
  exit 1
fi
echo "Preflight PASS — safe to proceed with WordPress deploy (human viewport QA still required)."
