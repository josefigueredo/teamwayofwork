from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from create_asset import body
from board_config import BoardConfig
import sync_board
from sync_board import apply_actions, create_fields, load_state
from sync_entities import load_local_entities, parse_frontmatter
from sync_models import LocalEntity, PlanAction, SyncSettings
from sync_planning import (
    canonical_labels,
    decide_source,
    jira_description,
    plan_adoption,
    plan_sync,
    remote_link_plan,
    save_plan,
    verify_plan,
)


class FakeJiraClient:
    def __init__(self, entity_paths: dict[str, Path] | None = None, parents: dict[str, str] | None = None) -> None:
        self.entity_paths = entity_paths or {}
        self.parents = parents or {}
        self.calls: list[dict] = []
        self.persisted_parents: list[bool] = []
        self.base_url = "https://jira.example.test"
        self.throttle_seconds = 0
        self.limiter = None

    def create_issue(self, fields: dict) -> dict:
        entity_id = fields["summary"].split("]", 1)[0].lstrip("[")
        parent_id = self.parents.get(entity_id)
        if parent_id:
            parent_data, _, _ = parse_frontmatter(self.entity_paths[parent_id].read_text(encoding="utf-8"))
            self.persisted_parents.append(bool(parent_data["jira_key"]) and parent_data["jira_sync"] == "done")
        self.calls.append({"id": entity_id, "fields": fields})
        return {"key": f"PROJ-{len(self.calls)}"}

    def issue_status(self, key: str) -> str:
        return "To Do"

    def transitions(self, key: str) -> list[dict]:
        return []


def settings(board_dir: Path) -> SyncSettings:
    sync_dir = board_dir / "sync"
    sync_dir.mkdir()
    (sync_dir / "state.json").write_text('{"entities": {}, "last_run": null}\n', encoding="utf-8")
    tracker = sync_dir / "jira-config.json"
    tracker.write_text("{}", encoding="utf-8")
    return SyncSettings(
        board_dir=board_dir,
        sync_dir=sync_dir,
        relations_path=sync_dir / "relations.json",
        tracker_config_path=tracker,
        project_key="PROJ",
        board_label="board",
        remote_link_namespace="board",
        entity_glob="*.md",
        type_map={"epic": "Epic", "story": "Story", "task": "Task", "sub-task": "Sub-task"},
        status_map={"To Do": "To Do"},
        parent_strategy={"epic": "none", "story": "parent", "task": "parent", "sub-task": "parent"},
        aliases={},
    )


def write_entity(path: Path, entity_id: str, entity_type: str, parent: str = "") -> None:
    parent_line = f"parent: {parent}\n" if parent else ""
    path.write_text(
        "---\n"
        f"id: {entity_id}\n"
        f"type: {entity_type}\n"
        f'summary: "{entity_type} {entity_id}"\n'
        "status: To Do\n"
        "assignee: pending\n"
        'assignee_account_id: ""\n'
        f"{parent_line}"
        "children: []\n"
        "labels: []\n"
        'jira_key: ""\n'
        "jira_sync: pending\n"
        "---\n\n"
        f"# {entity_id}\n\n"
        "## Objetivo y contexto\n\n"
        "Trabajo respaldado por la evidencia del board.\n\n"
        "## Criterios de aceptación\n\n"
        "- El resultado se puede verificar.\n",
        encoding="utf-8",
    )


