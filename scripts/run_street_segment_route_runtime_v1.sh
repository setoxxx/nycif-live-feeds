#!/usr/bin/env bash
# Build current publication-safe street route geometry from official NYC sources.
set -eEuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="${NYCIF_ROUTE_WORK_DIR:-/tmp/nycif-route-authority-v1}"
GEOSUPPORT_RUNTIME_IMAGE="${GEOSUPPORT_RUNTIME_IMAGE:-nycplanning/docker-geosupport:26.2.0}"
LION_DATASET_URL="${LION_DATASET_URL:-https://data.cityofnewyork.us/download/2v4z-66xt/application/zip}"
IDENTITY="$WORK/street_segment_route_identity_v1.json"
LION_ZIP="$WORK/lion.zip"
LION_DIR="$WORK/lion-package"
LION_GEOJSON="$WORK/lion_route_segments_v1.geojson"
CANDIDATES="$WORK/lion-layer-candidates.tsv"

mkdir -p "$WORK"
rm -rf "$LION_DIR"
mkdir -p "$LION_DIR"

command -v docker >/dev/null 2>&1 || { echo "docker is required for NYC Planning GeoSupport" >&2; exit 1; }
command -v curl >/dev/null 2>&1 || { echo "curl is required for LION acquisition" >&2; exit 1; }
command -v unzip >/dev/null 2>&1 || { echo "unzip is required for LION acquisition" >&2; exit 1; }
command -v ogrinfo >/dev/null 2>&1 || { echo "ogrinfo is required for LION discovery" >&2; exit 1; }
command -v ogr2ogr >/dev/null 2>&1 || { echo "ogr2ogr is required for LION extraction" >&2; exit 1; }

# Identity must be rebuilt from this transaction's exact committed source snapshot.
docker run --rm \
  -e PYTHONDONTWRITEBYTECODE=1 \
  -e NYCIF_USE_RAW_SNAPSHOT=yes \
  -e NYCIF_ALLOW_LIVE_GEOSEARCH=no \
  -e NYCIF_ALLOW_LIVE_GEOCLIENT=no \
  -e GEOSUPPORT_RUNTIME_IMAGE="$GEOSUPPORT_RUNTIME_IMAGE" \
  -v "$ROOT:/workspace:ro" \
  -v "$WORK:/evidence" \
  -w /workspace \
  "$GEOSUPPORT_RUNTIME_IMAGE" \
  python scripts/build_street_segment_route_authority_v1.py \
    --identity-output /evidence/street_segment_route_identity_v1.json

python - "$IDENTITY" <<'PY'
import json
import sys
r = json.load(open(sys.argv[1], encoding="utf-8"))
assert r["schema_version"] == "NYCIF_STREET_SEGMENT_ROUTE_IDENTITY_V1"
assert r["publication_authority_granted"] is False
assert r["point_generation_allowed"] is False
assert r["geometry_join_status"] == "SEGMENT_IDENTIFIER_ONLY_PENDING_LION_JOIN"
print(json.dumps({
    "unique_segment_claim_count": r["unique_segment_claim_count"],
    "strict_segment_identity_count": r["strict_segment_identity_count"],
    "strict_occurrence_coverage": r["strict_occurrence_coverage"],
}, sort_keys=True))
PY

# No strict claims is a valid result. Emit an empty, QA-passing reader artifact
# without downloading LION; unresolved events remain list-only.
STRICT_COUNT="$(python - "$IDENTITY" <<'PY'
import json, sys
print(int(json.load(open(sys.argv[1]))["strict_segment_identity_count"]))
PY
)"
if [ "$STRICT_COUNT" -eq 0 ]; then
  cat > "$LION_GEOJSON" <<'JSON'
{"type":"FeatureCollection","features":[]}
JSON
  python "$ROOT/scripts/build_street_segment_route_authority_v1.py" \
    --identity-report "$IDENTITY" \
    --lion-geojson "$LION_GEOJSON"
  exit 0
fi

curl --fail --location --retry 3 --retry-all-errors \
  --output "$LION_ZIP" \
  "$LION_DATASET_URL"
unzip -q "$LION_ZIP" -d "$LION_DIR"

: > "$CANDIDATES"
while IFS= read -r gdb; do
  layer_list="$(ogrinfo -ro "$gdb" 2>/dev/null || true)"
  while IFS= read -r layer; do
    [ -n "$layer" ] || continue
    info="$(ogrinfo -ro -so "$gdb" "$layer" 2>/dev/null || true)"
    if printf '%s\n' "$info" | grep -qiE '^[[:space:]]*SegmentID:' && \
       printf '%s\n' "$info" | grep -qiE '^[[:space:]]*Geometry: (Line String|Multi Line String)'; then
      printf 'gdb\t%s\t%s\n' "$gdb" "$layer" >> "$CANDIDATES"
    fi
  done < <(
    printf '%s\n' "$layer_list" | sed -n -E \
      -e 's/^Layer: (.*) \([^)]*\)$/\1/p' \
      -e 's/^[[:space:]]*[0-9]+: (.*) \([^)]*\)$/\1/p' | sort -u
  )
done < <(find "$LION_DIR" -type d -iname '*.gdb' | sort)

cat "$CANDIDATES"
CANDIDATE_COUNT="$(wc -l < "$CANDIDATES" | tr -d ' ')"
if [ "$CANDIDATE_COUNT" -ne 1 ]; then
  echo "expected exactly one LION SegmentID line layer; found $CANDIDATE_COUNT" >&2
  exit 1
fi
IFS=$'\t' read -r _kind LION_SOURCE_PATH LION_SOURCE_LAYER < "$CANDIDATES"

WHERE_CLAUSE="$(python - "$IDENTITY" <<'PY'
import json, sys
r = json.load(open(sys.argv[1], encoding="utf-8"))
ids = sorted({
    str(row.get("function_3_segment_identifier") or "").strip()
    for row in r.get("claims", [])
    if row.get("strict_segment_identity") is True
} - {""})
escaped = [value.replace("'", "''") for value in ids]
print("SegmentID IN (" + ",".join("'" + value + "'" for value in escaped) + ")")
PY
)"

ogr2ogr -f GeoJSON -t_srs EPSG:4326 -where "$WHERE_CLAUSE" \
  "$LION_GEOJSON" "$LION_SOURCE_PATH" "$LION_SOURCE_LAYER"

python "$ROOT/scripts/build_street_segment_route_authority_v1.py" \
  --identity-report "$IDENTITY" \
  --lion-geojson "$LION_GEOJSON"

python - "$ROOT/data/reader-safe/street-segment-routes-v1-status.json" <<'PY'
import json, sys
r = json.load(open(sys.argv[1], encoding="utf-8"))
if r.get("qa_pass") is not True:
    raise SystemExit("street route reader QA failed")
for key in (
    "point_geometry_count",
    "invalid_geometry_count",
    "duplicate_occurrence_count",
    "canonical_duplicate_occurrence_count",
    "midpoint_publication_count",
):
    if r.get(key) != 0:
        raise SystemExit(f"street route zero gate failed: {key}={r.get(key)}")
print(json.dumps(r, indent=2, sort_keys=True))
PY
