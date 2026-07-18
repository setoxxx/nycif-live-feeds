"""Offline assertions on supplemental M11 CI wiring in live-sync-qa.yml."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LIVE_SYNC_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "live-sync-qa.yml"


def _text() -> str:
    return LIVE_SYNC_WORKFLOW.read_text(encoding="utf-8")


def _step_order(text: str, *step_names: str) -> list[int]:
    lines = text.splitlines()
    indices: dict[str, int] = {}
    for name in step_names:
        marker = f"- name: {name}"
        for i, line in enumerate(lines):
            if line.strip() == marker:
                indices[name] = i
                break
        assert name in indices, f"step {name!r} not found"
    return [indices[name] for name in step_names]


def test_supplemental_memory_build_precedes_staging_feed():
    text = _text()
    memory_idx, staging_idx = _step_order(
        text,
        "Build supplemental location memory from approved queue (M11)",
        "Build supplemental events staging feed",
    )
    assert memory_idx < staging_idx


def test_incremental_intake_precedes_publish_export():
    text = _text()
    intake_idx, publish_idx = _step_order(
        text,
        "Incremental supplemental intake (M11)",
        "Publish supplemental approved export for field-desk preview",
    )
    assert intake_idx < publish_idx


def test_preview_enrichment_build_steps_in_publish_block():
    text = _text()
    assert "build_nypd_precinct_boundaries_reference.py" in text
    assert "build_supplemental_cultural_anniversary_staging.py" in text
    assert "build_supplemental_press_geofence_staging.py" in text
    publish_marker = "- name: Publish supplemental approved export for field-desk preview"
    publish_idx = text.index(publish_marker)
    block = text[publish_idx:publish_idx + 500]
    assert "build_supplemental_cultural_anniversary_staging.py" in block
    assert "publish_supplemental_approved_export_feed.py" in block


def test_destructive_queue_builder_not_in_workflow():
    text = _text()
    assert "build_supplemental_manual_approval_queue.py" not in text


def test_net_new_review_gated_on_pending_count():
    text = _text()
    assert "Net-new supplemental review when pending rows exist (M11)" in text
    assert "apply_supplemental_net_new_live_sync_review.py" in text
    assert 'if [ "$pending" -gt 0 ]; then' in text


def test_incremental_intake_still_present():
    assert "incremental_supplemental_intake.py" in _text()


def test_phase2e_dry_run_and_readiness_gate_in_workflow():
    text = _text()
    assert "Supplemental Phase 2E promotion dry-run (M11)" in text
    assert "dry_run_supplemental_phase2e_promotion.py" in text
    assert "verify_supplemental_phase2e_readiness.py" in text
    publish_idx, dry_run_idx, gate_idx = _step_order(
        text,
        "Publish supplemental approved export for field-desk preview",
        "Supplemental Phase 2E promotion dry-run (M11)",
        "Enforce supplemental Phase 2E readiness gate",
    )
    assert publish_idx < dry_run_idx < gate_idx


def test_supplemental_preview_deploy_workflow_exists():
    text = (REPO_ROOT / ".github/workflows/field-desk-supplemental-preview-deploy.yml").read_text(encoding="utf-8")
    assert "FIELD_DESK_DEPLOY_TOKEN" in text
    assert "supplemental-export-preview" in text
    assert "deploy_supplemental_preview_to_field_desk.sh" in text
    assert "supplemental_cultural_anniversary_staging.json" in text
