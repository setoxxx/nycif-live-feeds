from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from scripts.borg_cli_paths import resolve_workspace_file, workspace_relative


class BorgCliPathTests(unittest.TestCase):
    def test_existing_workspace_file_is_allowed(self):
        path = resolve_workspace_file("docs/contracts/BORG_SOURCE_REGISTRY_V1.json", must_exist=True)
        self.assertTrue(path.is_file())
        self.assertEqual(workspace_relative(path), "docs/contracts/BORG_SOURCE_REGISTRY_V1.json")

    def test_absolute_path_is_rejected(self):
        with self.assertRaises(ValueError):
            resolve_workspace_file("/tmp/nycif-borg.json", must_exist=False)

    def test_parent_traversal_is_rejected(self):
        with self.assertRaises(ValueError):
            resolve_workspace_file("../outside.json", must_exist=False)

    def test_unsupported_path_characters_are_rejected(self):
        with self.assertRaises(ValueError):
            resolve_workspace_file("tests/output file.json", must_exist=False)

    def test_symlink_escape_is_rejected(self):
        workspace = Path.cwd()
        with tempfile.TemporaryDirectory(dir=workspace, prefix="borg-path-test-") as local_tmp:
            local_dir = Path(local_tmp)
            with tempfile.TemporaryDirectory(prefix="borg-outside-") as outside_tmp:
                outside_file = Path(outside_tmp) / "outside.json"
                outside_file.write_text("{}\n")
                link = local_dir / "escape"
                os.symlink(outside_tmp, link)
                relative = (link / "outside.json").relative_to(workspace).as_posix()
                with self.assertRaises(ValueError):
                    resolve_workspace_file(relative, must_exist=True)

    def test_workspace_local_output_parent_must_exist(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd(), prefix="borg-path-test-") as local_tmp:
            relative = (Path(local_tmp) / "result.json").relative_to(Path.cwd()).as_posix()
            output = resolve_workspace_file(relative, must_exist=False)
            self.assertEqual(output.name, "result.json")


if __name__ == "__main__":
    unittest.main()
