#!/usr/bin/env bash
# Atomic daily production transaction for the NYC In Focus News Desk.
set -eEuo pipefail

RUNTIME_DIR="${NYCIF_RUNTIME_DIR:-.runtime}"
FAILURE_JSON="$RUNTIME_DIR/nycif-daily-failure.json"
FAILURE_LEGACY="$RUNTIME_DIR/nycif-daily-failure"
PREVIOUS_POINTER="$RUNTIME_DIR/nycif-previous-public-feed"
umask 077
install -d -m 700 "$RUNTIME_DIR"
CURRENT_STAGE="initialization"
CURRENT_COMMAND_ID="initialize_transaction"

record_shell_failure() {
  local code="$?"
  local line="${BASH_LINENO[0]:-not_available}"
  if [ ! -f "$FAILURE_JSON" ]; then
    NYCIF_FAILURE_STAGE="$CURRENT_STAGE" \
    NYCIF_FAILURE_COMMAND_ID="$CURRENT_COMMAND_ID" \
    NYCIF_FAILURE_EXIT_CODE="$code" \
    NYCIF_FAILURE_LINE="$line" \
      python - <<'PY'
import os
from scripts import daily_refresh_state as state
from scripts.run_daily_refresh_stage import failure_payload

payload = failure_payload(
    stage=os.environ.get("NYCIF_FAILURE_STAGE", "platform_or_uninstrumented_failure"),
    command_id=os.environ.get("NYCIF_FAILURE_COMMAND_ID", "workflow_shell_command"),
    exit_code=int(os.environ.get("NYCIF_FAILURE_EXIT_CODE", "1")),
    exception_class="ShellCommandFailure",
    error_summary=(
        "A shell command failed before a captured stderr summary was available. "
        "Review the GitHub Actions job log for this stage."
    ),
    public_feed_commit_occurred=False,
    shell_line=os.environ.get("NYCIF_FAILURE_LINE", "not_available"),
)
state.atomic_write_failure(payload)
PY
  fi
  printf '%s\n%s\n%s\n%s\n' "$CURRENT_STAGE" "$code" "$line" "$CURRENT_COMMAND_ID" > "$FAILURE_LEGACY"
  exit "$code"
}
trap record_shell_failure ERR

run_stage() {
  local stage="$1"
  local command_id="$2"
  shift 2
  CURRENT_STAGE="$stage"
  CURRENT_COMMAND_ID="$command_id"
  python scripts/run_daily_refresh_stage.py \
    --stage "$stage" \
    --command-id "$command_id" \
    -- "$@"
}

git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
rm -f "$FAILURE_JSON" "$FAILURE_LEGACY" "$PREVIOUS_POINTER"

run_stage \
  "preflight_live_event_contracts" \
  "test_live_event_intake_refresh_current" \
  python scripts/test_live_event_intake_refresh_current.py
run_stage \
  "preflight_daily_production_hardening" \
  "test_daily_production_hardening" \
  python scripts/test_daily_production_hardening.py
run_stage \
  "preflight_python_compile" \
  "compile_refresh_reliability_scripts" \
  python -m py_compile \
    scripts/run_daily_refresh_stage.py \
    scripts/test_live_event_intake_refresh_current.py \
    scripts/refresh_runtime_fallback_feeds.py \
    scripts/record_blocked_daily_data_health.py \
    scripts/check_field_desk_overlay_health.py \
    scripts/project_events_discovery_v03.py \
    scripts/build_news_desk_reader_safe.py \
    scripts/build_maplibre_reader_safe_v03.py \
    scripts/augment_daily_data_health_v03.py

