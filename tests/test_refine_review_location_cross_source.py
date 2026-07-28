from __future__ import annotations

from scripts.refine_review_location_cross_source import refine_payload


def approved_event(
    event_id: str,
    *,
    title: str,
    date: str,
    location: str,
    borough: str,
    latitude: float,
    longitude: float,
):
    return {
        "id": event_id,
        "title": title,
        "location": location,
        "borough": borough,
        "latitude": latitude,
        "longitude": longitude,
        "nycif": {"event_date": date},
    }


def unresolved(
    event_id: str,
    *,
    title: str,
    date: str,
    location: str,
):
    return {
        "canonical_id": event_id,
        "title": title,
        "date": date,
        "location": location,
        "disposition": "unresolved",
        "location_classified": True,
        "pin_eligible": False,
        "promotion_allowed": False,
        "public_map_modified": False,
    }


def run(proposals, approved):
    report = {
        "target_null_borough_count": len(proposals),
        "source_generated_at_utc": "2026-07-28T12:25:24Z",
        "safety": {
            "public_map_modified": False,
            "production_feed_modified": False,
            "location_cache_modified": False,
            "wordpress_modified": False,
            "promotion_allowed": False,
            "proposal_only": True,
        },
    }
    payload = {"target_count": len(proposals), "proposals": proposals}
    return refine_payload(
        report,
        payload,
        approved,
        approved_generated_at_utc="2026-07-28T12:25:24Z",
    )


def test_exact_title_date_and_little_bay_location_resolves():
    proposal = unresolved(
        "calendar:1",
        title="Silent Disco On The Bay",
        date="2026-07-24",
        location="Little Bay Park - Parking lot, lot under the bridge.",
    )
    approved = [
        approved_event(
            "parks:1",
            title="Silent Disco On The Bay",
            date="2026-07-24",
            location="Little Bay Park",
            borough="Queens",
            latitude=40.7896004,
            longitude=-73.7870026,
        )
    ]
    report, payload = run([proposal], approved)
    result = payload["proposals"][0]
    assert result["disposition"] == "mapped_from_cross_source_event_evidence"
    assert result["proposed_borough"] == "Queens"
    assert report["unresolved_count"] == 0


def test_generic_same_title_uses_location_tokens_to_choose_st_james():
    proposal = unresolved(
        "calendar:yoga",
        title="Yoga",
        date="2026-07-18",
        location="Multi-Use Room in St. James Recreation Center",
    )
    approved = [
        approved_event(
            "parks:st-james",
            title="Yoga",
            date="2026-07-18",
            location="Multi-Use Room (in St. James Park)",
            borough="Bronx",
            latitude=40.8647713,
            longitude=-73.8992192,
        ),
        approved_event(
            "parks:pelham",
            title="Yoga",
            date="2026-07-18",
            location="Tennis Courts (in Pelham Bay Park)",
            borough="Bronx",
            latitude=40.8498479,
            longitude=-73.8253550,
        ),
    ]
    _, payload = run([proposal], approved)
    result = payload["proposals"][0]
    assert result["disposition"] == "mapped_from_cross_source_event_evidence"
    assert result["cross_source_evidence_ids"] == ["parks:st-james"]
    assert result["proposed_longitude"] == -73.8992192


def test_exact_location_propagates_to_recurring_date_after_first_match():
    first = unresolved(
        "calendar:yoga-1",
        title="Yoga",
        date="2026-07-18",
        location="Multi-Use Room in St. James Recreation Center",
    )
    recurring = unresolved(
        "calendar:yoga-2",
        title="Yoga",
        date="2026-08-01",
        location="Multi-Use Room in St. James Recreation Center",
    )
    approved = [
        approved_event(
            "parks:st-james",
            title="Yoga",
            date="2026-07-18",
            location="Multi-Use Room (in St. James Park)",
            borough="Bronx",
            latitude=40.8647713,
            longitude=-73.8992192,
        )
    ]
    report, payload = run([first, recurring], approved)
    results = {item["canonical_id"]: item for item in payload["proposals"]}
    assert results["calendar:yoga-1"]["disposition"] == "mapped_from_cross_source_event_evidence"
    assert results["calendar:yoga-2"]["disposition"] == "mapped_from_cross_source_location_evidence"
    assert report["unresolved_count"] == 0


def test_ambiguous_same_title_date_cross_borough_cluster_stays_unresolved():
    proposal = unresolved(
        "calendar:event",
        title="Community Event",
        date="2026-07-18",
        location="Central Field",
    )
    approved = [
        approved_event(
            "approved:1",
            title="Community Event",
            date="2026-07-18",
            location="Central Field",
            borough="Brooklyn",
            latitude=40.65,
            longitude=-73.95,
        ),
        approved_event(
            "approved:2",
            title="Community Event",
            date="2026-07-18",
            location="Central Field",
            borough="Queens",
            latitude=40.75,
            longitude=-73.85,
        ),
    ]
    report, payload = run([proposal], approved)
    assert payload["proposals"][0]["disposition"] == "unresolved"
    assert report["unresolved_count"] == 1
