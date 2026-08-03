from __future__ import annotations
from typing import Any
from .dpr_structures_resolver import resolve_dpr_structure
from .library_resolver import resolve_library
from .school_resolver import resolve_school
from .pool_resolver import resolve_pool
from .recreation_center_resolver import resolve_recreation_center
from .dcp_facilities_resolver import cross_check_dcp_facility

RESOLVERS = (
    ("dpr_structures", resolve_dpr_structure),
    ("libraries", resolve_library),
    ("schools", resolve_school),
    ("pools", resolve_pool),
    ("recreation_centers", resolve_recreation_center),
)

def resolve_authoritative_facility(record: dict[str, Any]):
    for resolver_name, resolver in RESOLVERS:
        result = resolver(record)
        if result:
            result = dict(result)
            result["facility_resolver"] = resolver_name
            checked = cross_check_dcp_facility(record, result)
            return checked if checked is not None else result
    return None