# If main advances before push, discard generated work, reset to the new tip,
# and rebuild the complete transaction. Never merge generated conflicts or
# force-push over another successful data refresh.
for attempt in 1 2 3; do
  rm -f "$FAILURE_JSON" "$FAILURE_LEGACY"

  run_stage "reset_to_current_main" "fetch_origin_main" git fetch origin main
  run_stage "reset_to_current_main" "reset_to_fetched_main" git reset --hard FETCH_HEAD
  PREVIOUS_PUBLIC_FEED_SHA="$(git rev-parse HEAD)"
  export PREVIOUS_PUBLIC_FEED_SHA
  printf '%s\n' "$PREVIOUS_PUBLIC_FEED_SHA" > "$PREVIOUS_POINTER"

  run_stage \
    "official_source_live_fetch_and_permit_staging" \
    "live_event_intake_refresh" \
    python scripts/live_event_intake_refresh.py

  run_stage \
    "calendar_parks_exact_occurrence_intake" \
    "refresh_official_supplemental_occurrences" \
    python scripts/refresh_official_supplemental_occurrences.py

  run_stage \
    "discovery_major_projection" \
    "build_events_schema_v1_major" \
    python scripts/build_events_schema_v1_major.py
  run_stage \
    "street_festival_projection" \
    "build_street_festivals_feed" \
    python scripts/build_street_festivals_feed.py
  run_stage \
    "full_discovery_projection_and_dedupe" \
    "project_events_discovery_v03" \
    python scripts/project_events_discovery_v03.py
  run_stage \
    "strict_source_reconciliation" \
    "enforce_strict_discovery_reconciliation" \
    python scripts/enforce_strict_discovery_reconciliation.py
  run_stage \
    "comprehensive_public_feed" \
    "build_comprehensive_event_feed" \
    python scripts/build_comprehensive_event_feed.py

  run_stage \
    "news_desk_money_viral_and_civic_overlays" \
    "run_daily_people_facing_desk_sync" \
    python scripts/run_daily_people_facing_desk_sync.py --skip-network-sync
  run_stage \
    "news_desk_reader_safe_projection" \
    "build_news_desk_reader_safe" \
    python scripts/build_news_desk_reader_safe.py
  run_stage \
    "maplibre_reader_safe_projection" \
    "build_maplibre_reader_safe_v03" \
    python scripts/build_maplibre_reader_safe_v03.py

  run_stage \
    "runtime_emergency_fallback" \
    "refresh_runtime_fallback_feeds" \
    python scripts/refresh_runtime_fallback_feeds.py

  run_stage \
    "daily_data_health_gate" \
    "build_daily_data_health" \
    python scripts/build_daily_data_health.py
  run_stage \
    "daily_data_health_v3_augmentation" \
    "augment_daily_data_health_v03" \
    python scripts/augment_daily_data_health_v03.py

  run_stage \
    "god_view_project_state" \
    "generate_godview_project_state" \
    python scripts/generate_godview_project_state.py --fetch-github
  run_stage \
    "god_view_project_state" \
    "apply_daily_data_health_to_godview" \
    python scripts/apply_daily_data_health_to_godview.py

  CURRENT_STAGE="final_runtime_validation"
  CURRENT_COMMAND_ID="validate_complete_runtime_artifacts"
  python - <<'PY'
import glob
import json
import sys

raw = json.load(open("data/raw_nyc_open_data_snapshot.json"))
live = json.load(open("data/live_sync_report.json"))
calendar = json.load(open("data/nyc_citywide_events_calendar_snapshot.json"))
calendar_report = json.load(open("data/nyc_citywide_events_calendar_sync_report.json"))
parks = json.load(open("data/nyc_parks_bigapps_events_snapshot.json"))
parks_report = json.load(open("data/nyc_parks_bigapps_events_sync_report.json"))
test_manifest = json.load(open("data/test_enriched_feed_manifest.json"))
staged_manifest = json.load(open("data/staged_live_manifest.json"))
staged = json.load(open("data/nycif_staged_live_events.json"))
supplemental = json.load(open("data/supplemental_events_staging_feed.json"))
reconciliation = json.load(open("data/events_discovery_reconciliation_v02.json"))
v3 = json.load(open("data/events_discovery_v3_authority_report.json"))
news_safe = json.load(open("data/reader-safe/news-desk-status-v02.json"))
map_safe = json.load(open("data/reader-safe/national-map-events-v03-status.json"))
health = json.load(open("status/nycif-daily-data-health.json"))
overlay_health = json.load(open("status/nycif-field-desk-overlay-health.json"))
major = json.load(open("data/schema-v1-discovery/major/events.json"))
emergency = json.load(open("nycif_major_radar_map_events.json"))
fallback_report = json.load(open("data/runtime_fallback_feed_report.json"))
photographer = json.load(open("data/photographer_assignment_calendar_report.json"))
viral = json.load(open("data/photographer_viral_recurrence_report.json"))
manifest = json.load(open("data/schema-v1-discovery/approved/manifest.json"))
pages = glob.glob("data/schema-v1-discovery/approved/pages/*.json")
report = json.load(open("data/comprehensive_feed_report.json"))
whats_new = json.load(open("data/nycif_new_events.json"))

