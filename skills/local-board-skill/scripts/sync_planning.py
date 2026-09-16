"""Pure planning and persisted-plan validation for tracker synchronization."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sync_models import LocalEntity, PlanAction, SyncSettings


def jira_description(body: str) -> dict[str, Any]:
    """Render the board Markdown body as an ADF document accepted by Jira."""
    content: list[dict[str, Any]] = []
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#"):
            text = line.lstrip("#").strip()
            if text:
                content.append(
                    {
                        "type": "heading",
                        "attrs": {"level": min(len(line) - len(line.lstrip("#")), 6)},
                        "content": [{"type": "text", "text": text}],
                    }
                )
            continue
        if line.startswith(("- ", "* ")):
            content.append(
                {
                    "type": "bulletList",
                    "content": [
                        {
                            "type": "listItem",
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [{"type": "text", "text": line[2:]}],
                                }
                            ],
                        }
                    ],
                }
            )
            continue
        content.append({"type": "paragraph", "content": [{"type": "text", "text": line}]})
    if not content:
        raise ValueError("entity body is empty; add actionable board content before Jira synchronization")
    return {"type": "doc", "version": 1, "content": content}


def canonical_labels(entity: LocalEntity, entities: dict[str, LocalEntity], settings: SyncSettings) -> list[str]:
    labels = [settings.board_label, entity.id]
    if entity.parent:
        labels.append(entity.parent)
    parent = entities.get(entity.parent or "")
    if entity.type == "sub-task" and parent and parent.parent:
        labels.append(parent.parent)
    return list(dict.fromkeys([*labels, *entity.labels]))


def remote_status_to_local(name: str, settings: SyncSettings) -> str:
    try:
        return settings.remote_to_local_status[name]
    except KeyError as exc:
        raise ValueError(f"remote status without mapping in {settings.tracker_config_path}: {name}") from exc


def strip_local_id(summary: str, entity_id: str) -> str:
    for prefix in (f"[{entity_id}] ", f"[{entity_id}]"):
        if summary.startswith(prefix):
            return summary[len(prefix) :].lstrip()
    return summary


def remote_summary(summary: str, entity_id: str) -> str:
    return summary if summary.startswith(f"[{entity_id}]") else f"[{entity_id}] {summary}"


def identity_evidence(entity: LocalEntity, remote: dict[str, Any], settings: SyncSettings) -> dict[str, str]:
    fields = remote.get("fields") or {}
    key = remote.get("key")
    if not isinstance(key, str) or not key:
        raise RuntimeError(f"identity candidate for '{entity.id}' has no Jira key")
    project = (fields.get("project") or {}).get("key") or ""
    issue_type = (fields.get("issuetype") or {}).get("name") or ""
    summary = fields.get("summary") or ""
    labels = fields.get("labels") or []
    marker = f"[{entity.id}]"
    if project != settings.project_key:
        raise RuntimeError(f"identity candidate {remote.get('key', '<unknown>')} has unexpected project '{project}'")
    if issue_type != settings.type_map[entity.type]:
        raise RuntimeError(f"identity candidate {remote.get('key', '<unknown>')} has unexpected issue type '{issue_type}'")
    if not summary.startswith(marker) or summary != remote_summary(entity.summary, entity.id):
        raise RuntimeError(f"identity candidate {remote.get('key', '<unknown>')} has a contradictory summary marker")
    if settings.board_label not in labels:
        raise RuntimeError(f"identity candidate {remote.get('key', '<unknown>')} is missing board label '{settings.board_label}'")
    return {
        "key": key,
        "project": project,
        "issue_type": issue_type,
        "summary": summary,
        "board_label": settings.board_label,
    }


def plan_adoption(entity: LocalEntity, candidates: list[dict[str, Any]], settings: SyncSettings) -> PlanAction | None:
    if entity.jira_key:
        return None
    matching_marker = [candidate for candidate in candidates if (candidate.get("fields") or {}).get("summary", "").startswith(f"[{entity.id}]")]
    if not matching_marker:
        return None
    evidence = [identity_evidence(entity, candidate, settings) for candidate in matching_marker]
    if len(evidence) != 1:
        raise RuntimeError(f"ambiguous Jira identity for '{entity.id}': candidates {', '.join(item['key'] for item in evidence)}")
    return PlanAction(
        entity.id,
        "adopt_jira",
        "one exact Jira identity candidate found; adoption requires revalidation during apply",
        {"identity": evidence[0]},
        evidence[0]["key"],
    )


def remote_link_title(title: str) -> str:
    return title if len(title) <= 255 else title[:252] + "..."


def decide_source(local: datetime, remote: datetime, prefer: str | None) -> str:
    if prefer in ("local", "jira"):
        return prefer
    if remote > local:
        return "jira"
    return "local" if local > remote else "noop"


def remote_values(entity: LocalEntity, remote: dict[str, Any], settings: SyncSettings) -> tuple[datetime, dict[str, Any]]:
    fields = remote["fields"]
    updated = datetime.fromisoformat(fields["updated"].replace("Z", "+00:00")).astimezone(timezone.utc)
    account_id = ((fields.get("assignee") or {}) or {}).get("accountId") or ""
    return updated, {
        "summary": strip_local_id(fields.get("summary") or "", entity.id),
        "status": remote_status_to_local((fields.get("status") or {}).get("name") or "", settings),
        "assignee": settings.accounts_to_aliases.get(account_id, "pending"),
        "assignee_account_id": account_id,
        "labels": sorted(fields.get("labels") or []),
    }


def local_update_delta(entity: LocalEntity, values: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in values.items()
        if value != getattr(entity, key, None) and not (key == "labels" and set(value) == set(entity.labels))
    }


def remote_update_delta(entity: LocalEntity, values: dict[str, Any], labels: list[str]) -> dict[str, Any]:
    delta: dict[str, Any] = {}
    if entity.summary != values["summary"]:
        delta["summary"] = remote_summary(entity.summary, entity.id)
    if entity.status != values["status"]:
        delta["status"] = entity.status
    if entity.assignee_account_id != values["assignee_account_id"]:
        delta["assignee_account_id"] = entity.assignee_account_id or None
    if set(labels) != set(values["labels"]):
        delta["labels"] = labels
    return delta


def planned_create_fields(entity: LocalEntity, entities: dict[str, LocalEntity], settings: SyncSettings) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "project": {"key": settings.project_key},
        "issuetype": {"name": settings.type_map[entity.type]},
        "summary": remote_summary(entity.summary, entity.id),
        "description": jira_description(entity.body),
        "labels": canonical_labels(entity, entities, settings),
    }
    if entity.assignee_account_id:
        fields["assignee"] = {"accountId": entity.assignee_account_id}
    return fields


def entity_plan(entity: LocalEntity, remote: dict[str, Any] | None, prefer: str | None, settings: SyncSettings, entities: dict[str, LocalEntity]) -> PlanAction:
    if not entity.jira_key:
        strategy = settings.parent_strategy.get(entity.type, "none")
        return PlanAction(
            entity.id,
            "create",
            "missing local tracker key; parent is resolved during deterministic apply",
            {
                "jira_fields": planned_create_fields(entity, entities, settings),
                "status": entity.status,
                "parent_strategy": strategy,
                "parent_entity_id": entity.parent or "",
            },
        )
    if not remote:
        return PlanAction(entity.id, "skip", f"tracker key {entity.jira_key} not found", jira_key=entity.jira_key)
    remote_time, values = remote_values(entity, remote, settings)
    source = decide_source(entity.mtime, remote_time, prefer)
    if source == "noop":
        return PlanAction(entity.id, "noop", "equal timestamps", jira_key=entity.jira_key)
    local_labels = sorted(canonical_labels(entity, entities, settings))
    if source == "jira":
        delta = local_update_delta(entity, values)
        reason = f"remote newer ({remote_time.isoformat()} > {entity.mtime.isoformat()})"
        return PlanAction(entity.id, "update_local" if delta else "noop", reason, delta, entity.jira_key)
    delta = remote_update_delta(entity, values, local_labels)
    # Jira does not expose a stable Markdown representation to compare with the
    # local asset. When the local asset wins, it is authoritative for the body.
    delta["description"] = jira_description(entity.body)
    reason = f"local newer ({entity.mtime.isoformat()} > {remote_time.isoformat()})"
    if prefer:
        reason += f" [forced prefer={prefer}]"
    return PlanAction(entity.id, "update_jira" if delta else "noop", reason, delta, entity.jira_key)


def plan_sync(
    entities: dict[str, LocalEntity],
    remote: dict[str, dict[str, Any]],
    prefer: str | None,
    settings: SyncSettings,
    adoptions: dict[str, PlanAction] | None = None,
) -> list[PlanAction]:
    ordered = sorted(entities.values(), key=lambda entity: (settings.type_order.get(entity.type, 9), entity.id))
    return [(adoptions or {}).get(entity.id) or entity_plan(entity, remote.get(entity.jira_key), prefer, settings, entities) for entity in ordered]


def remote_link_action(
    relation: dict[str, Any],
    nodes: dict[str, dict[str, Any]],
    entities: dict[str, LocalEntity],
    settings: SyncSettings,
    selected_ids: set[str] | None,
    existing_links: dict[str, list[dict[str, Any]]] | None,
) -> tuple[PlanAction | None, str | None]:
    source, target = relation.get("from", ""), relation.get("to", "")
    if relation.get("type") != "evidence_for" or not source.startswith(("commit:", "pull_request:")) or not target.startswith("asset:"):
        return None, None
    node, asset_id = nodes.get(source, {}), target.removeprefix("asset:")
    if selected_ids is not None and asset_id not in selected_ids:
        return None, None
    entity, url, title = entities.get(asset_id), node.get("url"), node.get("title") or node.get("subject")
    if not entity or not isinstance(url, str) or not url or not isinstance(title, str) or not title:
        return None, f"{source} -> {target}"
    fields = {
        "globalId": f"urn:{settings.remote_link_namespace}:{source}",
        "url": url,
        "title": remote_link_title(title),
    }
    current = existing_links.get(entity.jira_key, []) if existing_links else []
    if any(
        link.get("globalId") == fields["globalId"]
        and (link.get("object") or {}).get("url") == fields["url"]
        and (link.get("object") or {}).get("title") == fields["title"]
        for link in current
    ):
        return None, None
    return PlanAction(asset_id, "link_remote", f"{source} -> {asset_id}", fields, entity.jira_key), None


def remote_link_plan(
    document: dict[str, Any],
    entities: dict[str, LocalEntity],
    settings: SyncSettings,
    selected_ids: set[str] | None = None,
    existing_links: dict[str, list[dict[str, Any]]] | None = None,
) -> list[PlanAction]:
    nodes = {node["id"]: node for collection in ("commits", "pull_requests") for node in document.get(collection, [])}
    actions: list[PlanAction] = []
    incomplete: list[str] = []
    for relation in document.get("relations", []):
        action, missing = remote_link_action(relation, nodes, entities, settings, selected_ids, existing_links)
        if missing:
            incomplete.append(missing)
        if action:
            actions.append(action)
    if incomplete:
        raise RuntimeError("incomplete evidence metadata for remote links: " + ", ".join(sorted(incomplete)))
    return actions


def document_checksum(document: dict[str, Any]) -> str:
    stable_document = {key: value for key, value in document.items() if key != "generated_at"}
    canonical = json.dumps(stable_document, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def save_plan(path: Path, document: dict[str, Any], actions: list[PlanAction]) -> None:
    layers: dict[str, list[str]] = {}
    for action in actions:
        if action.action in {"adopt_jira", "create", "update_jira", "update_local"}:
            layers.setdefault(action.action, []).append(action.entity_id)
    payload = {
        "schema_version": 3,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "relations_checksum": document_checksum(document),
        "layers": layers,
        "actions": [asdict(action) for action in actions],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _link_remote_keys(actions: list[PlanAction] | list[dict[str, Any]]) -> set[tuple[str, str, str]]:
    keys: set[tuple[str, str, str]] = set()
    for action in actions:
        if isinstance(action, dict):
            if action.get("action") != "link_remote":
                continue
            fields = action.get("fields") or {}
            keys.add((action["entity_id"], fields.get("globalId", ""), fields.get("url", "")))
        else:
            if action.action != "link_remote":
                continue
            keys.add((action.entity_id, action.fields.get("globalId", ""), action.fields.get("url", "")))
    return keys


def _action_keys(actions: list[PlanAction] | list[dict[str, Any]]) -> set[str]:
    keys: set[str] = set()
    for action in actions:
        payload = asdict(action) if isinstance(action, PlanAction) else action
        keys.add(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return keys


def verify_plan(path: Path, document: dict[str, Any], actions: list[PlanAction]) -> None:
    saved = json.loads(path.read_text(encoding="utf-8"))
    if saved.get("schema_version") != 3:
        raise RuntimeError("approved plan is stale or unsupported; regenerate and reapprove it")
    if saved.get("relations_checksum") != document_checksum(document):
        raise RuntimeError("approved plan is stale: relations graph changed; regenerate and reapprove it")
    saved_links = _link_remote_keys(saved.get("actions", []))
    current_links = _link_remote_keys(actions)
    if saved_links != current_links:
        raise RuntimeError("approved plan is stale: link_remote actions changed; regenerate and reapprove it")
    if _action_keys(saved.get("actions", [])) != _action_keys(actions):
        raise RuntimeError("approved plan is stale: entity actions or scope changed; regenerate and reapprove it")
