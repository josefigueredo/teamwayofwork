from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import enrich_commit_urls
import generate_traceability
import import_git_evidence
import init_board
import inventory_git
import purge_bad_remote_links
import rebuild_index
import reconcile_inventory
import refresh_relations_catalog
import render_git_inventory
import relations
import validate_relations
from board_config import load_board_config
from relations import RelationValidationError, empty_document, load_document, save_document, validate_document


def write_board(board: Path, *, prefix: str = "LB") -> Path:
    board.mkdir(parents=True, exist_ok=True)
    (board / "Board.md").write_text(
        "---\n"
        'board_name: "Test board"\n'
        'entity_glob: "*.md"\n'
        f'entity_id_prefix: "{prefix}"\n'
        'sync_dir: "sync"\n'
        'relations_file: "sync/relations.json"\n'
        'jira_project_key: "TEST"\n'
        'jira_label: "test-board"\n'
        'remote_link_namespace: "test-board"\n'
        "---\n\n# Test board\n",
        encoding="utf-8",
    )
    (board / "sync").mkdir(exist_ok=True)
    save_document(board / "sync" / "relations.json", empty_document())
    return board


def write_entity(board: Path, entity_id: str, kind: str = "task", **values: str) -> Path:
    path = board / f"{entity_id}.md"
    fields = {
        "id": entity_id,
        "type": kind,
        "summary": values.get("summary", f"Summary {entity_id}"),
        "status": values.get("status", "To Do"),
        "parent": values.get("parent", ""),
        "jira_key": values.get("jira_key", ""),
        "spec_refs": values.get("spec_refs", "[]"),
        "evidence": values.get("evidence", ""),
    }
    path.write_text(
        "---\n" + "".join(f'{key}: "{value}"\n' for key, value in fields.items()) + "---\n\n# Entity\n",
        encoding="utf-8",
    )
    return path