calendar_rows = calendar if isinstance(calendar, list) else calendar.get("events", [])
parks_rows = parks.get("events", []) if isinstance(parks, dict) else parks
supplemental_rows = supplemental.get("events", []) if isinstance(supplemental, dict) else supplemental
staged_events = staged.get("events") if isinstance(staged, dict) else None
major_events = major.get("events") if isinstance(major, dict) else major

if not isinstance(raw, list) or not raw:
    sys.exit("live NYC permitted-event snapshot is empty")
if live.get("raw_rows_loaded") != len(raw):
    sys.exit(f"live sync count {live.get('raw_rows_loaded')} != raw snapshot {len(raw)}")
if not calendar_report.get("qa_pass") or not calendar_rows:
    sys.exit("Citywide Calendar live sync failed or returned no active events")
if not parks_report.get("qa_pass") or parks_report.get("fetch_mode") != "live" or not parks_rows:
    sys.exit("Parks current-events source was not a successful live fetch")
if len(supplemental_rows) < len(calendar_rows) + len(parks_rows) - int(calendar_report.get("canceled_excluded", 0) or 0):
    print("Supplemental occurrence total is lower than raw source total; strict reconciliation remains authoritative.")
if test_manifest.get("raw_rows_loaded") != len(raw):
    sys.exit("test enrichment count does not match current permitted-event snapshot")
if not isinstance(staged_events, list) or not staged_events:
    sys.exit("staged map-ready feed has no events")
if staged_manifest.get("staged_feed_events") != len(staged_events):
    sys.exit("staged manifest count does not match staged rows")
if staged_manifest.get("cross_date_street_occurrences_suppressed") != 0:
    sys.exit("cross-date recurring street occurrences were suppressed")
if not reconciliation.get("reconciles_strict"):
    sys.exit("strict source reconciliation did not pass")
if not v3.get("qa_pass") or not v3.get("raw_accounting_pass"):
    sys.exit("Projector V3 authority or raw accounting gate failed")
for key in (
    "silent_identity_loss",
    "duplicate_exact_occurrences",
    "unsupported_exact_pin_count",
    "implicit_source_all_count",
    "legacy_occurrence_authority_count",
    "legacy_coordinate_authority_count",
):
    if v3.get(key) != 0:
        sys.exit(f"Projector V3 zero gate failed: {key}={v3.get(key)}")
if v3.get("invalid_publication_state_count", 0) != 0:
    sys.exit("Projector V3 emitted an invalid MAP_READY publication state")
if news_safe.get("unsupported_exact_pin_count") != 0 or news_safe.get("browser_raw_repository_required") is not False:
    sys.exit("News Desk reader-safe authority gate failed")
for key in (
    "unsupported_marker_count",
    "wrong_authority_marker_count",
    "location_evidence_failure_count",
    "borough_contradiction_count",
    "duplicate_exact_occurrence_count",
    "general_area_exact_geometry_count",
):
    if map_safe.get(key) != 0:
        sys.exit(f"MapLibre zero gate failed: {key}={map_safe.get(key)}")
if not map_safe.get("qa_pass"):
    sys.exit("MapLibre reader-safe marker audit failed")
