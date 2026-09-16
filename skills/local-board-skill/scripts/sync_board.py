#!/usr/bin/env python3
"""Command-line orchestrator for a configured local board and Jira sync."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from board_config import load_board_config
from relations import load_document
from sync_client import JiraClient, WriteLimiter
from sync_entities import atomic_write_text, load_local_entities, write_frontmatter_update
from sync_models import LocalEntity, PlanAction, SyncSettings
from sync_planning import (
    canonical_labels,
    identity_evidence,
    jira_description,
    plan_adoption,
    plan_sync,
    remote_link_plan,
    save_plan,
    verify_plan,
)


def load_settings(board_dir: Path) -> SyncSettings:
    config = load_board_config(board_dir)
    tracker_config_path = config.sync_dir / "jira-config.json"
    tracker = json.loads(tracker_config_path.read_text(encoding="utf-8"))
    required = ("type_map", "status_map", "parent_strategy", "aliases")
    missing = [key for key in required if not isinstance(tracker.get(key), dict)]
    if missing:
        raise ValueError(f"incomplete tracker configuration: {', '.join(missing)}")
    return SyncSettings(config.board_dir, config.sync_dir, config.relations_file, tracker_config_path, config.jira_project_key, config.jira_label, config.remote_link_namespace, config.entity_glob, tracker["type_map"], tracker["status_map"], tracker["parent_strategy"], tracker["aliases"])


def tracker_base_url() -> str:
    cloud_id = os.environ.get("JIRA_CLOUD_ID", "").strip()
    site = (os.environ.get("JIRA_BASE_URL") or os.environ.get("JIRA_URL") or "").rstrip("/")
    if cloud_id:
        return f"https://api.atlassian.com/ex/jira/{cloud_id}"
    if site:
        if not site.startswith("https://"):
            raise ValueError("JIRA_BASE_URL/JIRA_URL debe usar HTTPS")
        return site
    raise ValueError("missing JIRA_CLOUD_ID or JIRA_BASE_URL")


def state_path(settings: SyncSettings) -> Path:
    return settings.sync_dir / "state.json"


def load_state(settings: SyncSettings) -> dict[str, Any]:
    path = state_path(settings)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"entities": {}, "last_run": None}


def save_state(settings: SyncSettings, state: dict[str, Any]) -> None:
    atomic_write_text(state_path(settings), json.dumps(state, indent=2, ensure_ascii=False) + "\n")


def resolve_parent_key(entity: LocalEntity, entities: dict[str, LocalEntity], settings: SyncSettings) -> str | None:
    strategy = settings.parent_strategy.get(entity.type, "none")
    if strategy == "none":
        return None
    current = entities.get(entity.parent or "") if strategy == "parent" else entity
    target_type = strategy.split(":", 1)[1] if strategy.startswith("ancestor:") else None
    while current:
        if not target_type or current.type == target_type:
            if not current.jira_key:
                raise ValueError(
                    f"missing jira_key on required parent/ancestor '{current.id}' for entity '{entity.id}'"
                )
            return current.jira_key
        current = entities.get(current.parent or "")
    raise ValueError(f"invalid parent strategy for {entity.type}: {strategy}")


def create_fields(
    entity: LocalEntity,
    entities: dict[str, LocalEntity],
    settings: SyncSettings,
    planned_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    fields = dict(planned_fields or {
        "project": {"key": settings.project_key},
        "issuetype": {"name": settings.type_map[entity.type]},
        "summary": f"[{entity.id}] {entity.summary}",
        "description": jira_description(entity.body),
        "labels": canonical_labels(entity, entities, settings),
    })
    if planned_fields is None and entity.assignee_account_id:
        fields["assignee"] = {"accountId": entity.assignee_account_id}
    if parent_key := resolve_parent_key(entity, entities, settings):
        fields["parent"] = {"key": parent_key}
    return fields


def transition(client: JiraClient, key: str, status: str, settings: SyncSettings) -> None:
    target = settings.status_map.get(status)
    if not target:
        raise ValueError(f"status without mapping in {settings.tracker_config_path}: {status}")
    if client.issue_status(key) == target:
        return
    for item in client.transitions(key):
        if (item.get("to") or {}).get("name") == target:
            client.transition(key, str(item["id"]))
            return
    raise RuntimeError(f"no transition to {target} for {key}")


def record_state(state: dict[str, Any], entity: LocalEntity, source: str) -> None:
    state.setdefault("entities", {})[entity.id] = {"jira_key": entity.jira_key, "last_sync_at": datetime.now(timezone.utc).isoformat(), "last_applied_source": source, "last_local_mtime": entity.mtime.isoformat()}


def persist_created_entity(state: dict[str, Any], entity: LocalEntity, settings: SyncSettings) -> None:
    write_frontmatter_update(
        entity.path,
        {"jira_key": entity.jira_key, "jira_sync": "created", "labels": entity.labels},
    )
    record_state(state, entity, "local")
    save_state(settings, state)


def apply_create(client: JiraClient, action: PlanAction, entity: LocalEntity, entities: dict[str, LocalEntity], state: dict[str, Any], settings: SyncSettings) -> None:
    # Parent keys are intentionally resolved here, after prior hierarchy layers persist them.
    planned_fields = action.fields.get("jira_fields")
    if not isinstance(planned_fields, dict):
        raise RuntimeError(f"approved create for '{entity.id}' has no Jira payload; regenerate and reapprove the plan")
    created = client.create_issue(create_fields(entity, entities, settings, planned_fields))
    if not isinstance(created, dict) or not isinstance(created.get("key"), str) or not created["key"]:
        raise RuntimeError(f"create for entity '{entity.id}' returned no Jira key; cannot continue hierarchy")
    entity.jira_key = created["key"]
    entity.labels = canonical_labels(entity, entities, settings)
    persist_created_entity(state, entity, settings)
    transition(client, entity.jira_key, entity.status, settings)
    write_frontmatter_update(entity.path, {"jira_sync": "done"})
    record_state(state, entity, "local")
    save_state(settings, state)


def apply_adopt_jira(
    client: JiraClient,
    action: PlanAction,
    entity: LocalEntity,
    entities: dict[str, LocalEntity],
    state: dict[str, Any],
    settings: SyncSettings,
) -> None:
    expected = action.fields.get("identity")
    if not isinstance(expected, dict) or expected.get("key") != action.jira_key:
        raise RuntimeError(f"approved adoption for '{entity.id}' has invalid identity evidence")
    candidates = client.search_by_asset_marker(settings.project_key, entity.id)
    matching = [
        identity_evidence(entity, candidate, settings)
        for candidate in candidates
        if (candidate.get("fields") or {}).get("summary", "").startswith(f"[{entity.id}]")
    ]
    if len(matching) != 1 or matching[0] != expected:
        raise RuntimeError(f"approved Jira identity for '{entity.id}' changed; regenerate and reapprove the plan")
    entity.jira_key = action.jira_key
    entity.labels = canonical_labels(entity, entities, settings)
    write_frontmatter_update(entity.path, {"jira_key": entity.jira_key, "jira_sync": "done", "labels": entity.labels})
    record_state(state, entity, "jira")
    save_state(settings, state)


def apply_jira_update(client: JiraClient, action: PlanAction, entity: LocalEntity, state: dict[str, Any], settings: SyncSettings) -> None:
    fields = {"summary": action.fields["summary"]} if "summary" in action.fields else {}
    if "labels" in action.fields:
        fields["labels"] = action.fields["labels"]
    if "assignee_account_id" in action.fields:
        fields["assignee"] = {"accountId": action.fields["assignee_account_id"]} if action.fields["assignee_account_id"] else None
    if "description" in action.fields:
        fields["description"] = action.fields["description"]
    if fields:
        client.update_issue(entity.jira_key, fields)
    if "status" in action.fields:
        transition(client, entity.jira_key, action.fields["status"], settings)
    write_frontmatter_update(entity.path, {"jira_sync": "done"})
    record_state(state, entity, "local")


def apply_local_update(action: PlanAction, entity: LocalEntity, state: dict[str, Any], settings: SyncSettings) -> None:
    updates = {**action.fields, "jira_sync": "done"}
    updates["assignee"] = settings.accounts_to_aliases.get(updates.get("assignee_account_id", ""), updates.get("assignee", "pending"))
    write_frontmatter_update(entity.path, updates)
    record_state(state, entity, "jira")


def apply_entity_action(client: JiraClient, action: PlanAction, entity: LocalEntity, entities: dict[str, LocalEntity], state: dict[str, Any], settings: SyncSettings) -> None:
    if action.action == "create":
        apply_create(client, action, entity, entities, state, settings)
    elif action.action == "adopt_jira":
        apply_adopt_jira(client, action, entity, entities, state, settings)
    elif action.action == "update_jira":
        apply_jira_update(client, action, entity, state, settings)
    elif action.action == "update_local":
        apply_local_update(action, entity, state, settings)


def apply_link_remote_batch(
    jira_key: str,
    actions: list[PlanAction],
    base_url: str,
    email: str,
    token: str,
    throttle_seconds: float,
    limiter: WriteLimiter,
) -> int:
    client = JiraClient(base_url, email, token, throttle_seconds=throttle_seconds, limiter=limiter)
    existing = client.remote_links(jira_key)
    linked = 0
    for action in actions:
        global_id = action.fields["globalId"]
        matching = next((link for link in existing if link.get("globalId") == global_id), None)
        if matching and (matching.get("object") or {}).get("url") == action.fields["url"] and (matching.get("object") or {}).get("title") == action.fields["title"]:
            continue
        if matching and matching.get("id"):
            client.update_remote_link(jira_key, str(matching["id"]), action.fields)
        else:
            client.create_remote_link(jira_key, action.fields)
        linked += 1
    return linked


def apply_actions(
    client: JiraClient,
    actions: list[PlanAction],
    entities: dict[str, LocalEntity],
    state: dict[str, Any],
    settings: SyncSettings,
    *,
    workers: int,
    email: str,
    token: str,
) -> None:
    entity_actions = [action for action in actions if action.action in {"adopt_jira", "create", "update_jira", "update_local"}]
    link_actions = [action for action in actions if action.action == "link_remote"]

    entity_actions.sort(key=lambda action: (settings.type_order.get(entities[action.entity_id].type, 9), action.entity_id))
    for action in entity_actions:
        apply_entity_action(client, action, entities[action.entity_id], entities, state, settings)

    if not link_actions:
        return

    by_issue: dict[str, list[PlanAction]] = defaultdict(list)
    for action in link_actions:
        entity = entities.get(action.entity_id)
        if entity and entity.jira_key:
            by_issue[entity.jira_key].append(action)

    throttle = client.throttle_seconds
    limiter = client.limiter
    base_url = client.base_url
    linked_total = 0
    issue_workers = max(1, min(workers, len(by_issue)))
    print(f"Linking remote evidence: issues={len(by_issue)} workers={issue_workers}", file=sys.stderr)

    with ThreadPoolExecutor(max_workers=issue_workers) as pool:
        futures = [
            pool.submit(apply_link_remote_batch, jira_key, issue_actions, base_url, email, token, throttle, limiter)
            for jira_key, issue_actions in sorted(by_issue.items())
        ]
        for future in as_completed(futures):
            linked_total += future.result()
            if linked_total and linked_total % 100 == 0:
                print(f"Linked {linked_total} remote evidence items...", file=sys.stderr)

    if linked_total:
        print(f"Linked {linked_total} remote evidence items total", file=sys.stderr)


def rebuild_index(settings: SyncSettings) -> None:
    subprocess.run([sys.executable, str(Path(__file__).with_name("rebuild_index.py")), "--board-dir", str(settings.board_dir)], check=True)


def refresh_relations_catalog(settings: SyncSettings) -> None:
    subprocess.run(
        [
            sys.executable,
            str(Path(__file__).with_name("refresh_relations_catalog.py")),
            "--board-dir",
            str(settings.board_dir),
            "--workspace",
            str(settings.board_dir.parent),
        ],
        check=True,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Sync a configured local board with Jira. Hierarchical creates are applied "
            "deterministically and persist each parent key before creating children."
        )
    )
    parser.add_argument("--board-dir", type=Path, default=Path(os.environ.get("BOARD_DIR", Path.cwd() / "board")))
    parser.add_argument("--save-plan", type=Path)
    parser.add_argument("--apply-plan", type=Path)
    parser.add_argument("--prefer", choices=["local", "jira"])
    parser.add_argument("--only", default="")
    parser.add_argument("--workers", type=int, default=int(os.environ.get("JIRA_SYNC_WORKERS", "12")))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.save_plan and args.apply_plan:
        raise ValueError("--save-plan and --apply-plan are mutually exclusive")
    settings = load_settings(args.board_dir)
    email, token = os.environ.get("JIRA_EMAIL", ""), os.environ.get("JIRA_API_TOKEN") or os.environ.get("JIRA_TOKEN", "")
    if not email or not token:
        print("ERROR: missing JIRA_EMAIL / JIRA_API_TOKEN", file=sys.stderr)
        return 1
    document = load_document(settings.relations_path)
    entities = load_local_entities(settings)
    selected_ids: set[str] | None = None
    if args.only:
        requested = set(filter(None, (item.strip() for item in args.only.split(","))))
        selected_ids = requested
        if requested - entities.keys():
            raise ValueError(f"unknown IDs: {sorted(requested - entities.keys())}")
    client = JiraClient(tracker_base_url(), email, token)
    planning_entities = {key: value for key, value in entities.items() if selected_ids is None or key in selected_ids}
    adoptions = {
        entity.id: adoption
        for entity in planning_entities.values()
        if not entity.jira_key
        if (adoption := plan_adoption(entity, client.search_by_asset_marker(settings.project_key, entity.id), settings))
    }
    actions = plan_sync(
        planning_entities,
        client.search_by_keys([entity.jira_key for entity in planning_entities.values() if entity.jira_key]),
        args.prefer,
        settings,
        adoptions,
    )
    for entity_id, adoption in adoptions.items():
        entities[entity_id].jira_key = adoption.jira_key
    existing_links = {entity.jira_key: client.remote_links(entity.jira_key) for entity in planning_entities.values() if entity.jira_key}
    actions.extend(remote_link_plan(document, entities, settings, selected_ids, existing_links))
    if args.save_plan:
        save_plan(args.save_plan, document, actions)
        return 0
    if not args.apply_plan:
        print("DRY-RUN: use --save-plan, review it, then use --apply-plan.")
        return 0
    verify_plan(args.apply_plan, document, actions)
    state = load_state(settings)
    apply_actions(client, actions, entities, state, settings, workers=args.workers, email=email, token=token)
    state["last_run"] = datetime.now(timezone.utc).isoformat()
    save_state(settings, state)
    refresh_relations_catalog(settings)
    rebuild_index(settings)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