class DeterministicHierarchyTests(unittest.TestCase):
    def test_new_hierarchy_plan_apply_persists_parents_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            board_dir = Path(directory)
            config = settings(board_dir)
            paths = {
                "E1": board_dir / "E1.md",
                "S1": board_dir / "S1.md",
                "T1": board_dir / "T1.md",
                "ST1": board_dir / "ST1.md",
            }
            write_entity(paths["E1"], "E1", "epic")
            write_entity(paths["S1"], "S1", "story", "E1")
            write_entity(paths["T1"], "T1", "task", "S1")
            write_entity(paths["ST1"], "ST1", "sub-task", "T1")
            entities = load_local_entities(config)
            actions = plan_sync(entities, {}, None, config)
            plan_path = config.sync_dir / "approved.json"
            save_plan(plan_path, {"relations": []}, actions)

            payload = json.loads(plan_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema_version"], 3)
            self.assertEqual([action["entity_id"] for action in payload["actions"]], ["E1", "S1", "T1", "ST1"])
            verify_plan(plan_path, {"relations": []}, actions)

            client = FakeJiraClient(paths, {"S1": "E1", "T1": "S1", "ST1": "T1"})
            apply_actions(
                client, actions, entities, load_state(config), config, workers=1, email="test@example.test", token="token"
            )

            self.assertEqual([call["id"] for call in client.calls], ["E1", "S1", "T1", "ST1"])
            self.assertNotIn("parent", client.calls[0]["fields"])
            self.assertEqual(client.calls[1]["fields"]["parent"], {"key": "PROJ-1"})
            self.assertEqual(client.calls[2]["fields"]["parent"], {"key": "PROJ-2"})
            self.assertEqual(client.calls[3]["fields"]["parent"], {"key": "PROJ-3"})
            self.assertEqual(client.persisted_parents, [True, True, True])
            for index, entity_id in enumerate(paths, start=1):
                frontmatter, _, _ = parse_frontmatter(paths[entity_id].read_text(encoding="utf-8"))
                self.assertEqual(frontmatter["jira_key"], f"PROJ-{index}")
                self.assertEqual(frontmatter["jira_sync"], "done")
            persisted_state = load_state(config)
            self.assertEqual(persisted_state["entities"]["E1"]["jira_key"], "PROJ-1")

            refreshed = load_local_entities(config)
            remote = {
                entity.jira_key: {
                    "fields": {
                        "updated": datetime.now(timezone.utc).isoformat(),
                        "summary": f"[{entity.id}] {entity.summary}",
                        "status": {"name": "To Do"},
                        "assignee": None,
                        "labels": create_fields(entity, refreshed, config)["labels"],
                    }
                }
                for entity in refreshed.values()
            }
            self.assertTrue(all(action.action == "noop" for action in plan_sync(refreshed, remote, None, config)))

            locally_newer = {
                key: {
                    "fields": {
                        **issue["fields"],
                        "updated": "2000-01-01T00:00:00+00:00",
                    }
                }
                for key, issue in remote.items()
            }
            self.assertTrue(
                all(
                    action.fields.get("description", {}).get("type") == "doc"
                    for action in plan_sync(refreshed, locally_newer, None, config)
                    if action.action == "update_jira"
                )
            )

    def test_unresolvable_parent_fails_before_child_creation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            board_dir = Path(directory)
            config = settings(board_dir)
            write_entity(board_dir / "E1.md", "E1", "epic")
            write_entity(board_dir / "S1.md", "S1", "story", "E1")
            entities = load_local_entities(config)
            story_action = next(action for action in plan_sync(entities, {}, None, config) if action.entity_id == "S1")
            client = FakeJiraClient()

            with self.assertRaisesRegex(ValueError, "missing jira_key on required parent"):
                apply_actions(client, [story_action], entities, load_state(config), config, workers=1, email="a", token="b")
            self.assertEqual(client.calls, [])

    def test_create_uses_approved_payload_even_when_settings_change(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = settings(Path(directory))
            path = Path(directory) / "E1.md"
            write_entity(path, "E1", "epic")
            entity = load_local_entities(config)["E1"]
            action = plan_sync({"E1": entity}, {}, None, config)[0]
            self.assertEqual(action.fields["jira_fields"]["issuetype"], {"name": "Epic"})
            changed_config = SyncSettings(**{**config.__dict__, "type_map": {**config.type_map, "epic": "Changed Epic"}})
            client = FakeJiraClient()
            apply_actions(client, [action], {"E1": entity}, load_state(config), changed_config, workers=1, email="a", token="b")
            self.assertEqual(client.calls[0]["fields"]["issuetype"], {"name": "Epic"})

    def test_descriptions_preserve_actionable_board_content_and_templates_cover_standard(self) -> None:
        task_body = body("task", "T1 - Integración SDK")
        for heading in ("Objetivo y alcance", "Responsabilidades, contratos y dependencias", "Validación", "Supuestos y restricciones"):
            self.assertIn(heading, task_body)
        description = jira_description(task_body)
        rendered = json.dumps(description, ensure_ascii=False)
        self.assertIn("configuración, errores, compatibilidad, seguridad y observabilidad", rendered)
        self.assertIn("Pendiente de completar", rendered)
        existing_body = "# Alcance existente\n\nLa compatibilidad actual debe preservarse."
        self.assertIn("La compatibilidad actual debe preservarse.", json.dumps(jira_description(existing_body), ensure_ascii=False))


class SyncUnitTests(unittest.TestCase):
    def make_entity(self, entity_id: str, entity_type: str = "epic", parent: str | None = None) -> LocalEntity:
        return LocalEntity(
            id=entity_id,
            type=entity_type,
            summary=f"Summary {entity_id}",
            status="To Do",
            assignee="pending",
            assignee_account_id="",
            parent=parent,
            children=[],
            jira_key="",
            labels=[],
            path=Path(f"/tmp/{entity_id}.md"),
            mtime=datetime(2025, 1, 1, tzinfo=timezone.utc),
            body=f"# {entity_id}\n\n## Contexto\n\nContenido accionable.",
        )

    def test_parent_resolution_and_create_fields_support_all_strategies(self) -> None:
        config = settings(Path(tempfile.mkdtemp()))
        epic = self.make_entity("E1")
        epic.jira_key = "PROJ-1"
        story = self.make_entity("S1", "story", "E1")
        task = self.make_entity("T1", "task", "S1")
        task.jira_key = "PROJ-2"
        entities = {"E1": epic, "S1": story, "T1": task}
        self.assertIsNone(sync_board.resolve_parent_key(epic, entities, config))
        self.assertEqual(sync_board.resolve_parent_key(story, entities, config), "PROJ-1")
        ancestor_config = SyncSettings(
            **{**config.__dict__, "parent_strategy": {**config.parent_strategy, "task": "ancestor:epic"}}
        )
        self.assertEqual(sync_board.resolve_parent_key(task, entities, ancestor_config), "PROJ-1")
        fields = create_fields(story, entities, config)
        self.assertEqual(fields["parent"], {"key": "PROJ-1"})
        self.assertEqual(fields["description"]["type"], "doc")
        story.parent = "missing"
        with self.assertRaisesRegex(ValueError, "invalid parent strategy"):
            sync_board.resolve_parent_key(story, entities, config)

    def test_tracker_base_url_requires_https_or_cloud_id(self) -> None:
        with patch.dict(os.environ, {"JIRA_CLOUD_ID": "cloud", "JIRA_BASE_URL": "http://ignored"}, clear=True):
            self.assertEqual(sync_board.tracker_base_url(), "https://api.atlassian.com/ex/jira/cloud")
        with patch.dict(os.environ, {"JIRA_BASE_URL": "https://jira.example.test/"}, clear=True):
            self.assertEqual(sync_board.tracker_base_url(), "https://jira.example.test")
        with patch.dict(os.environ, {"JIRA_URL": "http://jira.example.test"}, clear=True):
            with self.assertRaisesRegex(ValueError, "HTTPS"):
                sync_board.tracker_base_url()
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "missing"):
                sync_board.tracker_base_url()

    def test_load_settings_and_maintenance_helpers_use_configured_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            board_dir = Path(directory)
            sync_dir = board_dir / "sync"
            sync_dir.mkdir()
            tracker_path = sync_dir / "jira-config.json"
            tracker_path.write_text(
                json.dumps(
                    {
                        "type_map": {"epic": "Epic"},
                        "status_map": {"To Do": "To Do"},
                        "parent_strategy": {"epic": "none"},
                        "aliases": {},
                    }
                ),
                encoding="utf-8",
            )
            board = BoardConfig(board_dir, board_dir / "Board.md", "Board", "*.md", "", sync_dir, sync_dir / "relations.json", "PROJ", "board", "board")
            with patch.object(sync_board, "load_board_config", return_value=board):
                loaded = sync_board.load_settings(board_dir)
            self.assertEqual(loaded.tracker_config_path, tracker_path)
            with patch.object(sync_board.subprocess, "run") as run:
                sync_board.rebuild_index(loaded)
                sync_board.refresh_relations_catalog(loaded)
            self.assertEqual(run.call_count, 2)

    def test_transition_and_update_actions_use_jira_client_contract(self) -> None:
        config = settings(Path(tempfile.mkdtemp()))
        client = Mock()
        client.issue_status.return_value = "To Do"
        sync_board.transition(client, "PROJ-1", "To Do", config)
        client.transition.assert_not_called()
        client.issue_status.return_value = "Open"
        client.transitions.return_value = [{"id": "11", "to": {"name": "To Do"}}]
        sync_board.transition(client, "PROJ-1", "To Do", config)
        client.transition.assert_called_once_with("PROJ-1", "11")
        client.transitions.return_value = []
        with self.assertRaisesRegex(RuntimeError, "no transition"):
            sync_board.transition(client, "PROJ-1", "To Do", config)
        with self.assertRaisesRegex(ValueError, "status without mapping"):
            sync_board.transition(client, "PROJ-1", "Unknown", config)

    def test_planning_helpers_cover_links_and_source_selection(self) -> None:
        config = settings(Path(tempfile.mkdtemp()))
        entity = self.make_entity("E1")
        entity.jira_key = "PROJ-1"
        self.assertEqual(canonical_labels(entity, {"E1": entity}, config), ["board", "E1"])
        old, new = datetime(2020, 1, 1, tzinfo=timezone.utc), datetime(2021, 1, 1, tzinfo=timezone.utc)
        self.assertEqual(decide_source(old, new, None), "jira")
        self.assertEqual(decide_source(new, old, None), "local")
        self.assertEqual(decide_source(old, old, None), "noop")
        document = {
            "commits": [{"id": "commit:abc", "url": "https://example.test/abc", "subject": "Commit"}],
            "pull_requests": [],
            "relations": [{"type": "evidence_for", "from": "commit:abc", "to": "asset:E1"}],
        }
        actions = remote_link_plan(document, {"E1": entity}, config)
        self.assertEqual(actions[0].action, "link_remote")
        self.assertEqual(remote_link_plan(document, {"E1": entity}, config, existing_links={"PROJ-1": [{"globalId": actions[0].fields["globalId"], "object": {"url": actions[0].fields["url"], "title": actions[0].fields["title"]}}]}), [])
        document["commits"][0].pop("url")
        with self.assertRaisesRegex(RuntimeError, "incomplete evidence"):
            remote_link_plan(document, {"E1": entity}, config)

    def test_adoption_plans_and_recovers_interrupted_create_without_duplicate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = settings(Path(directory))
            path = Path(directory) / "E1.md"
            write_entity(path, "E1", "epic")
            entity = load_local_entities(config)["E1"]
            candidate = {
                "key": "PROJ-42",
                "fields": {
                    "project": {"key": "PROJ"},
                    "issuetype": {"name": "Epic"},
                    "summary": "[E1] epic E1",
                    "labels": ["board", "E1"],
                },
            }
            adoption = plan_adoption(entity, [candidate], config)
            self.assertIsNotNone(adoption)
            self.assertEqual(adoption.action, "adopt_jira")
            self.assertEqual(adoption.jira_key, "PROJ-42")
            self.assertEqual(plan_sync({"E1": entity}, {}, None, config, {"E1": adoption})[0].action, "adopt_jira")
            plan_path = config.sync_dir / "approved.json"
            save_plan(plan_path, {"relations": []}, [adoption])
            saved = json.loads(plan_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["schema_version"], 3)
            self.assertEqual(saved["actions"][0]["fields"]["identity"]["summary"], "[E1] epic E1")
            verify_plan(plan_path, {"relations": []}, [adoption])

            client = Mock()
            client.search_by_asset_marker.return_value = [candidate]
            apply_actions(client, [adoption], {"E1": entity}, load_state(config), config, workers=1, email="a", token="b")
            client.create_issue.assert_not_called()
            frontmatter, _, _ = parse_frontmatter(path.read_text(encoding="utf-8"))
            self.assertEqual(frontmatter["jira_key"], "PROJ-42")
            self.assertEqual(frontmatter["jira_sync"], "done")

            entity = load_local_entities(config)["E1"]
            remote = {
                "PROJ-42": {
                    "fields": {
                        **candidate["fields"],
                        "updated": entity.mtime.isoformat(),
                        "status": {"name": "To Do"},
                        "assignee": None,
                    }
                }
            }
            self.assertEqual(plan_sync({"E1": entity}, remote, None, config)[0].action, "noop")

    def test_adoption_apply_rejects_changed_remote_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = settings(Path(directory))
            path = Path(directory) / "E1.md"
            write_entity(path, "E1", "epic")
            entity = load_local_entities(config)["E1"]
            candidate = {
                "key": "PROJ-42",
                "fields": {
                    "project": {"key": "PROJ"},
                    "issuetype": {"name": "Epic"},
                    "summary": "[E1] epic E1",
                    "labels": ["board", "E1"],
                },
            }
            adoption = plan_adoption(entity, [candidate], config)
            candidate["fields"]["summary"] = "[E1] changed remotely"
            client = Mock()
            client.search_by_asset_marker.return_value = [candidate]
            with self.assertRaisesRegex(RuntimeError, "contradictory summary marker"):
                apply_actions(client, [adoption], {"E1": entity}, load_state(config), config, workers=1, email="a", token="b")
            frontmatter, _, _ = parse_frontmatter(path.read_text(encoding="utf-8"))
            self.assertEqual(frontmatter["jira_key"], "")

    def test_adoption_rejects_ambiguous_or_invalid_identity(self) -> None:
        config = settings(Path(tempfile.mkdtemp()))
        entity = self.make_entity("E1")
        candidate = {
            "key": "PROJ-42",
            "fields": {
                "project": {"key": "PROJ"},
                "issuetype": {"name": "Epic"},
                "summary": "[E1] Summary E1",
                "labels": ["board"],
            },
        }
        with self.assertRaisesRegex(RuntimeError, "ambiguous"):
            plan_adoption(entity, [candidate, {**candidate, "key": "PROJ-43"}], config)
        candidate["fields"]["issuetype"]["name"] = "Task"
        with self.assertRaisesRegex(RuntimeError, "unexpected issue type"):
            plan_adoption(entity, [candidate], config)

    def test_apply_updates_and_link_batches(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = settings(Path(directory))
            path = Path(directory) / "E1.md"
            write_entity(path, "E1", "epic")
            entity = load_local_entities(config)["E1"]
            entity.jira_key = "PROJ-1"
            client = Mock()
            client.issue_status.return_value = "To Do"
            state = load_state(config)
            sync_board.apply_jira_update(
                client,
                PlanAction("E1", "update_jira", "", {"summary": "[E1] Changed", "labels": ["board"], "description": jira_description(entity.body)}),
                entity,
                state,
                config,
            )
            self.assertIn("description", client.update_issue.call_args.args[1])
            sync_board.apply_local_update(
                PlanAction("E1", "update_local", "", {"summary": "Local", "assignee_account_id": ""}),
                entity,
                state,
                config,
            )
            frontmatter, _, _ = parse_frontmatter(path.read_text(encoding="utf-8"))
            self.assertEqual(frontmatter["summary"], "Local")
            self.assertEqual(frontmatter["jira_sync"], "done")

            remote_client = Mock()
            remote_client.remote_links.return_value = []
            with patch.object(sync_board, "JiraClient", return_value=remote_client):
                self.assertEqual(
                    sync_board.apply_link_remote_batch(
                        "PROJ-1",
                        [PlanAction("E1", "link_remote", "", {"globalId": "g", "url": "https://example.test", "title": "Evidence"})],
                        "https://jira.example.test",
                        "a",
                        "b",
                        0,
                        Mock(),
                    ),
                    1,
                )
            remote_client.create_remote_link.assert_called_once()

    def test_apply_actions_parallelizes_only_remote_link_groups(self) -> None:
        config = settings(Path(tempfile.mkdtemp()))
        first, second = self.make_entity("E1"), self.make_entity("E2")
        first.jira_key, second.jira_key = "PROJ-1", "PROJ-2"
        client = Mock(base_url="https://jira.example.test", throttle_seconds=0, limiter=Mock())
        actions = [
            PlanAction("E2", "link_remote", "", {"globalId": "two", "url": "https://example.test/2", "title": "Two"}),
            PlanAction("E1", "link_remote", "", {"globalId": "one", "url": "https://example.test/1", "title": "One"}),
        ]
        with patch.object(sync_board, "apply_link_remote_batch", return_value=1) as link:
            apply_actions(client, actions, {"E1": first, "E2": second}, {}, config, workers=2, email="a", token="b")
        self.assertEqual(link.call_count, 2)

    def test_main_orchestrates_saved_and_applied_plans_without_remote_writes_on_save(self) -> None:
        config = settings(Path(tempfile.mkdtemp()))
        entity = self.make_entity("E1")
        entity.jira_key = "PROJ-1"
        args = Mock(save_plan=Path("/tmp/plan.json"), apply_plan=None, only="", prefer=None, workers=1)
        client = Mock()
        client.search_by_keys.return_value = {}
        client.remote_links.return_value = []
        with (
            patch.object(sync_board, "parse_args", return_value=args),
            patch.object(sync_board, "load_settings", return_value=config),
            patch.object(sync_board, "load_document", return_value={"relations": []}),
            patch.object(sync_board, "load_local_entities", return_value={"E1": entity}),
            patch.object(sync_board, "tracker_base_url", return_value="https://jira.example.test"),
            patch.object(sync_board, "JiraClient", return_value=client),
            patch.object(sync_board, "plan_sync", return_value=[]),
            patch.object(sync_board, "remote_link_plan", return_value=[]),
            patch.object(sync_board, "save_plan") as save,
            patch.dict(os.environ, {"JIRA_EMAIL": "a", "JIRA_API_TOKEN": "b"}, clear=False),
        ):
            self.assertEqual(sync_board.main(), 0)
        save.assert_called_once()
        client.create_issue.assert_not_called()

    def test_main_applies_verified_plan_and_persists_state(self) -> None:
        config = settings(Path(tempfile.mkdtemp()))
        entity = self.make_entity("E1")
        entity.jira_key = "PROJ-1"
        args = Mock(save_plan=None, apply_plan=Path("/tmp/plan.json"), only="", prefer=None, workers=1)
        client = Mock()
        client.search_by_keys.return_value = {}
        client.remote_links.return_value = []
        with (
            patch.object(sync_board, "parse_args", return_value=args),
            patch.object(sync_board, "load_settings", return_value=config),
            patch.object(sync_board, "load_document", return_value={"relations": []}),
            patch.object(sync_board, "load_local_entities", return_value={"E1": entity}),
            patch.object(sync_board, "tracker_base_url", return_value="https://jira.example.test"),
            patch.object(sync_board, "JiraClient", return_value=client),
            patch.object(sync_board, "plan_sync", return_value=[]),
            patch.object(sync_board, "remote_link_plan", return_value=[]),
            patch.object(sync_board, "verify_plan") as verify,
            patch.object(sync_board, "apply_actions") as apply,
            patch.object(sync_board, "save_state") as save,
            patch.object(sync_board, "refresh_relations_catalog") as refresh,
            patch.object(sync_board, "rebuild_index") as rebuild,
            patch.dict(os.environ, {"JIRA_EMAIL": "a", "JIRA_API_TOKEN": "b"}, clear=False),
        ):
            self.assertEqual(sync_board.main(), 0)
        verify.assert_called_once()
        apply.assert_called_once()
        save.assert_called_once()
        refresh.assert_called_once_with(config)
        rebuild.assert_called_once_with(config)


if __name__ == "__main__":
    unittest.main()