if not health.get("release_ready") or health.get("status") != "READY":
    sys.exit("daily data health is not READY")
if not health.get("v3_runtime", {}).get("zero_gate_pass"):
    sys.exit("daily V3 health augmentation did not certify zero gates")
if not overlay_health.get("qa_pass") or overlay_health.get("overlay_count") != 3:
    sys.exit("Field Desk auxiliary overlay health did not pass")
if not isinstance(major_events, list) or not major_events:
    sys.exit("major feed has no events")
if not isinstance(emergency, list) or len(emergency) != len(major_events):
    sys.exit("emergency fallback does not match authoritative major feed count")
if not fallback_report.get("qa_pass") or fallback_report.get("duplicate_ids") != 0:
    sys.exit("emergency fallback QA failed")
if not photographer.get("qa_pass") or not viral.get("qa_pass"):
    sys.exit("News Desk money/viral overlay QA failed")
if manifest.get("page_count") != len(pages) or not pages:
    sys.exit("approved manifest page count does not match page files")
if not manifest.get("latest_date"):
    sys.exit("approved manifest missing latest_date")
if not report.get("qa_pass") or report.get("kept", 0) < 1:
    sys.exit("coverage report failed QA or scanned no events")
if "new_this_run" not in whats_new:
    sys.exit("what's-new diff missing new_this_run")

print(
    f"READY V3: {len(raw)} permits, {len(calendar_rows)} Calendar, {len(parks_rows)} Parks, "
    f"{len(staged_events)} staged, {manifest.get('total')} approved, "
    f"{map_safe.get('exact_marker_count')} certified MapLibre markers, "
    f"{news_safe.get('money_emitted_rows')} reader-safe money, "
    f"{news_safe.get('viral_emitted_rows')} reader-safe viral, "
    f"borough_unverified={map_safe.get('borough_unverified_count')}, "
    f"{whats_new['new_this_run']} newly added"
)
PY

  CURRENT_STAGE="rollback_pointer"
  CURRENT_COMMAND_ID="write_last_known_good_pointer"
  python - <<'PY'
import json
import os
from datetime import datetime, timezone

