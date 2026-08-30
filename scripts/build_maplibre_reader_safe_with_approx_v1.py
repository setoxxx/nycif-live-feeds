#!/usr/bin/env python3
"""Compatibility wrapper for V3 reader-safe output plus approximate markers.

The exact V3 builder remains authoritative for certified marker geometry. This
wrapper only teaches its reader-list projection that ``approximate_marker`` is a
reader-visible disposition; those occurrences still enter V3 with null geometry
and are mapped separately by the approximate overlay.
"""
from __future__ import annotations

try:
    from scripts import build_maplibre_reader_safe_v03 as reader
except ModuleNotFoundError:  # pragma: no cover
    import build_maplibre_reader_safe_v03 as reader  # type: ignore[no-redef]

reader.READER_VISIBLE_DISPOSITIONS = set(reader.READER_VISIBLE_DISPOSITIONS) | {"approximate_marker"}

if __name__ == "__main__":
    raise SystemExit(reader.main())