class BoardAndRelationsTests(unittest.TestCase):
    def test_board_config_reads_profile_and_rejects_incomplete_index(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            board = write_board(Path(directory) / "board")
            config = load_board_config(board)
            self.assertEqual((config.name, config.entity_id_prefix), ("Test board", "LB"))
            self.assertEqual(config.relations_file, (board / "sync" / "relations.json").resolve())
            (board / "Bad.md").write_text("---\nboard_name: x\n---\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "configuración incompleta"):
                load_board_config(board, "Bad.md")

    def test_relation_document_validates_coverage_and_persists(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested" / "relations.json"
            document = empty_document()
            document["assets"] = [{"id": "asset:A"}]
            document["commits"] = [{"id": "commit:repo:abc"}]
            document["relations"] = [{
                "from": "commit:repo:abc", "to": "asset:A", "type": "evidence_for",
                "evidence": "test", "decision": "test",
            }]
            save_document(path, document)
            self.assertEqual(load_document(path)["commits"][0]["id"], "commit:repo:abc")
            document["relations"] = [{"from": "asset:A", "to": "missing", "type": "relates_to"}]
            with self.assertRaisesRegex(RelationValidationError, "huérfana"):
                validate_document(document)
            with self.assertRaisesRegex(RelationValidationError, "no existe"):
                load_document(path.parent / "absent.json")

    def test_relation_validation_rejects_malformed_document_shapes(self) -> None:
        node = {"asset:A": relations.RelationNode("asset:A", {"id": "asset:A"})}
        with tempfile.TemporaryDirectory() as directory:
            invalid_json = Path(directory) / "invalid.json"
            invalid_json.write_text("{", encoding="utf-8")
            with self.assertRaisesRegex(RelationValidationError, "JSON inválido"):
                load_document(invalid_json)
        for document, message in [
            ([], "documento"),
            ({"schema_version": 99, "baseline": {}}, "schema_version"),
            ({"schema_version": 1, "baseline": []}, "baseline"),
            ({"schema_version": 1, "baseline": {}}, "faltan"),
        ]:
            with self.assertRaisesRegex(RelationValidationError, message):
                relations.validate_header(document)
        base = empty_document()
        base["assets"] = "not-a-list"
        with self.assertRaisesRegex(RelationValidationError, "debe ser una lista"):
            relations.index_nodes(base)
        for values, message in [([1], "no objeto"), ([{}], "sin id"), ([{"id": "asset:A"}, {"id": "asset:A"}], "duplicado")]:
            base = empty_document()
            base["assets"] = values
            with self.assertRaisesRegex(RelationValidationError, message):
                relations.index_nodes(base)
        for relation, message in [
            (1, "no objeto"),
            ({}, "deben ser texto"),
            ({"from": "asset:A", "to": "asset:A", "type": "invalid"}, "no permitido"),
            ({"from": "asset:A", "to": "asset:A", "type": "relates_to", "evidence": 1}, "evidence"),
        ]:
            with self.assertRaisesRegex(RelationValidationError, message):
                relations.validate_relation(relation, node)
        base = empty_document()
        base["relations"] = "not-a-list"
        with self.assertRaisesRegex(RelationValidationError, "relations debe"):
            relations.validate_relations(base, node)
        base["relations"] = []
        base["exceptions"] = "not-a-list"
        with self.assertRaisesRegex(RelationValidationError, "exceptions"):
            relations.validate_commit_coverage(base, {"commit:repo:a": relations.RelationNode("commit:repo:a", {})}, set())
        self.assertEqual(relations.relations_for_asset({"relations": [{"from": "asset:A", "to": "spec:S"}, {"from": "x", "to": "y"}]}, "A"), [{"from": "asset:A", "to": "spec:S"}])


class InventoryAndRenderingTests(unittest.TestCase):
    def test_inventory_parses_git_output_and_prunes_invalid_repositories(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            repo = workspace / "repo"
            repo.mkdir()
            git_calls: list[tuple[str, ...]] = []

            def git_side_effect(repository: Path, *args: str) -> str:
                git_calls.append(args)
                if args[:2] == ("remote", "-v"):
                    return "origin git@example.test:team/repo.git (fetch)\norigin git@example.test:team/repo.git (push)\n"
                if args[0] == "log":
                    return "abc\x1f2025-01-02T00:00:00Z\x1fAda\x1fada@test\x1fparent\x1fA change\nsrc/a.py\n"
                if args[:2] == ("rev-parse", "HEAD"):
                    return "abc\n"
                if args[:2] == ("branch", "--show-current"):
                    return "main\n"
                if args[:2] == ("status", "--short"):
                    return " M file\n"
                return "true\n"

            with patch.object(inventory_git, "run_git", side_effect=git_side_effect):
                result = inventory_git.repository_inventory(workspace, repo, "2025-01-01")
            self.assertEqual(result["remotes"]["origin"], "git@example.test:team/repo.git")
            self.assertEqual(result["commits"][0]["paths"], ["src/a.py"])
            self.assertTrue(any("--since=2025-01-01" in call for call in git_calls))

            (repo / ".git").mkdir()
            ignored = workspace / "node_modules" / "skip"
            ignored.mkdir(parents=True)
            (ignored / ".git").mkdir()
            with patch.object(inventory_git, "run_git", side_effect=[ "true\n", subprocess.CalledProcessError(1, "git") ]):
                self.assertEqual(inventory_git.discover_repositories(workspace), [repo])

    def test_inventory_main_and_markdown_renderer_write_generated_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            board = write_board(root / "board")
            output = board / "sync" / "inventory.json"
            with patch.object(inventory_git, "discover_repositories", return_value=[]), patch.object(
                sys, "argv", ["inventory_git.py", "--board-dir", str(board), "--workspace", str(root), "--output", str(output)]
            ):
                self.assertEqual(inventory_git.main(), 0)
            inventory = json.loads(output.read_text(encoding="utf-8"))
            inventory["repositories"] = [{"path": "repo", "commits": [{"committed_at": "2025-01-01", "hash": "abcdef123456", "author": "Ada", "subject": "a | b"}]}]
            output.write_text(json.dumps(inventory), encoding="utf-8")
            rendered = board / "_meta" / "commits.md"
            with patch.object(sys, "argv", ["render_git_inventory.py", "--board-dir", str(board), "--input", str(output), "--output", str(rendered)]):
                self.assertEqual(render_git_inventory.main(), 0)
            self.assertIn("a \\| b", rendered.read_text(encoding="utf-8"))
            self.assertEqual(render_git_inventory.short_date(""), "unknown")


class CatalogAndEvidenceTests(unittest.TestCase):
    def test_catalog_cli_and_traceability_report_link_specs_and_assets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            board = write_board(root / "board")
            write_entity(board, "LB-1", spec_refs="[12]")
            spec = root / "specs" / "12-example" / "spec.md"
            spec.parent.mkdir(parents=True)
            spec.write_text("# Spec title\n**Status**: Approved\n", encoding="utf-8")
            with patch.object(sys, "argv", ["refresh.py", "--board-dir", str(board), "--workspace", str(root)]):
                self.assertEqual(refresh_relations_catalog.main(), 0)
            document = load_document(board / "sync" / "relations.json")
            self.assertEqual(document["relations"][0]["from"], "spec:12")
            report = board / "_meta" / "trace.md"
            with patch.object(sys, "argv", ["trace.py", "--board-dir", str(board), "--output", str(report)]):
                self.assertEqual(generate_traceability.main(), 0)
            self.assertIn("Spec title (Approved)", report.read_text(encoding="utf-8"))

    def test_import_and_reconcile_evidence_cover_resolved_unresolved_and_exceptions(self) -> None:
        document = empty_document()
        document["assets"] = [{"id": "asset:A"}]
        commits = {("repo", "abcdef123456"): {"committed_at": "now", "author": "Ada", "subject": "Feature"}}
        nodes: dict[str, dict] = {}
        relations: set[tuple[str, str, str]] = set()
        count, unresolved = import_git_evidence.process_evidence_references("A", "evidence: repo@abcdef1 repo@1234567", commits, document, nodes, relations)
        self.assertEqual((count, unresolved), (1, ["asset:A:repo@1234567"]))
        inventory = {"repositories": [{"path": "repo", "commits": [
            {"hash": "abcdef123456", "committed_at": "now", "author": "Ada", "subject": "Feature"},
            {"hash": "defabc123456", "committed_at": "now", "author": "Ada", "subject": "chore(deps): update"},
        ]}]}
        unresolved = reconcile_inventory.reconcile(document, inventory, {"abcdef": "A"}, {"asset:A"}, auto_exceptions=True)
        self.assertEqual(unresolved, [])
        self.assertEqual(len(document["exceptions"]), 1)
        self.assertEqual(reconcile_inventory.parse_assignments(["abc=A"]), {"abc": "A"})
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            reconcile_inventory.reconcile(document, inventory, {"a": "A", "ab": "A"}, {"asset:A"}, auto_exceptions=False)


class UtilitiesCliTests(unittest.TestCase):
    def test_enrich_urls_validate_cli_and_rebuild_index(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            board = write_board(Path(directory) / "board")
            write_entity(board, "LB-E1", "epic", status="In Progress", summary="[LB-E1] " + "x" * 80, jira_key="TEST-1")
            document = load_document(board / "sync" / "relations.json")
            document["assets"] = [{"id": "asset:LB-E1", "jira_key": "TEST-1"}]
            document["commits"] = [{"id": "commit:repo:abc", "repository": "repo", "hash": "abc"}]
            document["exceptions"] = [{"type": "excluded_with_reason", "commit": "commit:repo:abc"}]
            save_document(board / "sync" / "relations.json", document)
            inventory = board / "sync" / "inventory.json"
            inventory.write_text(json.dumps({"repositories": [{"path": "repo", "remotes": {"origin": "git@gitlab.example:team/repo.git"}}]}), encoding="utf-8")
            with patch.object(sys, "argv", ["urls.py", "--board-dir", str(board), "--inventory", str(inventory)]):
                self.assertEqual(enrich_commit_urls.main(), 0)
            self.assertEqual(load_document(board / "sync" / "relations.json")["commits"][0]["url"], "https://gitlab.example/team/repo/-/commit/abc")
            with patch.object(sys, "argv", ["validate.py", "--board-dir", str(board)]):
                self.assertEqual(validate_relations.main(), 0)
            lines = rebuild_index.build_index(load_board_config(board))
            self.assertIn("LB-E1", "\n".join(lines))
            self.assertEqual(rebuild_index.short_summary("[LB-E1] hello", "LB-E1"), "hello")
            self.assertIsNone(enrich_commit_urls.web_base("not-a-remote"))

    def test_init_board_and_purge_mocked_network_client(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            board = Path(directory) / "created"
            with patch.object(sys, "argv", ["init.py", "--board-dir", str(board), "--name", "Created", "--jira-project-key", "C", "--jira-label", "created"]):
                self.assertEqual(init_board.main(), 0)
            self.assertTrue((board / "_meta" / "autores.md").is_file())
            self.assertTrue((board / "sync" / ".env").is_file())

        class Client:
            instances: list["Client"] = []
            def __init__(self, *_args, **_kwargs): self.deleted = []; Client.instances.append(self)
            def remote_links(self, _key): return [{"id": "1", "object": {"url": "https://x/repo.git/commit/a"}}, {"id": "2", "object": {"url": "https://x/ok"}}]
            def delete_remote_link(self, key, link_id): self.deleted.append((key, link_id))

        with patch.object(purge_bad_remote_links, "JiraClient", Client):
            key, scanned, deleted = purge_bad_remote_links.purge_issue("C-1", "url", "e", "t", 0)
        self.assertEqual((key, scanned, deleted, Client.instances[0].deleted), ("C-1", 2, 1, [("C-1", "1")]))
        self.assertTrue(purge_bad_remote_links.bad_url("x.git"))
        self.assertFalse(purge_bad_remote_links.bad_url("https://x/commit/a"))

    def test_purge_main_handles_credentials_and_parallel_issue_results(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            board = write_board(Path(directory) / "board")
            document = load_document(board / "sync" / "relations.json")
            document["assets"] = [{"id": "asset:A", "jira_key": "T-2"}, {"id": "asset:B", "jira_key": "T-1"}]
            save_document(board / "sync" / "relations.json", document)
            settings = type("Settings", (), {"relations_path": board / "sync" / "relations.json"})()
            with patch.dict("os.environ", {}, clear=True), patch.object(sys, "argv", ["purge.py", "--board-dir", str(board)]):
                self.assertEqual(purge_bad_remote_links.main(), 1)
            with patch.dict("os.environ", {"JIRA_EMAIL": "a@test", "JIRA_API_TOKEN": "token", "JIRA_WRITE_THROTTLE": "0.2"}, clear=True), patch.object(
                purge_bad_remote_links, "load_settings", return_value=settings
            ), patch.object(purge_bad_remote_links, "tracker_base_url", return_value="https://jira.test"), patch.object(
                purge_bad_remote_links, "purge_issue", side_effect=[("T-1", 2, 1), ("T-2", 3, 2)]
            ) as purge, patch.object(sys, "argv", ["purge.py", "--board-dir", str(board), "--workers", "99"]):
                self.assertEqual(purge_bad_remote_links.main(), 0)
            self.assertEqual(purge.call_count, 2)

    def test_rebuild_index_cli_renders_hierarchy_and_rejects_other_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            board = write_board(Path(directory) / "board")
            write_entity(board, "LB-E1", "epic")
            write_entity(board, "LB-S1", "story", parent="LB-E1")
            write_entity(board, "LB-T1", "task", parent="LB-S1")
            write_entity(board, "LB-ST1", "sub-task", parent="LB-T1")
            with patch.object(sys, "argv", ["index.py", "--board-dir", str(board)]):
                rebuild_index.main()
            text = (board / "Board.md").read_text(encoding="utf-8")
            self.assertIn("LB-ST1", text)
            self.assertIn("## LB-E1", text)
            with patch.object(sys, "argv", ["index.py", "--board-dir", str(board), "--output", str(board / "other.md")]):
                with self.assertRaisesRegex(ValueError, "índice principal"):
                    rebuild_index.main()
            self.assertEqual(rebuild_index.parse_frontmatter("not frontmatter"), {})
            self.assertEqual(rebuild_index.decode_quoted_scalar('"unterminated'), '"unterminated')


class ErrorAndMainFlowTests(unittest.TestCase):
    def test_import_evidence_main_persists_and_reports_unresolved_references(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            board = write_board(Path(directory) / "board")
            asset = write_entity(board, "A", evidence="repo@abcdef1")
            asset.write_text(
                asset.read_text(encoding="utf-8").replace('id: "A"', "id: A").replace('evidence: "repo@abcdef1"', "evidence: repo@abcdef1"),
                encoding="utf-8",
            )
            document = load_document(board / "sync" / "relations.json")
            document["assets"] = [{"id": "asset:A"}]
            save_document(board / "sync" / "relations.json", document)
            inventory = board / "sync" / "inventory.json"
            inventory.write_text(json.dumps({"repositories": [{"path": "repo", "commits": [{
                "hash": "abcdef123456", "committed_at": "now", "author": "Ada", "subject": "feature"
            }]}]}), encoding="utf-8")
            with patch.object(sys, "argv", ["import.py", "--board-dir", str(board), "--inventory", str(inventory)]):
                self.assertEqual(import_git_evidence.main(), 0)
            self.assertEqual(load_document(board / "sync" / "relations.json")["commits"][0]["hash"], "abcdef123456")
            unresolved_asset = write_entity(board, "B", evidence="repo@1234567")
            unresolved_asset.write_text(
                unresolved_asset.read_text(encoding="utf-8").replace('id: "B"', "id: B").replace('evidence: "repo@1234567"', "evidence: repo@1234567"),
                encoding="utf-8",
            )
            with patch.object(sys, "argv", ["import.py", "--board-dir", str(board), "--inventory", str(inventory)]):
                with self.assertRaisesRegex(RuntimeError, "unresolved"):
                    import_git_evidence.main()
            plain = board / "plain.md"
            plain.write_text("not frontmatter", encoding="utf-8")
            self.assertEqual(import_git_evidence.frontmatter_block(plain), "")
            self.assertEqual(import_git_evidence.frontmatter(plain), {})

    def test_reconcile_main_and_edge_classification_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            board = write_board(Path(directory) / "board")
            document = load_document(board / "sync" / "relations.json")
            document["assets"] = [{"id": "asset:A"}]
            save_document(board / "sync" / "relations.json", document)
            inventory = board / "sync" / "inventory.json"
            inventory.write_text(json.dumps({"repositories": [{"path": "repo", "commits": [{
                "hash": "abcdef123456", "committed_at": "now", "author": "Ada", "subject": "Feature"
            }]}]}), encoding="utf-8")
            with patch.object(sys, "argv", ["reconcile.py", "--board-dir", str(board), "--inventory", str(inventory), "--map", "abcdef=A"]):
                self.assertEqual(reconcile_inventory.main(), 0)
            self.assertEqual(reconcile_inventory.exception_reason("Merge: branch"), "reviewed integration commit; no independent product outcome")
            self.assertIsNone(reconcile_inventory.exception_reason("Feature"))
            with self.assertRaisesRegex(ValueError, "unknown asset"):
                reconcile_inventory.reconcile(empty_document(), json.loads(inventory.read_text()), {"abcdef": "missing"}, set(), auto_exceptions=False)

    def test_remaining_utility_error_and_parser_branches(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            board = write_board(root / "board")
            self.assertEqual(enrich_commit_urls.web_base("https://bitbucket.test/team/repo.git"), ("https://bitbucket.test/team/repo", "bitbucket.test"))
            self.assertEqual(enrich_commit_urls.commit_url("https://bitbucket.test/r", "bitbucket.test", "a"), "https://bitbucket.test/r/commits/a")
            self.assertEqual(enrich_commit_urls.commit_url("https://github.test/r", "github.test", "a"), "https://github.test/r/commit/a")
            self.assertEqual(refresh_relations_catalog.decode_scalar('"bad'), '"bad')
            self.assertEqual(refresh_relations_catalog.list_value("bad"), [])
            (root / "plain.md").write_text("plain", encoding="utf-8")
            self.assertEqual(refresh_relations_catalog.frontmatter(root / "plain.md"), {})
            self.assertEqual(rebuild_index.index_frontmatter(type("Config", (), {"index_file": root / "plain.md"})()), [])
            with patch.object(sys, "argv", ["validate.py", "--board-dir", str(root / "missing")]), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(ValueError):
                    validate_relations.main()
            bad_relations = board / "sync" / "bad.json"
            bad_relations.write_text("{", encoding="utf-8")
            with patch.object(sys, "argv", ["render.py", "--board-dir", str(board), "--input", str(bad_relations)]), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    render_git_inventory.main()
            with patch.object(subprocess, "run", return_value=type("Result", (), {"stdout": "ok"})()) as run:
                self.assertEqual(inventory_git.run_git(root, "status"), "ok")
            self.assertEqual(run.call_args.args[0][:2], ["git", "-C"])


if __name__ == "__main__":
    unittest.main()
