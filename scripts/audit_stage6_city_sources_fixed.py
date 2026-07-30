#!/usr/bin/env python3
"""Corrected Stage 6 shadow-audit entry point.

The approved manifest stores page files under an `approved/pages/` directory.
The first audit entry point looked beside the manifest, which silently indexed
zero approved occurrences. This wrapper corrects page resolution, fails closed
when an approved manifest has rows but no rows were indexed, and delegates the
rest of the reviewed audit logic unchanged.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "nycif_stage6_audit",
    HERE / "audit_stage6_city_sources.py",
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Could not load audit_stage6_city_sources.py")
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


def approved_events() -> list[dict[str, Any]]:
    manifest = audit.load_json(audit.APPROVED_MANIFEST, {})
    rows: list[dict[str, Any]] = []
    pages = manifest.get("pages", []) if isinstance(manifest, dict) else []
    for page in pages:
        name = page.get("page") if isinstance(page, dict) else page
        if not name:
            continue
        candidates = [
            audit.APPROVED_MANIFEST.parent / "pages" / str(name),
            audit.APPROVED_MANIFEST.parent / str(name),
        ]
        page_path = next((path for path in candidates if path.exists()), None)
        if page_path is None:
            raise RuntimeError(f"approved manifest page is missing: {name}")
        payload = audit.load_json(page_path, {})
        if isinstance(payload, list):
            rows.extend(item for item in payload if isinstance(item, dict))
        elif isinstance(payload, dict):
            rows.extend(item for item in payload.get("events", []) if isinstance(item, dict))

    expected_total = int(manifest.get("total") or 0) if isinstance(manifest, dict) else 0
    if expected_total and not rows:
        raise RuntimeError(
            f"approved manifest reports {expected_total} events but the audit indexed zero"
        )
    if expected_total and len(rows) != expected_total:
        raise RuntimeError(
            f"approved manifest/index mismatch: expected {expected_total}, indexed {len(rows)}"
        )
    return rows


audit.approved_events = approved_events

if __name__ == "__main__":
    raise SystemExit(audit.main())
