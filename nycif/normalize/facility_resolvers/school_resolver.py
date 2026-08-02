from __future__ import annotations
import re
from pathlib import Path
from typing import Any
from .base import candidate_phrases, resolve_exact

LOOKUP = Path(__file__).resolve().parents[3] / "data" / "doe_school_centroids.json"
TERM_RE = re.compile(r"\b(?:school|academy|p\.s\.|i\.s\.|m\.s\.|high school)\b", re.I)
SUFFIXES = (r"school", r"academy", r"p\.s\.\s*\d+", r"i\.s\.\s*\d+", r"m\.s\.\s*\d+")

def resolve_school(record: dict[str, Any], *, lookup_path: Path = LOOKUP):
    text = str(record.get("location") or record.get("display_location") or "")
    if not TERM_RE.search(text):
        return None
    return resolve_exact(record, lookup_path=lookup_path, candidates=candidate_phrases(text, suffixes=SUFFIXES), coordinate_source="doe_school_points_centroid", accepted_types={"school"})
