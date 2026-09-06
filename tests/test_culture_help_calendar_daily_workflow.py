"""Safety contract for the daily Culture help-calendar GitHub Actions workflow."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "culture-help-calendar-daily.yml"
PLAN = ROOT / "docs" / "CULTURE_COMMUNITY_ENGINEERING_PLAN.md"


def test_daily_workflow_is_staging_only_and_fail_closed():
    text = WORKFLOW.read_text(encoding="utf-8")

    required = (
        'cron: "0 10 * * *"',
        "6:00 AM America/New_York",
        "EDT",
        "EST",
        "workflow_dispatch:",
        "permissions:\n  contents: read",
        "scripts/culture/pull_workforce1_events.py --live",
        "scripts/culture/pull_dol_career_events.py",
        "scripts/culture/pull_cuny_career_events.py",
        "scripts/culture/pull_nybc_blood_drives.py",
        "scripts/culture/pull_show_mobile_clinics.py",
        "scripts/culture/pull_aspca_mobile.py",
        "scripts/culture/validate_before_publish.py",
        "publication_allowed must stay false",
        "actions/upload-artifact@v4",
        "data/culture/staging/*.json",
        "data/culture/reports/*.json",
        "retention-days: 7",
        "scripts/culture/load_calendar_civic_staging.py",
        "--dataset calendar",
        "Gates were not written",
    )
    for value in required:
        assert value in text, f"missing {value!r}"

    forbidden = (
        "git push",
        "git commit",
        "contents: write",
        "supabase db",
        "supabase functions deploy",
        "wpcom",
        "wordpress.com",
        "actions/deploy-pages",
        "peaceiris/actions-gh-pages",
        "business_publication_enabled: true",
        "help_calendar_publication_enabled: true",
        "calendar_publication_enabled: true",
        "civic_publication_enabled: true",
        "publication_allowed=true",
        "websockets",
        "realtime",
    )
    lowered = text.lower()
    for value in forbidden:
        assert value.lower() not in lowered, f"forbidden {value!r}"


def test_plan_documents_howard_approved_schedule():
    plan = PLAN.read_text(encoding="utf-8")
    assert "6:00 AM America/New_York" in plan
    assert "0 10 * * *" in plan
    assert "Workforce1" in plan
    assert "NYS DOL" in plan or "DOL" in plan
    assert "CUNY" in plan
    assert "NYBC" in plan
    assert "SHOW" in plan
    assert "ASPCA" in plan
    assert "weekly" in plan.lower()
    assert "NYPD" in plan
    assert "FDNY" in plan
    assert "2:00 PM" in plan
    assert "culture-help-calendar-daily.yml" in plan
