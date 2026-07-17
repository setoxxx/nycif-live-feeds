"""Tests for intersection and child-in-parent parsing."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.coverage_gap_utils import (  # noqa: E402
    parse_facility_in_parent,
    parse_intersection,
    parse_intersection_in_parent,
)


class IntersectionParseTests(unittest.TestCase):
    def test_plain_intersection(self) -> None:
        self.assertEqual(parse_intersection("125th Street and Marginal Street"), ("125th Street", "Marginal Street"))

    def test_intersection_before_comma(self) -> None:
        self.assertEqual(
            parse_intersection("Leland Avenue and O'Brien Avenue (in Soundview Park),Leland Avenue and"),
            ("Leland Avenue", "O'Brien Avenue (in Soundview Park)"),
        )

    def test_intersection_in_parent(self) -> None:
        self.assertEqual(
            parse_intersection_in_parent("Wilson Avenue and Weirfield Street in Irving Square Park"),
            ("Wilson Avenue", "Weirfield Street", "Irving Square Park"),
        )

    def test_intersection_in_parent_boardwalk(self) -> None:
        self.assertEqual(
            parse_intersection_in_parent("Sand Lane and Father Capadanno Boulevard in Franklin D. Roosevelt Boardwalk"),
            ("Sand Lane", "Father Capadanno Boulevard", "Franklin D. Roosevelt Boardwalk"),
        )

    def test_child_in_parent_paren_format(self) -> None:
        self.assertEqual(
            parse_facility_in_parent("Dance Room (in Chelsea Recreation Center)"),
            ("Dance Room", "Chelsea Recreation Center"),
        )

    def test_intersection_in_parent_paren_format(self) -> None:
        self.assertEqual(
            parse_intersection_in_parent("125th Street and Marginal Street (in West Harlem Piers)"),
            ("125th Street", "Marginal Street", "West Harlem Piers"),
        )


if __name__ == "__main__":
    unittest.main()
