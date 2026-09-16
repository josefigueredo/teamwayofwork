from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import create_asset
from board_config import BoardConfig


def config(board_dir: Path) -> BoardConfig:
    return BoardConfig(
        board_dir=board_dir,
        index_file=board_dir / "Board.md",
        name="Board",
        entity_glob="*.md",
        entity_id_prefix="B",
        sync_dir=board_dir / "sync",
        relations_file=board_dir / "sync" / "relations.json",
        jira_project_key="PROJ",
        jira_label="board",
        remote_link_namespace="board",
    )


class CreateAssetTests(unittest.TestCase):
    def test_helpers_and_hierarchy_creation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            board_dir = Path(directory)
            board = config(board_dir)
            with patch.object(create_asset, "load_board_config", return_value=board):
                with patch.object(sys, "argv", ["create_asset.py", "--board-dir", directory, "--type", "epic", "--summary", "Platform"]):
                    self.assertEqual(create_asset.main(), 0)
                epic = next(board_dir.rglob("BE01.md"))
                with patch.object(sys, "argv", ["create_asset.py", "--board-dir", directory, "--type", "story", "--parent", "BE01", "--summary", "Story"]):
                    self.assertEqual(create_asset.main(), 0)
                story = next(board_dir.rglob("BS01.md"))
                with patch.object(sys, "argv", ["create_asset.py", "--board-dir", directory, "--type", "task", "--parent", "BS01", "--summary", "Task"]):
                    self.assertEqual(create_asset.main(), 0)
                task = next(board_dir.rglob("BT01.md"))
                with patch.object(sys, "argv", ["create_asset.py", "--board-dir", directory, "--type", "sub-task", "--parent", "BT01", "--summary", "Sub"]):
                    self.assertEqual(create_asset.main(), 0)
            self.assertIn("BS01", create_asset.read_children(epic))
            self.assertIn("BT01", create_asset.read_children(story))
            self.assertIn("BST01", create_asset.read_children(task))

    def test_validation_and_helper_errors(self) -> None:
        self.assertEqual(create_asset.slugify("A Complex name!"), "a-complex-name")
        with self.assertRaisesRegex(ValueError, "slug vacío"):
            create_asset.slugify("***")
        with tempfile.TemporaryDirectory() as directory:
            board_dir = Path(directory)
            board = config(board_dir)
            with patch.object(create_asset, "load_board_config", return_value=board):
                with patch.object(sys, "argv", ["create_asset.py", "--board-dir", directory, "--type", "story", "--summary", "No parent"]):
                    with self.assertRaises(SystemExit):
                        create_asset.main()
                with patch.object(sys, "argv", ["create_asset.py", "--board-dir", directory, "--type", "epic", "--summary", "Bad", "--slug", "../bad"]):
                    with self.assertRaises(ValueError):
                        create_asset.main()


if __name__ == "__main__":
    unittest.main()
