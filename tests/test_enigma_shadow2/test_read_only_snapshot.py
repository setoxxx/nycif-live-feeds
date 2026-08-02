import json
import tempfile
import unittest
from pathlib import Path

from enigma.shadow2.read_only_snapshot import ReadOnlySnapshot, SnapshotReadError


class ReadOnlySnapshotTests(unittest.TestCase):
    def _write_registry(self, root: Path, raw_path: str = "data/raw.json") -> Path:
        registry_path = root / "data" / "source_lineage_registry_v01.json"
        registry_path.parent.mkdir(parents=True, exist_ok=True)
        registry_path.write_text(
            json.dumps(
                {
                    "artifact_type": "source_lineage_registry_v01",
                    "entries": [
                        {
                            "id": "raw:test",
                            "repository": "setoxxx/nycif-live-feeds",
                            "path_or_source": raw_path,
                            "raw_intake_countable": True,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        return registry_path

    def test_reads_pages_without_mutating_source_objects(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pages = root / "approved"
            pages.mkdir()
            original = {"events": [{"id": "1", "title": "Event One"}]}
            page_path = pages / "page-0001.json"
            page_path.write_text(json.dumps(original), encoding="utf-8")

            snapshot = ReadOnlySnapshot(
                repo_root=root,
                approved_pages_root=Path("approved"),
                review_pages_root=None,
                lineage_registry_path=None,
                require_page_manifests=False,
            )
            records = list(snapshot.read_approved_events())
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0].record, original["events"][0])
            records[0].record["title"] = "Changed copy"
            self.assertEqual(json.loads(page_path.read_text(encoding="utf-8")), original)

    def test_malformed_page_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pages = root / "approved"
            pages.mkdir()
            (pages / "page-0001.json").write_text("not json", encoding="utf-8")
            snapshot = ReadOnlySnapshot(
                repo_root=root,
                approved_pages_root=Path("approved"),
                review_pages_root=None,
                lineage_registry_path=None,
                require_page_manifests=False,
            )
            with self.assertRaises(SnapshotReadError):
                list(snapshot.read_approved_events())

    def test_non_object_event_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pages = root / "approved"
            pages.mkdir()
            (pages / "page-0001.json").write_text(json.dumps({"events": ["bad"]}), encoding="utf-8")
            snapshot = ReadOnlySnapshot(
                repo_root=root,
                approved_pages_root=Path("approved"),
                review_pages_root=None,
                lineage_registry_path=None,
                require_page_manifests=False,
            )
            with self.assertRaises(SnapshotReadError):
                list(snapshot.read_approved_events())

    def test_registry_discovers_countable_raw_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_registry(root)
            raw = root / "data" / "raw.json"
            raw.write_text(json.dumps({"events": [{"id": "1"}, {"id": "2"}]}), encoding="utf-8")
            snapshot = ReadOnlySnapshot(
                repo_root=root,
                approved_pages_root=None,
                review_pages_root=None,
            )
            records = list(snapshot.read_raw_snapshots())
            self.assertEqual([record.record["id"] for record in records], ["1", "2"])
            self.assertEqual(records[0].artifact_path, "data/raw.json")

    def test_malformed_raw_snapshot_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_registry(root)
            raw = root / "data" / "raw.json"
            raw.write_text("{broken", encoding="utf-8")
            snapshot = ReadOnlySnapshot(
                repo_root=root,
                approved_pages_root=None,
                review_pages_root=None,
            )
            with self.assertRaises(SnapshotReadError):
                list(snapshot.read_raw_snapshots())

    def test_registry_path_cannot_escape_repository(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = self._write_registry(root, raw_path="../outside.json")
            self.assertTrue(registry.exists())
            snapshot = ReadOnlySnapshot(
                repo_root=root,
                approved_pages_root=None,
                review_pages_root=None,
            )
            with self.assertRaises(SnapshotReadError):
                snapshot.raw_snapshot_paths()

    def test_event_counts_reconcile_enabled_collections(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pages = root / "approved"
            pages.mkdir()
            (pages / "page-0001.json").write_text(
                json.dumps({"events": [{"id": "1"}, {"id": "2"}]}),
                encoding="utf-8",
            )
            snapshot = ReadOnlySnapshot(
                repo_root=root,
                approved_pages_root=Path("approved"),
                review_pages_root=None,
                lineage_registry_path=None,
                require_page_manifests=False,
            )
            self.assertEqual(snapshot.event_counts(), {"approved": 2, "review": 0, "raw": 0})

    def test_manifest_reconciles_page_counts_and_total(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            layer = root / "approved"
            pages = layer / "pages"
            pages.mkdir(parents=True)
            (pages / "page-0001.json").write_text(
                json.dumps({"events": [{"id": "1"}, {"id": "2"}]}),
                encoding="utf-8",
            )
            (layer / "manifest.json").write_text(
                json.dumps(
                    {
                        "layer": "approved",
                        "page_count": 1,
                        "total": 2,
                        "pages": [{"page": "page-0001.json", "count": 2}],
                    }
                ),
                encoding="utf-8",
            )
            snapshot = ReadOnlySnapshot(
                repo_root=root,
                approved_pages_root=Path("approved/pages"),
                review_pages_root=None,
                lineage_registry_path=None,
            )
            self.assertEqual(len(list(snapshot.read_approved_events())), 2)

    def test_manifest_mismatch_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            layer = root / "approved"
            pages = layer / "pages"
            pages.mkdir(parents=True)
            (pages / "page-0001.json").write_text(
                json.dumps({"events": [{"id": "1"}]}),
                encoding="utf-8",
            )
            (layer / "manifest.json").write_text(
                json.dumps(
                    {
                        "layer": "approved",
                        "page_count": 1,
                        "total": 2,
                        "pages": [{"page": "page-0001.json", "count": 2}],
                    }
                ),
                encoding="utf-8",
            )
            snapshot = ReadOnlySnapshot(
                repo_root=root,
                approved_pages_root=Path("approved/pages"),
                review_pages_root=None,
                lineage_registry_path=None,
            )
            with self.assertRaises(SnapshotReadError):
                list(snapshot.read_approved_events())


if __name__ == "__main__":
    unittest.main()
