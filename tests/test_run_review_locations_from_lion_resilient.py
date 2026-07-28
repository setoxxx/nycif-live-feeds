from __future__ import annotations

from scripts import run_review_locations_from_lion_resilient as resilient


def report():
    return {
        "target_null_borough_count": 1,
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


def payload():
    return {
        "target_count": 1,
        "proposals": [
            {
                "canonical_id": "calendar:test",
                "title": "Test",
                "location": "WEST 48 STREET between 6 AVENUE and 7 AVENUE Manhattan",
                "disposition": "unresolved",
                "location_classified": True,
                "pin_eligible": False,
                "promotion_allowed": False,
                "public_map_modified": False,
            }
        ],
    }


def test_service_failure_is_fail_soft(monkeypatch):
    def fail(*_args, **_kwargs):
        raise RuntimeError("temporary ArcGIS redeployment")

    monkeypatch.setattr(resilient.transport.lion, "resolve_payload", fail)
    final_report, final_payload = resilient.resolve_resilient(
        report(),
        payload(),
        boundaries=[],
    )
    assert final_report["qa_pass"] is True
    assert final_report["unresolved_count"] == 1
    assert final_report["lion_line_resolution"]["service_available"] is False
    assert "temporary ArcGIS redeployment" in final_report["lion_line_resolution"]["service_error"]
    assert final_payload["proposals"][0]["disposition"] == "unresolved"


def test_successful_line_resolution_is_preserved_and_renamed(monkeypatch):
    resolved_payload = payload()
    resolved_payload["proposals"][0] = {
        **resolved_payload["proposals"][0],
        "disposition": "mapped_from_nyc_lion_nodes",
        "proposed_borough": "Manhattan",
        "proposed_latitude": 40.759,
        "proposed_longitude": -73.982,
        "pin_eligible": True,
    }

    def succeed(_report, _payload, *, boundaries):
        assert boundaries == [("Manhattan", {})]
        return (
            {
                **report(),
                "artifact_type": "review_location_coverage_audit_lion",
                "accounted_count": 1,
                "location_classified_count": 1,
                "location_classified_pct": 100.0,
                "disposition_counts": {"mapped_from_nyc_lion_nodes": 1},
                "unresolved_count": 0,
                "zero_silent_null_borough_records": True,
                "qa_pass": True,
                "lion_resolution": {
                    "method": "nyc_dcp_lion_shared_node_midpoint_v1",
                    "unresolved_before": 1,
                    "unresolved_after": 0,
                    "newly_resolved_count": 1,
                },
            },
            resolved_payload,
        )

    monkeypatch.setattr(resilient.transport.lion, "resolve_payload", succeed)
    final_report, final_payload = resilient.resolve_resilient(
        report(),
        payload(),
        boundaries=[("Manhattan", {})],
    )
    assert final_report["unresolved_count"] == 0
    assert "lion_resolution" not in final_report
    assert final_report["lion_line_resolution"]["newly_resolved_count"] == 1
    assert final_report["lion_line_resolution"]["service_available"] is True
    assert final_payload["proposals"][0]["pin_eligible"] is True
