#!/usr/bin/env python3
"""Run official LION line/node resolution with a fail-soft transport boundary.

The current official LION line layer provides street names and endpoint NodeIDs;
the current LION node layer provides endpoint geometry. This wrapper uses the
existing normalized POST transport and records a pass-through audit artifact if
the external ArcGIS service is temporarily unavailable. A service outage never
fabricates a coordinate and never blocks the broader location-classification
audit.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

try:
    from scripts import run_review_locations_from_lion as transport
    from scripts.resolve_remaining_review_locations import load_boundaries
    from scripts.schema_v1_common import utc_now
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    import run_review_locations_from_lion as transport
    from resolve_remaining_review_locations import load_boundaries
    from schema_v1_common import utc_now

# Pin the currently published official DCP services. The transport uses form POST
# to avoid query-string length rejection.
transport.lion.LION_LINE_URL = (
    "https://services5.arcgis.com/GfwWNkhOj9bNBqoJ/arcgis/rest/services/"
    "LION/FeatureServer/0/query"
)
transport.lion.LION_NODE_URL = (
    "https://services5.arcgis.com/GfwWNkhOj9bNBqoJ/arcgis/rest/services/"
    "LION_Node/FeatureServer/0/query"
)
transport.lion.LION_LAYER_URL = (
    "https://services5.arcgis.com/GfwWNkhOj9bNBqoJ/arcgis/rest/services/"
    "LION/FeatureServer/0"
)
transport.lion.LION_NODE_LAYER_URL = (
    "https://services5.arcgis.com/GfwWNkhOj9bNBqoJ/arcgis/rest/services/"
    "LION_Node/FeatureServer/0"
)


def pass_through(
    report: dict[str, Any],
    payload: dict[str, Any],
    *,
    error: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    proposals = [dict(item) for item in payload.get("proposals") or [] if isinstance(item, dict)]
    counts = Counter(str(item.get("disposition") or "missing_disposition") for item in proposals)
    target = int(report.get("target_null_borough_count") or len(proposals))
    unresolved = counts.get("unresolved", 0)
    final_report = dict(report)
    final_report.update(
        {
            "artifact_type": "review_location_coverage_audit_lion_line_fail_soft",
            "generated_at_utc": utc_now(),
            "accounted_count": len(proposals),
            "location_classified_count": sum(1 for item in proposals if item.get("location_classified") is True),
            "location_classified_pct": round((len(proposals) / target * 100.0), 4) if target else 100.0,
            "disposition_counts": dict(sorted(counts.items())),
            "unresolved_count": unresolved,
            "zero_silent_null_borough_records": len(proposals) == target,
            "qa_pass": len(proposals) == target and all(item.get("disposition") for item in proposals),
            "lion_line_resolution": {
                "method": "nyc_dcp_lion_line_shared_node_midpoint_v1",
                "line_layer_url": transport.lion.LION_LAYER_URL,
                "node_layer_url": transport.lion.LION_NODE_LAYER_URL,
                "service_available": False,
                "service_error": error,
                "unresolved_before": unresolved,
                "unresolved_after": unresolved,
                "newly_resolved_count": 0,
            },
        }
    )
    final_payload = dict(payload)
    final_payload.update(
        {
            "artifact_type": "review_location_resolution_proposals_lion_line_fail_soft",
            "generated_at_utc": final_report["generated_at_utc"],
            "target_count": target,
            "proposals": proposals,
        }
    )
    return final_report, final_payload


def resolve_resilient(
    report: dict[str, Any],
    payload: dict[str, Any],
    *,
    boundaries: list[tuple[str, dict[str, Any]]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        final_report, final_payload = transport.lion.resolve_payload(
            report,
            payload,
            boundaries=boundaries,
        )
    except RuntimeError as exc:
        return pass_through(report, payload, error=str(exc))

    line_details = dict(final_report.pop("lion_resolution", {}))
    line_details["service_available"] = True
    final_report["artifact_type"] = "review_location_coverage_audit_lion_line"
    final_report["lion_line_resolution"] = line_details
    final_payload["artifact_type"] = "review_location_resolution_proposals_lion_line"
    return final_report, final_payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-report", type=Path, required=True)
    parser.add_argument("--input-proposals", type=Path, required=True)
    parser.add_argument("--borough-boundaries", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--proposals", type=Path, required=True)
    args = parser.parse_args()

    report = json.loads(args.input_report.read_text(encoding="utf-8"))
    payload = json.loads(args.input_proposals.read_text(encoding="utf-8"))
    boundaries = load_boundaries(args.borough_boundaries)
    final_report, final_payload = resolve_resilient(
        report,
        payload,
        boundaries=boundaries,
    )
    write_json(args.report, final_report)
    write_json(args.proposals, final_payload)
    print(json.dumps(final_report, indent=2, sort_keys=True))
    return 0 if final_report["qa_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
