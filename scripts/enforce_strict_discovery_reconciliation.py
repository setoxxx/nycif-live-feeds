#!/usr/bin/env python3
"""Normalize and enforce strict discovery reconciliation.

The projector historically retained a weaker disposition-only pass when source
occurrences remained unaccounted. This gate makes the strict equation canonical
and exits nonzero unless both the disposition sum and Calendar/Parks occurrence
coverage are complete.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECON = ROOT / "data" / "events_discovery_reconciliation_v02.json"
AUDIT = ROOT / "data" / "events_discovery_taxonomy_v02_audit.json"


def main() -> int:
    reconciliation = json.loads(RECON.read_text(encoding="utf-8"))
    equations = reconciliation.get("equations") or {}
    disposition_ok = bool(equations.get("accepted_equals_disposition_sum"))
    gap = int(equations.get("calendar_parks_unaccounted_gap") or 0)
    strict = disposition_ok and gap == 0

    reconciliation["reconciles_disposition_layer"] = disposition_ok
    reconciliation["reconciles_strict"] = strict
    reconciliation["reconciles"] = strict
    reconciliation["strict_gate_reason"] = (
        "all source occurrences accounted and disposition equation balanced"
        if strict
        else f"disposition_ok={disposition_ok}; calendar_parks_unaccounted_gap={gap}"
    )
    RECON.write_text(
        json.dumps(reconciliation, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    audit["strict_reconciliation_pass"] = strict
    audit["qa_pass"] = bool(audit.get("qa_pass")) and strict
    AUDIT.write_text(
        json.dumps(audit, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(json.dumps({"strict_reconciliation": strict, "calendar_parks_unaccounted_gap": gap}, indent=2))
    return 0 if strict else 1


if __name__ == "__main__":
    sys.exit(main())
