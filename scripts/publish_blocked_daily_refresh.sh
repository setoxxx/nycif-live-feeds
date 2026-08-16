#!/usr/bin/env bash
# Publish only operator health after a failed refresh; never publish partial feeds.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$REPO_ROOT"
umask 077

git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"

ATTEMPT="${NYCIF_BLOCKED_PUBLISH_ATTEMPT:-1}"
if [[ ! "$ATTEMPT" =~ ^[1-3]$ ]]; then
  echo "Invalid BLOCKED publication attempt: $ATTEMPT" >&2
  exit 2
fi

PINNED_SHA="${NYCIF_BLOCKED_PUBLISH_PINNED_SHA:-}"
if [ -z "$PINNED_SHA" ]; then
  git fetch origin main
  PINNED_SHA="$(git rev-parse FETCH_HEAD)"
  git reset --hard "$PINNED_SHA"
  exec env \
    NYCIF_BLOCKED_PUBLISH_PINNED_SHA="$PINNED_SHA" \
    NYCIF_BLOCKED_PUBLISH_ATTEMPT="$ATTEMPT" \
    bash scripts/publish_blocked_daily_refresh.sh
fi
if [ "$(git rev-parse HEAD)" != "$PINNED_SHA" ]; then
  echo "Pinned BLOCKED publisher SHA does not match the checked-out transaction." >&2
  exit 2
fi

stage="platform_or_uninstrumented_failure"
command_id="workflow_platform_or_uninstrumented"
code="1"
line="not_available"
exception_class="WorkflowStepFailure"
error_summary="No structured failure context was captured. Review the GitHub Actions job log."

pointer_verified=true
if previous="$(python - <<'PY'
from scripts import daily_refresh_state as state

try:
    commit_sha = state.read_previous_commit()
except (OSError, RuntimeError, ValueError) as exc:
    print(f"Unsafe previous-commit state: {exc}", file=__import__("sys").stderr)
    raise SystemExit(4)
if commit_sha is None:
    raise SystemExit(3)
print(commit_sha)
PY
)"; then
  :
else
  pointer_status="$?"
  previous="$PINNED_SHA"
  pointer_verified=false
  if [ "$pointer_status" -eq 3 ]; then
    echo "No previous transaction pointer was captured; publishing conservative BLOCKED health."
  else
    echo "Previous transaction pointer was invalid; publishing conservative BLOCKED health." >&2
  fi
fi

if [ "$pointer_verified" = true ]; then
  if ! git cat-file -e "${previous}^{commit}" 2>/dev/null ||
     ! git merge-base --is-ancestor "$previous" "$PINNED_SHA"; then
    echo "Previous transaction pointer is not a valid ancestor; treating publication state as unverified." >&2
    previous="$PINNED_SHA"
    pointer_verified=false
  elif [ "$previous" != "$PINNED_SHA" ]; then
    if ! git diff --quiet "$previous" "$PINNED_SHA" -- status/nycif-last-known-good-feed.json; then
      echo "A newer READY transaction changed the last-known-good marker; skipping stale BLOCKED status."
      exit 0
    fi
    echo "Main advanced without a newer READY marker; publishing BLOCKED health on $PINNED_SHA."
    previous="$PINNED_SHA"
  fi
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
if [ "$pointer_verified" != true ]; then
  report_args+=(--publication-state-unverified)
fi
python scripts/record_blocked_daily_data_health.py "${report_args[@]}"

companions=(
  status/nycif-field-desk-overlay-health.json
  status/nycif-godview-project-state-v02.json
  status/nycif-github-tracker.json
  status/nycif-project-status.json
  status/nycif-live-pipeline-dashboard.json
  data/reports/godview_project_state_report.json
)
companion_state=complete
if ! python scripts/generate_godview_project_state.py --fetch-github ||
   ! PREVIOUS_PUBLIC_FEED_SHA="$previous" python scripts/apply_daily_data_health_to_godview.py; then
  companion_state=restored_after_failure
  git restore --source="$PINNED_SHA" --staged --worktree -- "${companions[@]}"
  echo "::warning::God View companion generation failed; publishing authoritative BLOCKED health only."
fi

git add status/nycif-daily-data-health.json
if [ "$companion_state" = complete ]; then
  git add "${companions[@]}"
fi

while IFS= read -r changed_path; do
  [ -z "$changed_path" ] && continue
  allowed=false
  if [ "$changed_path" = "status/nycif-daily-data-health.json" ]; then
    allowed=true
  elif [ "$companion_state" = complete ]; then
    for companion in "${companions[@]}"; do
      if [ "$changed_path" = "$companion" ]; then
        allowed=true
        break
      fi
    done
  fi
  if [ "$allowed" != true ]; then
    echo "Unexpected staged BLOCKED artifact: $changed_path" >&2
    exit 1
  fi
done < <(git diff --cached --name-only)

if git diff --cached --quiet; then
  echo "BLOCKED status is already current."
  exit 0
fi

git commit -m "Record BLOCKED News Desk refresh at ${stage}"
if git push origin HEAD:main; then
  python - <<'PY'
from scripts import daily_refresh_state as state
state.clear_runtime_state()
PY
  exit 0
fi

if [ "$ATTEMPT" -ge 3 ]; then
  echo "::error::Could not publish BLOCKED health after 3 compare-and-swap attempts."
  exit 1
fi

next_attempt="$((ATTEMPT + 1))"
git fetch origin main
next_sha="$(git rev-parse FETCH_HEAD)"
git reset --hard "$next_sha"
exec env \
  NYCIF_BLOCKED_PUBLISH_PINNED_SHA="$next_sha" \
  NYCIF_BLOCKED_PUBLISH_ATTEMPT="$next_attempt" \
  bash scripts/publish_blocked_daily_refresh.sh

