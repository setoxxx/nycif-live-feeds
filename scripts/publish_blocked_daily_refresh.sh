#!/usr/bin/env bash
# Publish only operator health after a failed refresh; never publish partial feeds.
set -euo pipefail

RUNTIME_DIR="${NYCIF_RUNTIME_DIR:-.runtime}"
FAILURE_JSON="$RUNTIME_DIR/nycif-daily-failure.json"
FAILURE_LEGACY="$RUNTIME_DIR/nycif-daily-failure"
PREVIOUS_POINTER="$RUNTIME_DIR/nycif-previous-public-feed"
umask 077
install -d -m 700 "$RUNTIME_DIR"

stage="platform_or_uninstrumented_failure"
command_id="workflow_platform_or_uninstrumented"
code="1"
line="not_available"
exception_class="WorkflowStepFailure"
error_summary="No structured failure context was captured. Review the GitHub Actions job log."

if [ -f "$FAILURE_LEGACY" ]; then
  legacy_stage="$(sed -n '1p' "$FAILURE_LEGACY")"
  legacy_code="$(sed -n '2p' "$FAILURE_LEGACY")"
  legacy_line="$(sed -n '3p' "$FAILURE_LEGACY")"
  legacy_command="$(sed -n '4p' "$FAILURE_LEGACY")"
  if [ -n "$legacy_stage" ] && [ "$legacy_stage" != "unknown_stage" ]; then
    stage="$legacy_stage"
  fi
  if [[ "$legacy_code" =~ ^[0-9]+$ ]]; then
    code="$legacy_code"
  fi
  if [ -n "$legacy_line" ]; then
    line="$legacy_line"
  fi
  if [ -n "$legacy_command" ]; then
    command_id="$legacy_command"
  fi
fi

previous="$(cat "$PREVIOUS_POINTER" 2>/dev/null || true)"

git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git fetch origin main
remote="$(git rev-parse origin/main)"

if [ -n "$previous" ] && [ "$remote" != "$previous" ]; then
  echo "Main advanced from $previous to $remote; a newer transaction owns current health. Skipping stale BLOCKED status."
  exit 0
fi

git reset --hard origin/main
if [ -z "$previous" ]; then
  previous="$remote"
fi

report_args=(
  --stage "$stage"
  --command-id "$command_id"
  --exit-code "$code"
  --line "$line"
  --exception-class "$exception_class"
  --error-summary "$error_summary"
  --previous-commit "$previous"
)
python scripts/record_blocked_daily_data_health.py "${report_args[@]}"
python scripts/generate_godview_project_state.py --fetch-github || true
PREVIOUS_PUBLIC_FEED_SHA="$previous" python scripts/apply_daily_data_health_to_godview.py || true

git add \
  status/nycif-daily-data-health.json \
  status/nycif-field-desk-overlay-health.json \
  status/nycif-godview-project-state-v02.json \
  status/nycif-github-tracker.json \
  status/nycif-project-status.json \
  status/nycif-live-pipeline-dashboard.json \
  data/reports/godview_project_state_report.json

if git diff --cached --quiet; then
  echo "BLOCKED status is already current."
  exit 0
fi

git commit -m "Record BLOCKED News Desk refresh at ${stage}"
git push origin HEAD:main
