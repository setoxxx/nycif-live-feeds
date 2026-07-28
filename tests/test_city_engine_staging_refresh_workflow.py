from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "city-engine-staging-refresh.yml"


def test_refresh_workflow_is_artifact_only_and_read_only():
    text = WORKFLOW.read_text(encoding="utf-8")

    required = (
        "permissions:\n  contents: read",
        "workflow_dispatch:",
        "allow_live_fetch:",
        "scripts/sync_nyc_open_data.py",
        "scripts/build_test_enriched_feed.py",
        "scripts/build_staged_production_feed.py",
        "scripts/build_city_engine_staging_feed.py",
        "public_authorized\"] is False",
        "public_display_eligible\"] is False",
        "staging_display_eligible\"] is True",
        "actions/upload-artifact@v4",
        "retention-days: 7",
        "cancel-in-progress: true",
    )
    for value in required:
        assert value in text

    forbidden = (
        "git push",
        "git commit",
        "send_live_delta_email.py",
        "wpcom",
        "wordpress.com",
        "actions/deploy-pages",
        "peaceiris/actions-gh-pages",
        "contents: write",
    )
    lowered = text.lower()
    for value in forbidden:
        assert value.lower() not in lowered


def test_refresh_workflow_requires_explicit_manual_live_fetch():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "default: \"no\"" in text
    assert "github.event.inputs.allow_live_fetch == 'yes'" in text
