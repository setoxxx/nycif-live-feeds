#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.supplemental_discovery_merge import (  # noqa: E402
    fold_approved_supplemental_export,
    identity_key,
    is_merge_authorized,
)


class SupplementalDiscoveryMergeTests(unittest.TestCase):
    def test_identity_key(self) -> None:
        key = identity_key("NYC-Parks", " 42 ", "2026-07-16T12:00:00")
        self.assertEqual(key, ("nyc-parks", "42", "2026-07-16"))

    def test_fold_skips_when_not_authorized(self) -> None:
        approved = [{"id": "a", "source": {"dataset": "x", "source_event_id": "1"}, "nycif": {"event_date": "2026-07-16"}}]
        def fake_build(*_a, **_k):
            return {"id": "new"}

        out, stats = fold_approved_supplemental_export(approved, build_base_event=fake_build, authorized=False)
        self.assertEqual(out, approved)
        self.assertFalse(stats["authorized"])
        self.assertEqual(stats["merged"], 0)

    def test_merge_authorized_from_status(self) -> None:
        self.assertTrue(is_merge_authorized())


if __name__ == "__main__":
    unittest.main()
