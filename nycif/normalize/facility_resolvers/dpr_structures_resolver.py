from __future__ import annotations
import re
from pathlib import Path
from typing import Any
from .base import candidate_phrases, resolve_exact

LOOKUP = Path(__file__).resolve().parents[3] / "data" / "dpr_structures_centroids.json"
TERM_RE = re.compile(r"\b(?:recreation center|rec center|nature center|visitor center|audubon center|boathouse|field house|community room|garden)\b", re.I)
SUFFIXES = (r"recreation\s+center", r"rec\s+center", r"nature\s+center", r"visitor\s+center", r"audubon\s+center", r"boathouse", r"field\s+house", r"community\s+room", r"garden")

def resolve_dpr_structure(record: dict[str, Any], *, lookup_path: Path = LOOKUP):
    text = str(record.get("location") or record.get("display_location") or "")
    if not TERM_RE.search(text):
        return None
    candidates = candidate_phrases(text, suffixes=SUFFIXES, prefixes=(r"^(?:dance room|gymnasium(?: \(court\))?|multi-use room(?: b)?|multipurpose room|outdoors)\s+(?:in|at)\s+",))
    return resolve_exact(record, lookup_path=lookup_path, candidates=candidates, coordinate_source="dpr_parks_structures_centroid")