approved = json.load(open("data/schema-v1-discovery/approved/manifest.json"))
health = json.load(open("status/nycif-daily-data-health.json"))
pointer = {
    "artifact_type": "nycif_last_known_good_feed_pointer",
    "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    "previous_public_feed_commit": os.environ["PREVIOUS_PUBLIC_FEED_SHA"],
    "candidate_health_status": health.get("status"),
    "candidate_approved_generated_at_utc": approved.get("generated_at_utc"),
    "candidate_approved_events": approved.get("total"),
    "rollback_instruction": "Reset or revert the candidate refresh commit to restore previous_public_feed_commit.",
}
open("status/nycif-last-known-good-feed.json", "w").write(
    json.dumps(pointer, indent=2, sort_keys=True) + "\n"
)
PY

  CURRENT_STAGE="stage_ready_artifacts"
  CURRENT_COMMAND_ID="git_add_ready_artifacts"
  git add \
    nycif_major_radar_map_events.json \
    data/runtime_fallback_feed_report.json \
    data/raw_nyc_open_data_snapshot.json \
    data/live_sync_report.json \
    data/nyc_citywide_events_calendar_snapshot.json \
    data/nyc_citywide_events_calendar_sync_report.json \
    data/nyc_parks_bigapps_events_snapshot.json \
    data/nyc_parks_bigapps_events_sync_report.json \
    data/supplemental_events_staging_feed.json \
    data/official_supplemental_occurrence_refresh_report.json \
    data/nycif_live_test_enriched_events.json \
    data/test_enriched_feed_manifest.json \
    data/nycif_staged_live_events.json \
    data/staged_live_manifest.json \
    data/nyc_geosearch_gazetteer_cache.json \
    data/schema-v1-discovery \
    data/nycif_new_events.json \
    data/comprehensive_feed_report.json \
    data/_event_seen_index.json \
    data/nycif_street_festivals_feed.json \
    data/events_discovery_contract_v02.json \
    data/events_discovery_v02_approved.json \
    data/events_discovery_v02_review.json \
    data/events_discovery_v02_major.json \
    data/events_discovery_taxonomy_v02_audit.json \
    data/events_discovery_reconciliation_v02.json \
    data/events_discovery_grouping_v02_report.json \
    data/events_discovery_schema_validation_v02.json \
    data/events_discovery_v3_authority_report.json \
    data/events_schema_v1_major.json \
    data/events_schema_v1_major_report.json \
    data/reader-safe/news-desk-money-v02.json \
    data/reader-safe/news-desk-viral-v02.json \
    data/reader-safe/news-desk-status-v02.json \
    data/reader-safe/national-map-events-v03.geojson \
    data/reader-safe/national-map-events-v03-status.json \
    data/reports/discovery_approved_dedupe_report.json \
    data/reports/discovery_shared_cems_occurrence_dedupe_report.json \
    data/civic_*.json \
    data/photographer_assignment_calendar_*.json \
    data/photographer_money_day_*.json \
    data/photographer_viral_recurrence_*.json \
    data/photographer_shoot_day_certified_*.json \
    data/pin_integrity_*.json \
    data/nyc_permits_historical_*.json \
    data/sapo_foil_operator_index.json \
    data/daily_people_facing_sync_report.json \
    data/events_discovery_godview_digest_v02.json \
    data/events_schema_v1_civic_*.json \
    data/schema-v1-civic-review \
    status/nycif-daily-data-health.json \
    status/nycif-field-desk-overlay-health.json \
    status/nycif-last-known-good-feed.json \
    status/nycif-godview-project-state-v02.json \
    status/nycif-github-tracker.json \
    status/nycif-project-status.json \
    status/nycif-live-pipeline-dashboard.json \
    data/reports/godview_project_state_report.json \
    docs/events-discovery-taxonomy-v02.md \
    docs/field-desk-map-deploy

  if git diff --cached --quiet; then
    echo "No source or public feed changes to commit."
    rm -f "$FAILURE_JSON" "$FAILURE_LEGACY"
    exit 0
  fi

  CURRENT_STAGE="commit_ready_transaction"
  CURRENT_COMMAND_ID="git_commit_ready_transaction"
  git commit -m "Refresh READY complete News Desk runtime"

  CURRENT_STAGE="push_ready_transaction"
  CURRENT_COMMAND_ID="git_push_ready_transaction"
  if git push origin HEAD:main; then
    rm -f "$FAILURE_JSON" "$FAILURE_LEGACY"
    echo "Pushed READY complete daily runtime on attempt ${attempt}."
    exit 0
  fi

  rm -f "$FAILURE_JSON" "$FAILURE_LEGACY"
  echo "Push rejected because main advanced; rebuilding the full transaction (attempt ${attempt} of 3)."
  sleep $((attempt * 10))
done

CURRENT_STAGE="push_retry_exhausted"
CURRENT_COMMAND_ID="git_push_retry_exhausted"
NYCIF_FAILURE_STAGE="$CURRENT_STAGE" \
NYCIF_FAILURE_COMMAND_ID="$CURRENT_COMMAND_ID" \
  python - <<'PY'
import os
from scripts import daily_refresh_state as state
from scripts.run_daily_refresh_stage import failure_payload

payload = failure_payload(
    stage=os.environ["NYCIF_FAILURE_STAGE"],
    command_id=os.environ["NYCIF_FAILURE_COMMAND_ID"],
    exit_code=1,
    exception_class="PushRetryExhausted",
    error_summary="Could not push a READY daily feed after three complete rebuild attempts; main remained unchanged.",
    public_feed_commit_occurred=False,
)
state.atomic_write_failure(payload)
PY
printf '%s\n%s\n%s\n%s\n' "$CURRENT_STAGE" "1" "not_available" "$CURRENT_COMMAND_ID" > "$FAILURE_LEGACY"
echo "::error::Could not push a READY daily feed after 3 attempts; main remained unchanged."
exit 1