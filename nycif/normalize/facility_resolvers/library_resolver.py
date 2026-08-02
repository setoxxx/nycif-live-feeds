from __future__ import annotations
import re
from pathlib import Path
from typing import Any
from .base import candidate_phrases, resolve_exact

LOOKUP = Path(__file__).resolve().parents[3] / "data" / "library_branch_centroids.json"
TERM_RE = re.compile(r"\b(?:library|bpl|nypl|queens public library)\b", re.I)
SUFFIXES = (r"library", r"branch")
PREFIXES = (r"^(?:bpl|nypl|brooklyn public library|queens public library)\s*[-:]?\s*",)

def resolve_library(record: dict[str, Any], *, lookup_path: Path = LOOKUP):
    text = str(record.get("location") or record.get("display_location") or "")
    if not TERM_RE.search(text):
        return None
    candidates = candidate_phrases(text, suffixes=SUFFIXES, prefixes=PREFIXES)
    expanded = set(candidates)
    for value in candidates:
        core = re.sub(r"\b(?:library|branch)\b", "", value, flags=re.I).strip(" -")
        if core:
            expanded.update({core, f"{core} Library", f"{core} Branch"})
    return resolve_exact(record, lookup_path=lookup_path, candidates=expanded, coordinate_source="nyc_library_branches_centroid", accepted_types={"library"})
