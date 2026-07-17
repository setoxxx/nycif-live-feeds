"""Tests for supplemental location memory and gazetteer overlay."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_supplemental_location_memory import (  # noqa: E402
    build_overlay_index,
    location_key_for_row,
    memory_entry_to_gazetteer_keys,
)
from scripts.nyc_location_gazetteer import (  # noqa: E402
    NYCLocationGazetteer,
    gazetteer_entry,
    merge_gazetteer_indexes,
)


class SupplementalLocationMemoryTests(unittest.TestCase):
    def test_location_key_includes_parent_context(self) -> None:
        row = {
            "display_location": "Handball Court in Washington Square Park",
            "borough": "Mn",
            "proposed_lat": 40.731,
            "proposed_lng": -73.997,
        }
        key = location_key_for_row(row)
        self.assertIn("parent:", key)
        self.assertIn("washington square park", key)

    def test_overlay_merged_into_gazetteer_lookup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            base_path = tmp_path / "base_gazetteer.json"
            overlay_path = tmp_path / "overlay.json"
            base_path.write_text(
                json.dumps(
                    {
                        "artifact_type": "nyc_location_gazetteer",
                        "index": {},
                    }
                ),
                encoding="utf-8",
            )
            overlay_path.write_text(
                json.dumps(
                    {
                        "artifact_type": "supplemental_location_gazetteer_overlay",
                        "index": {
                            "mn|bryant park": gazetteer_entry(
                                lat=40.7536,
                                lng=-73.9832,
                                source="supplemental_location_memory",
                                confidence="high",
                                confidence_reason="approved supplemental memory",
                                label="Bryant Park",
                                borough="Mn",
                            )
                        },
                    }
                ),
                encoding="utf-8",
            )
            gazetteer = NYCLocationGazetteer.from_file(
                base_path,
                overlay_path=overlay_path,
                include_overlay=True,
            )
            hit = gazetteer.lookup_display("Bryant Park", "Mn")
            self.assertIsNotNone(hit)
            assert hit is not None
            self.assertEqual(hit["source"], "supplemental_location_memory")

    def test_memory_entry_generates_child_and_parent_keys(self) -> None:
        entry = {
            "display_location": "Dance Room in Shirley Chisholm Recreation Center",
            "borough": "Bk",
            "proposed_lat": 40.63811,
            "proposed_lng": -73.94706,
        }
        keys = memory_entry_to_gazetteer_keys(entry)
        self.assertTrue(any("shirley chisholm recreation center" in key for key in keys))
        self.assertTrue(any("dance room" in key for key in keys))

    def test_merge_prefers_higher_confidence_existing_entry(self) -> None:
        base = {
            "bk|test park": gazetteer_entry(
                lat=40.6,
                lng=-73.9,
                source="location_cache",
                confidence="high",
                confidence_reason="cache",
            )
        }
        overlay = {
            "bk|test park": gazetteer_entry(
                lat=40.61,
                lng=-73.91,
                source="supplemental_location_memory",
                confidence="medium",
                confidence_reason="memory",
            )
        }
        merged = merge_gazetteer_indexes(base, overlay)
        self.assertEqual(merged["bk|test park"]["source"], "location_cache")


if __name__ == "__main__":
    unittest.main()
