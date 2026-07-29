#!/usr/bin/env python3
"""Normalize and enforce strict discovery reconciliation.

The projector historically retained a weaker disposition-only pass when source
occurrences remained unaccounted. This gate distinguishes documented human
rejections and exact duplicate source rows from a true unexplained gap, then
requires the remaining unexplained gap to be zero.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECON = ROOT / "data" / "events_discovery_reconciliation_v02.json"
AUDIT = ROOT / "data" / "events_discovery_taxonomy_v02_audit.json"
SUPPLEMENTAL_REPORT = ROOT / "data" / "official_supplemental_occurrence_refresh_report.json"


def main() -> int:
    reconciliation = json.loads(RECON.read_text(encoding="utf-8"))
    supplemental = json.loads(SUPPLEMENTAL_REPORT.read_text(encoding="utf-8"))
    equations = reconciliation.get("equations") or {}
    disposition_ok = bool(equations.get("accepted_equals_disposition_sum"))

    raw_gap = int(equations.get("calendar_parks_unaccounted_gap") or 0)
    human_rejected = int(supplemental.get("human_rejected") or 0)
    exact_duplicates = int(supplemental.get("duplicate_exact_occurrences_collapsed") or 0)
    invalid = int(supplemental.get("invalid_missing_identity") or 0)
    unexpected_canceled = int(supplemental.get("unexpected_canceled_rows") or 0)
    documented_exclusions = human_rejected + exact_duplicates
    unexplained_gap = max(0, raw_gap - documented_exclusions)

    source_intake_clean = bool(supplemental.get("qa_pass")) and invalid == 0 and unexpected_canceled == 0
    strict = disposition_ok and source_intake_clean and unexplained_gap == 0

    equations["calendar_parks_unaccounted_gap_raw"] = raw_gap
    equations["calendar_parks_documented_human_rejected"] = human_rejected
    equations["calendar_parks_exact_duplicate_rows_excluded"] = exact_duplicates
    equations["calendar_parks_documented_exclusions"] = documented_exclusions
    equations["calendar_parks_unaccounted_gap"] = unexplained_gap
    reconciliation["equations"] = equations
    reconciliation["reconciles_disposition_layer"] = disposition_ok
    reconciliation["reconciles_strict"] = strict
    reconciliation["reconciles"] = strict
    reconciliation["strict_gate_reason"] = (
        "all source occurrences accepted or explicitly dispositioned; disposition equation balanced"
        if strict
        else (
            f"disposition_ok={disposition_ok}; source_intake_clean={source_intake_clean}; "
            f"raw_gap={raw_gap}; documented_exclusions={documented_exclusions}; "
            f"unexplained_gap={unexplained_gap}"
        )
    )
    RECON.write_text(
        json.dumps(reconciliation, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    audit["strict_reconciliation_pass"] = strict
    audit["strict_reconciliation"] = {
        "raw_calendar_parks_gap": raw_gap,
        "documented_human_rejected": human_rejected,
        "exact_duplicate_rows_excluded": exact_duplicates,
        "unexplained_gap": unexplained_gap,
        "source_intake_clean": source_intake_clean,
    }
    audit["qa_pass"] = bool(audit.get("qa_pass")) and strict
    AUDIT.write_text(
        json.dumps(audit, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "strict_reconciliation": strict,
                "raw_gap": raw_gap,
                "documented_exclusions": documented_exclusions,
                "unexplained_gap": unexplained_gap,
            },
            indent=2,
        )
    )
    return 0 if strict else 1


if __name__ == "__main__":
    sys.exit(main())
