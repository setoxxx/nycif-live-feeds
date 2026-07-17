"""Tests for the shared supplemental GPS-fill resolver in coverage_gap_utils.

Covers the "Child in Parent" display_location decomposition bug fix: rows
like "Pétanque Court in Washington Square Park" were being looked up as a
single opaque string against the gazetteer and almost always missing, even
though the child facility or the parent park was already a known location.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.coverage_gap_utils import (  # noqa: E402
    build_calendar_parks_overlap_index,
    parse_facility_in_parent,
    resolve_supplemental_coordinates,
)
from scripts.nyc_location_gazetteer import (  # noqa: E402
    NYCLocationGazetteer,
    gazetteer_entry,
)
from scripts.nyc_location_resolver import NYCLocationResolver, ResolveResult  # noqa: E402


class ParseFacilityInParentTests(unittest.TestCase):
    def test_splits_child_and_parent(self) -> None:
        self.assertEqual(
            parse_facility_in_parent("Pétanque Court in Washington Square Park"),
            ("Pétanque Court", "Washington Square Park"),
        )

    def test_splits_on_first_in_only(self) -> None:
        # Parent itself may legitimately contain " in " again; only the first
        # occurrence is the child/parent boundary.
        self.assertEqual(
            parse_facility_in_parent("Front Lawn in Rev. T. Wendell Foster Park and Recreation Center"),
            ("Front Lawn", "Rev. T. Wendell Foster Park and Recreation Center"),
        )

    def test_no_split_for_plain_park_name(self) -> None:
        self.assertIsNone(parse_facility_in_parent("Bryant Park"))
        self.assertIsNone(parse_facility_in_parent("125th Street and Marginal Street"))

    def test_no_split_when_side_would_be_empty(self) -> None:
        self.assertIsNone(parse_facility_in_parent("in Central Park"))
        self.assertIsNone(parse_facility_in_parent(""))
        self.assertIsNone(parse_facility_in_parent(None))


class BuildCalendarParksOverlapIndexTests(unittest.TestCase):
    def test_indexes_only_rows_with_valid_coordinates(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "calendar_parks_coord_match_proposals.json"
            path.write_text(
                json.dumps(
                    {
                        "proposals": [
                            {
                                "overlap_key": "match one|2026-07-24",
                                "proposed_lat": 40.66,
                                "proposed_lng": -73.94,
                            },
                            {
                                "overlap_key": "pending no coords|2026-07-24",
                                "proposed_lat": None,
                                "proposed_lng": None,
                            },
                            {"overlap_key": "", "proposed_lat": 40.7, "proposed_lng": -73.9},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            index = build_calendar_parks_overlap_index(path)
        self.assertEqual(set(index.keys()), {"match one|2026-07-24"})


def _gazetteer(entries: dict[str, dict]) -> NYCLocationGazetteer:
    return NYCLocationGazetteer(entries)


class ResolveSupplementalCoordinatesTests(unittest.TestCase):
    def test_child_gazetteer_hit_wins_over_parent(self) -> None:
        child_entry = gazetteer_entry(
            lat=40.731,
            lng=-73.997,
            source="nyc_parks_facility_reference",
            confidence="high",
            confidence_reason="Official NYC Parks BigApps facility reference.",
            label="Handball Court",
        )
        gazetteer = _gazetteer({"mn|handball court": child_entry})
        row = {
            "display_location": "Handball Court in Washington Square Park",
            "borough": "Mn",
            "overlap_key": "some event|2026-07-20",
        }
        fill = resolve_supplemental_coordinates(row, gazetteer, {}, None)
        self.assertIsNotNone(fill)
        self.assertEqual(fill["fill_method"], "location_gazetteer")
        self.assertEqual(fill["proposed_lat"], 40.731)

    def test_falls_back_to_parent_park_when_child_misses(self) -> None:
        parent_entry = gazetteer_entry(
            lat=40.618,
            lng=-73.94,
            source="nyc_parks_facility_reference",
            confidence="high",
            confidence_reason="Official NYC Parks BigApps facility reference.",
            label="Marine Park",
        )
        gazetteer = _gazetteer({"bk|marine park": parent_entry})
        row = {
            "display_location": "Playground 278 in Marine Park",
            "borough": "Bk",
            "overlap_key": "marine park event|2026-07-20",
        }
        fill = resolve_supplemental_coordinates(row, gazetteer, {}, None)
        self.assertIsNotNone(fill)
        self.assertEqual(fill["fill_method"], "parent_park_fallback")
        self.assertEqual(fill["geocoder_confidence"], "medium")
        self.assertEqual(fill["proposed_lat"], 40.618)

    def test_calendar_parks_overlap_used_before_resolver(self) -> None:
        gazetteer = _gazetteer({})
        resolver = NYCLocationResolver(gazetteer, {}, allow_live_geosearch=False)
        row = {
            "display_location": "Front Lawn in Some Unknown Park",
            "borough": "Qn",
            "overlap_key": "some overlap key|2026-07-20",
        }
        calendar_overlap = {
            "some overlap key|2026-07-20": {
                "proposed_lat": 40.75,
                "proposed_lng": -73.85,
            }
        }
        with patch.object(resolver, "resolve") as mock_resolve:
            fill = resolve_supplemental_coordinates(
                row, gazetteer, {}, resolver, calendar_parks_overlap=calendar_overlap
            )
        mock_resolve.assert_not_called()
        self.assertIsNotNone(fill)
        self.assertEqual(fill["fill_method"], "parks_overlap_key")
        self.assertEqual(fill["geocoder_source"], "calendar_parks_coord_match_proposals")
        self.assertEqual(fill["proposed_lat"], 40.75)

    def test_resolver_is_last_resort_and_uses_child_name(self) -> None:
        gazetteer = _gazetteer({})
        resolver = NYCLocationResolver(gazetteer, {}, allow_live_geosearch=False)
        fake_result = ResolveResult(
            resolved=True,
            tier="tier_2_geosearch_cache",
            lat=40.7,
            lng=-73.9,
            source="nyc_geosearch_planninglabs",
            confidence="high",
            confidence_reason="cached",
            label="Test Pool",
            query_used="Test Pool, Queens, NY",
        )
        row = {
            "display_location": "Test Pool in Example Park",
            "borough": "Qn",
            "overlap_key": "no overlap match|2026-07-20",
        }
        with patch.object(resolver, "resolve", return_value=fake_result) as mock_resolve:
            fill = resolve_supplemental_coordinates(row, gazetteer, {}, resolver, calendar_parks_overlap={})
        self.assertEqual(mock_resolve.call_args.kwargs["display_location"], "Test Pool")
        self.assertIsNotNone(fill)
        self.assertEqual(fill["fill_method"], "nyc_geosearch_cache")

    def test_no_fill_returns_none(self) -> None:
        gazetteer = _gazetteer({})
        resolver = NYCLocationResolver(gazetteer, {}, allow_live_geosearch=False)
        row = {
            "display_location": "Nowhere Facility in Nowhere Park",
            "borough": "SI",
            "overlap_key": "nowhere|2026-07-20",
        }
        with patch.object(
            resolver,
            "resolve",
            return_value=ResolveResult(
                resolved=False,
                tier="unresolved",
                lat=None,
                lng=None,
                source=None,
                confidence=None,
                confidence_reason="No match.",
            ),
        ):
            fill = resolve_supplemental_coordinates(row, gazetteer, {}, resolver, calendar_parks_overlap={})
        self.assertIsNone(fill)

    def test_permanently_ungeocodable_never_reaches_resolver(self) -> None:
        gazetteer = _gazetteer({})
        resolver = NYCLocationResolver(gazetteer, {}, allow_live_geosearch=True)
        row = {
            "display_location": "Poll Sites Citywide",
            "borough": "Mn",
            "overlap_key": "election|2026-11-01",
        }
        with patch.object(resolver, "resolve") as mock_resolve:
            fill = resolve_supplemental_coordinates(row, gazetteer, {}, resolver)
        mock_resolve.assert_not_called()
        self.assertIsNone(fill)


class RealDataChildInParentDecompositionTests(unittest.TestCase):
    """Validates the fix against the actual M11 supplemental queue.

    Rows in ranks 2419-3457 that are still marked "rejected" and whose
    display_location matches the "Child in Parent" pattern should now
    overwhelmingly resolve via gazetteer decomposition (child or parent
    park), matching the ~909-row expectation from the rejected-pass fix.
    """

    @classmethod
    def setUpClass(cls) -> None:
        from scripts.apply_supplemental_rejected_pass import (
            build_parks_overlap_index,
            ensure_gazetteer,
            load_resolver,
            resolve_coordinates,
        )
        from scripts.coverage_gap_utils import build_calendar_parks_overlap_index

        cls.resolve_coordinates = staticmethod(resolve_coordinates)
        cls.gazetteer = ensure_gazetteer()
        cls.parks_overlap = build_parks_overlap_index()
        cls.calendar_parks_overlap = build_calendar_parks_overlap_index()
        cls.resolver = load_resolver(allow_live_geosearch=False)

        queue_path = ROOT / "data" / "supplemental_manual_approval_queue.json"
        payload = json.loads(queue_path.read_text(encoding="utf-8"))
        rows = payload.get("approval_queue", [])
        cls.in_parent_rejected_rows = [
            row
            for row in rows
            if row.get("manual_review_status") == "rejected"
            and row.get("review_rank") is not None
            and 2419 <= int(row["review_rank"]) <= 3457
            and parse_facility_in_parent(row.get("display_location")) is not None
        ]

    def test_most_child_in_parent_rows_now_resolve(self) -> None:
        if not self.in_parent_rejected_rows:
            self.skipTest("supplemental_manual_approval_queue.json has no matching rows in this checkout")
        resolved = 0
        for row in self.in_parent_rejected_rows:
            fill = self.resolve_coordinates(
                row,
                self.gazetteer,
                self.parks_overlap,
                self.resolver,
                calendar_parks_overlap=self.calendar_parks_overlap,
            )
            if fill:
                resolved += 1
        total = len(self.in_parent_rejected_rows)
        # Expect the overwhelming majority to resolve via gazetteer decomposition
        # alone (no live GeoSearch). As rejected-pass batches progress, the
        # remaining "X in Y" pool skews toward hard cases (intersections,
        # duplicate rec-center names, etc.), so use 85% not 90%.
        self.assertGreater(
            resolved / total,
            0.85,
            f"only {resolved}/{total} 'Child in Parent' rejected rows resolved",
        )


if __name__ == "__main__":
    unittest.main()
