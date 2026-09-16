"""Markdown entity access for local-board tracker synchronization."""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sync_models import LocalEntity, SyncSettings


def parse_list(value: str) -> list[str]:
    value = value.strip()
    if not value or value == "[]":
        return []
    if not (value.startswith("[") and value.endswith("]")):
        return []
    return [item.strip().strip('"').strip("'") for item in value[1:-1].split(",") if item.strip()]


def parse_scalar(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        try:
            parsed = json.loads(value)
            if isinstance(parsed, str):
                return parsed
        except json.JSONDecodeError:
            pass
        return value[1:-1]
    return value


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str, str]:
    if not text.startswith("---\n"):
        raise ValueError("missing frontmatter")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise ValueError("unclosed frontmatter")
    raw, body = text[4:end], text[end + 5 :]
    data: dict[str, Any] = {}
    for line in raw.splitlines():
        if not line or line[0] in " \t" or ":" not in line:
            continue
        key, value = (part.strip() for part in line.split(":", 1))
        data[key] = parse_list(value) if key in ("children", "labels") else parse_scalar(value)
    return data, raw, body


def format_frontmatter_value(key: str, value: Any) -> str:
    if key in ("children", "labels"):
        items = value if isinstance(value, list) else parse_list(str(value))
        rendered = ", ".join(json.dumps(item, ensure_ascii=False) for item in items)
        return f"{key}: [{rendered}]" if items else f"{key}: []"
    if key in ("summary", "assignee_account_id", "jira_key"):
        return f"{key}: {json.dumps(str(value), ensure_ascii=False)}"
    return f"{key}: {value}"


def write_frontmatter_update(path: Path, updates: dict[str, Any]) -> None:
    data, raw, body = parse_frontmatter(path.read_text(encoding="utf-8"))
    data.update(updates)
    managed = {"summary", "status", "assignee", "assignee_account_id", "labels", "jira_key", "jira_sync"}
    lines, emitted = ["---"], set()
    for line in raw.splitlines():
        if not line.strip() or line[0] in " \t" or ":" not in line:
            lines.append(line)
            continue
        key = line.split(":", 1)[0].strip()
        if key in managed and key in data:
            lines.append(format_frontmatter_value(key, data[key]))
            emitted.add(key)
        else:
            lines.append(line)
    for key in managed:
        if key in updates and key not in emitted:
            lines.append(format_frontmatter_value(key, data[key]))
    lines.append("---")
    atomic_write_text(path, "\n".join(lines) + "\n" + body.lstrip("\n"))


def atomic_write_text(path: Path, content: str) -> None:
    """Replace one local sync artifact without exposing a partially written file."""
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent, text=True)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def load_local_entities(settings: SyncSettings) -> dict[str, LocalEntity]:
    entities: dict[str, LocalEntity] = {}
    for path in sorted(settings.board_dir.rglob(settings.entity_glob)):
        if settings.sync_dir in path.parents or settings.board_dir / "_meta" in path.parents:
            continue
        try:
            data, _, body = parse_frontmatter(path.read_text(encoding="utf-8"))
        except ValueError:
            continue
        entity_id = data.get("id")
        if not entity_id:
            continue
        assignee = data.get("assignee", "pending")
        entities[entity_id] = LocalEntity(
            id=entity_id,
            type=data.get("type", ""),
            summary=data.get("summary", ""),
            status=data.get("status", "To Do"),
            assignee=assignee,
            assignee_account_id=data.get("assignee_account_id") or settings.aliases.get(assignee, ""),
            parent=data.get("parent") or None,
            children=list(data.get("children") or []),
            jira_key=(data.get("jira_key") or "").strip(),
            labels=list(data.get("labels") or []),
            path=path,
            mtime=datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc),
            body=body.strip(),
        )
    return entities
