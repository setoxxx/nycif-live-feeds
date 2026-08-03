from __future__ import annotations
from pathlib import Path
from typing import Any
from .dpr_structures_resolver import resolve_dpr_structure, LOOKUP


def resolve_recreation_center(record: dict[str, Any], *, lookup_path: Path = LOOKUP):
    resolved = resolve_dpr_structure(record, lookup_path=lookup_path)
    if not resolved:
        return None
    if resolved.get("facility_type") not in {"recreation_center", "nature_center", "visitor_center", "boathouse", "field_house", "park_structure"}:
        return None
    return resolved
